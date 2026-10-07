#!/usr/bin/env python3
"""Offline comparison of shared-pool and region-aware eviction policies.

The trace, tokenizer, page size, and synthetic completion construction are
shared with the existing fixed-ratio simulator.  This script only changes
the finite-cache victim selection, so it can isolate UniCache-style global
competition from the existing request-region capacity policy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BASE_SCRIPT = ROOT / "experiments/固定分区试验对比/scripts/select_agent_cache_capacity_ratio.py"
MODEL_DEFAULT = Path(
    "/mnt/public/dai-sys/.cache/hub/hub/models--deepseek-ai--DeepSeek-V4-Flash/"
    "snapshots/fd53f944496234770ba80e15004f9b6d269a71f5"
)
CLASSIFIER_DEFAULT = (
    ROOT / "models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt"
)
REPLAY_DEFAULT = (
    ROOT
    / "experiments/动态分区试验/results/diagnosis_20261001_exactpages/"
    "mixed_scaled_exactpages/fixed/run_mix_replay/replay.jsonl"
)
WORKLOAD_DEFAULT = ROOT / "experiments/动态分区试验/data/mixed_scaled/workload.jsonl"
OUT_DEFAULT = ROOT / "experiments/动态分区试验/results/offline_global_efficiency_20261001"


def load_base_module():
    spec = importlib.util.spec_from_file_location("ratio_simulator", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(eq=False)
class SharedNode:
    region: str
    page: tuple[int, ...] | None = None
    parent: "SharedNode | None" = None
    children: dict[tuple[str, tuple[int, ...]], "SharedNode"] = field(default_factory=dict)
    depth: int = 0
    full_present: bool = True
    swa_present: bool = True
    full_last_access: int = 0
    swa_last_access: int = 0

    @property
    def is_leaf(self) -> bool:
        return not self.children


class GlobalCacheSimulator:
    """Page-level Full/SWA cache with optional cross-region coordination."""

    def __init__(
        self,
        *,
        full_capacity_tokens: int,
        swa_capacity_tokens: int,
        page_size: int,
        sliding_window_tokens: int,
        policy: str,
        agent_ratio: float,
        efficiency_window: int,
        protected_floor: bool,
    ) -> None:
        if policy not in {
            "shared_lru",
            "efficiency",
            "borrow",
            "tail_first",
            "request_tail_agent_lru",
        }:
            raise ValueError(f"unknown policy: {policy}")
        self.page_size = page_size
        self.sliding_window_tokens = sliding_window_tokens
        self.policy = policy
        self.protected_floor = protected_floor
        self.efficiency_window = max(int(efficiency_window), 1)
        self.full_capacity_pages = full_capacity_tokens // page_size
        self.swa_capacity_pages = swa_capacity_tokens // page_size
        self.floor_full_pages = {
            "agent": int(self.full_capacity_pages * agent_ratio),
            "request": self.full_capacity_pages
            - int(self.full_capacity_pages * agent_ratio),
        }
        self.floor_swa_pages = {
            "agent": int(self.swa_capacity_pages * agent_ratio),
            "request": self.swa_capacity_pages
            - int(self.swa_capacity_pages * agent_ratio),
        }
        self.root = SharedNode(region="root", page=None, parent=None)
        self.full_used_pages = 0
        self.swa_used_pages = 0
        self.full_used_by_region = defaultdict(int)
        self.swa_used_by_region = defaultdict(int)
        self.clock = 0
        self.request_count = 0
        self.window_hits_full = defaultdict(int)
        self.window_hits_swa = defaultdict(int)
        self.recent_hits_full = defaultdict(float)
        self.recent_hits_swa = defaultdict(float)
        self.full_evicted_pages = defaultdict(int)
        self.swa_evicted_pages = defaultdict(int)
        self.eviction_operations = 0
        self.policy_evictions = defaultdict(int)
        self.totals = {
            "agent": self._empty_totals(),
            "request": self._empty_totals(),
        }

    @staticmethod
    def _empty_totals() -> dict[str, int]:
        return {
            "requests": 0,
            "prompt_tokens": 0,
            "page_aligned_prompt_tokens": 0,
            "cached_prompt_tokens": 0,
            "recomputed_prompt_tokens": 0,
        }

    def _touch_full(self, node: SharedNode) -> None:
        self.clock += 1
        node.full_last_access = self.clock

    def _touch_swa(self, node: SharedNode) -> None:
        self.clock += 1
        node.swa_last_access = self.clock

    def _key(self, region: str, page: tuple[int, ...]) -> tuple[str, tuple[int, ...]]:
        return region, page

    def match(self, region: str, pages: tuple[tuple[int, ...], ...]) -> int:
        node = self.root
        best_pages = 0
        tokens_since_tombstone = 0
        saw_tombstone = False
        for depth, page in enumerate(pages, start=1):
            child = node.children.get(self._key(region, page))
            if child is None or not child.full_present:
                break
            node = child
            self._touch_full(node)
            if node.swa_present:
                self._touch_swa(node)
                tokens_since_tombstone += self.page_size
                if (
                    not saw_tombstone
                    or tokens_since_tombstone >= self.sliding_window_tokens
                ):
                    best_pages = depth
            else:
                saw_tombstone = True
                tokens_since_tombstone = 0
        hit_tokens = best_pages * self.page_size
        self.window_hits_full[region] += hit_tokens
        self.window_hits_swa[region] += hit_tokens
        return best_pages

    def insert(
        self,
        region: str,
        pages: tuple[tuple[int, ...], ...],
        matched_pages: int,
    ) -> None:
        node = self.root
        for depth, page in enumerate(pages, start=1):
            key = self._key(region, page)
            child = node.children.get(key)
            if child is None:
                child = SharedNode(
                    region=region,
                    page=page,
                    parent=node,
                    depth=node.depth + 1,
                )
                node.children[key] = child
                self.full_used_pages += 1
                self.swa_used_pages += 1
                self.full_used_by_region[region] += 1
                self.swa_used_by_region[region] += 1
            else:
                if not child.full_present:
                    child.full_present = True
                    self.full_used_pages += 1
                    self.full_used_by_region[region] += 1
                if not child.swa_present and depth > matched_pages:
                    child.swa_present = True
                    self.swa_used_pages += 1
                    self.swa_used_by_region[region] += 1
            node = child
            self._touch_full(node)
            if node.swa_present:
                self._touch_swa(node)
        self._enforce_capacity(region)

    def _iter_nodes(self):
        stack = list(self.root.children.values())
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children.values())

    def _full_candidates(self) -> list[SharedNode]:
        return [node for node in self._iter_nodes() if node.full_present and node.is_leaf]

    def _swa_candidates(self) -> list[SharedNode]:
        return [node for node in self._iter_nodes() if node.swa_present]

    def _region_efficiency(self, region: str, pool: str) -> float:
        if pool == "full":
            hits = self.recent_hits_full[region]
            used = self.full_used_by_region[region]
        else:
            hits = self.recent_hits_swa[region]
            used = self.swa_used_by_region[region]
        return hits / max(float(used * self.page_size), 1.0)

    def _eligible_regions(self, pool: str, candidates: list[SharedNode]) -> set[str]:
        regions = {node.region for node in candidates}
        if self.policy == "shared_lru":
            return regions
        if pool == "full":
            floors = self.floor_full_pages
            used = self.full_used_by_region
        else:
            floors = self.floor_swa_pages
            used = self.swa_used_by_region
        above_floor = {region for region in regions if used[region] > floors[region]}
        if self.policy in {"borrow", "request_tail_agent_lru"}:
            return above_floor or regions
        if self.protected_floor:
            return above_floor or regions
        return regions

    def _choose_victim(
        self,
        candidates: list[SharedNode],
        pool: str,
        pressure_region: str | None = None,
    ) -> SharedNode | None:
        if not candidates:
            return None
        eligible = self._eligible_regions(pool, candidates)
        candidates = [node for node in candidates if node.region in eligible]
        if self.policy in {"shared_lru", "borrow"}:
            return min(
                candidates,
                key=lambda node: (
                    node.full_last_access if pool == "full" else node.swa_last_access,
                    node.region,
                ),
            )
        if self.policy == "tail_first":
            # Preserve earlier shared ancestors by removing a deeper leaf or
            # tombstone first.  Ties fall back to LRU for determinism.
            return max(
                candidates,
                key=lambda node: (
                    node.depth,
                    -(
                        node.full_last_access
                        if pool == "full"
                        else node.swa_last_access
                    ),
                    node.region,
                ),
            )
        if self.policy == "request_tail_agent_lru":
            if pressure_region in eligible:
                candidates = [node for node in candidates if node.region == pressure_region]
            request_candidates = [node for node in candidates if node.region == "request"]
            if request_candidates:
                return max(
                    request_candidates,
                    key=lambda node: (
                        node.depth,
                        -(
                            node.full_last_access
                            if pool == "full"
                            else node.swa_last_access
                        ),
                    ),
                )
            return min(
                candidates,
                key=lambda node: (
                    node.full_last_access if pool == "full" else node.swa_last_access,
                    node.region,
                ),
            )
        # UniCache-style two-stage approximation: keep each region's oldest
        # local candidate, then compare its recent hit efficiency globally.
        local = {}
        for node in candidates:
            current = local.get(node.region)
            access = node.full_last_access if pool == "full" else node.swa_last_access
            if current is None or access < (
                current.full_last_access if pool == "full" else current.swa_last_access
            ):
                local[node.region] = node
        mean_eff = sum(self._region_efficiency(r, pool) for r in local) / max(len(local), 1)

        def score(node: SharedNode) -> tuple[float, int, str]:
            efficiency = self._region_efficiency(node.region, pool)
            alpha = efficiency / max(mean_eff, 1e-12) if mean_eff > 0 else efficiency
            access = node.full_last_access if pool == "full" else node.swa_last_access
            # A newer local candidate has higher survival score.  The lowest
            # global score is the victim, matching G_q = alpha_q * s_q.
            survival = access / max(self.clock, 1)
            return alpha * survival, access, node.region

        return min(local.values(), key=score)

    def _remove_leaf(self, node: SharedNode) -> None:
        if node.parent is None or not node.is_leaf:
            raise RuntimeError("only a non-root leaf can be removed")
        node.parent.children.pop(self._key(node.region, node.page), None)
        if node.full_present:
            self.full_used_pages -= 1
            self.full_used_by_region[node.region] -= 1
            self.full_evicted_pages[node.region] += 1
            node.full_present = False
        if node.swa_present:
            self.swa_used_pages -= 1
            self.swa_used_by_region[node.region] -= 1
            self.swa_evicted_pages[node.region] += 1
            node.swa_present = False

    def _delete_tombstone_ancestors(self, start: SharedNode | None) -> None:
        node = start
        while (
            node is not None
            and node.parent is not None
            and node.is_leaf
            and not node.swa_present
            and not node.full_present
        ):
            parent = node.parent
            parent.children.pop(self._key(node.region, node.page), None)
            node = parent

    def _evict_full_once(self, pressure_region: str | None = None) -> bool:
        victim = self._choose_victim(
            self._full_candidates(), "full", pressure_region
        )
        if victim is None:
            return False
        parent = victim.parent
        region = victim.region
        self._remove_leaf(victim)
        self._delete_tombstone_ancestors(parent)
        self.eviction_operations += 1
        self.policy_evictions[f"full:{region}"] += 1
        return True

    def _evict_swa_once(self, pressure_region: str | None = None) -> bool:
        victim = self._choose_victim(
            self._swa_candidates(), "swa", pressure_region
        )
        if victim is None:
            return False
        region = victim.region
        if victim.is_leaf:
            parent = victim.parent
            self._remove_leaf(victim)
            self._delete_tombstone_ancestors(parent)
        else:
            victim.swa_present = False
            self.swa_used_pages -= 1
            self.swa_used_by_region[region] -= 1
            self.swa_evicted_pages[region] += 1
        self.eviction_operations += 1
        self.policy_evictions[f"swa:{region}"] += 1
        return True

    def _enforce_capacity(self, pressure_region: str | None = None) -> None:
        while self.full_used_pages > self.full_capacity_pages:
            if not self._evict_full_once(pressure_region):
                break
        while self.swa_used_pages > self.swa_capacity_pages:
            if not self._evict_swa_once(pressure_region):
                break

    def _advance_efficiency_window(self) -> None:
        if self.request_count % self.efficiency_window:
            return
        for region in ("agent", "request"):
            self.recent_hits_full[region] = 0.5 * self.recent_hits_full[region] + self.window_hits_full[region]
            self.recent_hits_swa[region] = 0.5 * self.recent_hits_swa[region] + self.window_hits_swa[region]
            self.window_hits_full[region] = 0
            self.window_hits_swa[region] = 0

    def process(self, request: Any) -> None:
        region = request.region
        matched_pages = self.match(region, request.prompt_pages)
        cached_tokens = matched_pages * self.page_size
        aligned_prompt_tokens = len(request.prompt_pages) * self.page_size
        totals = self.totals[region]
        totals["requests"] += 1
        totals["prompt_tokens"] += request.prompt_tokens
        totals["page_aligned_prompt_tokens"] += aligned_prompt_tokens
        totals["cached_prompt_tokens"] += cached_tokens
        totals["recomputed_prompt_tokens"] += aligned_prompt_tokens - cached_tokens
        self.insert(region, request.stored_pages, matched_pages)
        self.request_count += 1
        self._advance_efficiency_window()

    def result(self, *, full_capacity_tokens: int, swa_capacity_tokens: int) -> dict[str, Any]:
        overall = {
            key: sum(self.totals[r][key] for r in self.totals)
            for key in (
                "requests",
                "prompt_tokens",
                "page_aligned_prompt_tokens",
                "cached_prompt_tokens",
                "recomputed_prompt_tokens",
            )
        }
        for block in self.totals.values():
            denominator = block["page_aligned_prompt_tokens"]
            block["page_aligned_hit_ratio"] = block["cached_prompt_tokens"] / denominator if denominator else 0.0
        overall["page_aligned_hit_ratio"] = (
            overall["cached_prompt_tokens"] / overall["page_aligned_prompt_tokens"]
            if overall["page_aligned_prompt_tokens"]
            else 0.0
        )
        regions = {}
        for region, block in self.totals.items():
            regions[region] = {
                **block,
                "full_capacity_tokens": full_capacity_tokens,
                "swa_capacity_tokens": swa_capacity_tokens,
                "final_full_used_tokens": self.full_used_by_region[region] * self.page_size,
                "final_swa_used_tokens": self.swa_used_by_region[region] * self.page_size,
                "full_evicted_tokens": self.full_evicted_pages[region] * self.page_size,
                "swa_evicted_tokens": self.swa_evicted_pages[region] * self.page_size,
                "full_efficiency": self._region_efficiency(region, "full"),
                "swa_efficiency": self._region_efficiency(region, "swa"),
            }
        return {
            "policy": self.policy,
            "protected_floor": self.protected_floor,
            "efficiency_window": self.efficiency_window,
            "overall": overall,
            "regions": regions,
            "full_evicted_tokens": sum(self.full_evicted_pages.values()) * self.page_size,
            "swa_evicted_tokens": sum(self.swa_evicted_pages.values()) * self.page_size,
            "eviction_operations": self.eviction_operations,
            "policy_evictions": dict(self.policy_evictions),
            "final_full_used_tokens": self.full_used_pages * self.page_size,
            "final_swa_used_tokens": self.swa_used_pages * self.page_size,
        }


def run_shared(
    trace,
    args,
    *,
    policy: str,
    protected_floor: bool,
    display_name: str | None = None,
) -> dict[str, Any]:
    simulator = GlobalCacheSimulator(
        full_capacity_tokens=args.full_capacity_tokens,
        swa_capacity_tokens=args.swa_capacity_tokens,
        page_size=args.page_size,
        sliding_window_tokens=args.sliding_window_tokens,
        policy=policy,
        agent_ratio=args.agent_ratio,
        efficiency_window=args.efficiency_window,
        protected_floor=protected_floor,
    )
    for request in trace:
        simulator.process(request)
    result = simulator.result(
        full_capacity_tokens=args.full_capacity_tokens,
        swa_capacity_tokens=args.swa_capacity_tokens,
    )
    if display_name is not None:
        result["policy"] = display_name
    return result


def run_fixed(base, trace, args) -> dict[str, Any]:
    result = base.simulate_ratio(
        trace,
        ratio=args.agent_ratio,
        full_capacity_tokens=args.full_capacity_tokens,
        swa_capacity_tokens=args.swa_capacity_tokens,
        page_size=args.page_size,
        sliding_window_tokens=args.sliding_window_tokens,
    )
    result["policy"] = "fixed_region_lru"
    return result


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy": result["policy"],
        "overall_hit": result["overall"]["page_aligned_hit_ratio"],
        "cached_tokens": result["overall"]["cached_prompt_tokens"],
        "recomputed_tokens": result["overall"]["recomputed_prompt_tokens"],
        "agent_hit": result["regions"]["agent"]["page_aligned_hit_ratio"],
        "request_hit": result["regions"]["request"]["page_aligned_hit_ratio"],
        "full_evicted_tokens": result.get("full_evicted_tokens", result.get("total_full_evicted_tokens")),
        "swa_evicted_tokens": result.get("swa_evicted_tokens", result.get("total_swa_evicted_tokens")),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, default=MODEL_DEFAULT)
    parser.add_argument("--classifier-checkpoint", type=Path, default=CLASSIFIER_DEFAULT)
    parser.add_argument("--workload", type=Path, default=WORKLOAD_DEFAULT)
    parser.add_argument("--completion-replay", type=Path, default=REPLAY_DEFAULT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--full-capacity-tokens", type=int, default=705280)
    parser.add_argument("--swa-capacity-tokens", type=int, default=70400)
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--sliding-window-tokens", type=int, default=128)
    parser.add_argument("--agent-ratio", type=float, default=0.61)
    parser.add_argument("--efficiency-window", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.model_path, args.classifier_checkpoint, args.workload, args.completion_replay):
        if not path.exists():
            raise SystemExit(f"missing input: {path}")
    base = load_base_module()
    from transformers import AutoTokenizer

    print(f"[tokenizer] loading {args.model_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True, local_files_only=True)
    classifier = base.RequestRegionClassifier.load(args.classifier_checkpoint, threshold=0.5)
    workload_rows = base.read_jsonl(args.workload)
    completion_rows = base.read_jsonl(args.completion_replay)
    trace, calibration = base.build_trace(
        workload_rows, completion_rows, tokenizer, classifier, args.page_size
    )
    print(
        f"[trace] requests={len(trace)} agent={sum(r.region == 'agent' for r in trace)} "
        f"request={sum(r.region == 'request' for r in trace)}",
        flush=True,
    )
    results = {
        "fixed_region_lru": run_fixed(base, trace, args),
        "shared_lru": run_shared(
            trace, args, policy="shared_lru", protected_floor=False, display_name="shared_lru"
        ),
        "global_efficiency": run_shared(
            trace, args, policy="efficiency", protected_floor=False, display_name="global_efficiency"
        ),
        "global_efficiency_floor": run_shared(
            trace,
            args,
            policy="efficiency",
            protected_floor=True,
            display_name="global_efficiency_floor",
        ),
        "borrow_lru": run_shared(
            trace, args, policy="borrow", protected_floor=True, display_name="borrow_lru"
        ),
        "tail_first_floor": run_shared(
            trace,
            args,
            policy="tail_first",
            protected_floor=True,
            display_name="tail_first_floor",
        ),
        "tail_first_shared": run_shared(
            trace,
            args,
            policy="tail_first",
            protected_floor=False,
            display_name="tail_first_shared",
        ),
        "request_tail_agent_lru": run_shared(
            trace,
            args,
            policy="request_tail_agent_lru",
            protected_floor=True,
            display_name="request_tail_agent_lru",
        ),
    }
    summary = [normalize_result(result) for result in results.values()]
    args.out_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema": "agentkv_global_efficiency_offline_v1",
        "configuration": {
            "workload": str(args.workload.resolve()),
            "completion_replay": str(args.completion_replay.resolve()),
            "model_path": str(args.model_path.resolve()),
            "classifier_checkpoint": str(args.classifier_checkpoint.resolve()),
            "full_capacity_tokens": args.full_capacity_tokens,
            "swa_capacity_tokens": args.swa_capacity_tokens,
            "page_size": args.page_size,
            "sliding_window_tokens": args.sliding_window_tokens,
            "agent_ratio": args.agent_ratio,
            "efficiency_window": args.efficiency_window,
        },
        "trace": {"requests": len(trace), "calibration": calibration},
        "results": results,
        "summary": summary,
        "limitations": [
            "Page-level approximation; no request locks or concurrent admission.",
            "Output token IDs are synthetic and do not assert generated-text reuse.",
            "Efficiency uses recent hit tokens per resident page, while the paper uses queue capacity fractions.",
            "This is a mechanism screen; GPU serving must validate the selected candidate later.",
        ],
    }
    (args.out_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Global efficiency offline experiment",
        "",
        f"Trace: `{args.workload}`; requests: {len(trace)}; page size: {args.page_size}",
        "",
        "| policy | overall hit | Agent hit | request hit | cached tokens | Full evicted | SWA evicted |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['policy']} | {row['overall_hit']:.4%} | {row['agent_hit']:.4%} | "
            f"{row['request_hit']:.4%} | {row['cached_tokens']:,} | "
            f"{row['full_evicted_tokens']:,} | {row['swa_evicted_tokens']:,} |"
        )
    lines.extend(["", "## Relative to fixed region LRU", ""])
    baseline = summary[0]
    for row in summary[1:]:
        lines.append(
            f"- `{row['policy']}`: overall {100 * (row['overall_hit'] - baseline['overall_hit']):+.4f} pp; "
            f"Agent {100 * (row['agent_hit'] - baseline['agent_hit']):+.4f} pp; "
            f"request {100 * (row['request_hit'] - baseline['request_hit']):+.4f} pp; "
            f"cached {row['cached_tokens'] - baseline['cached_tokens']:+,} tokens."
        )
    (args.out_dir / "results.md").write_text("\n".join(lines) + "\n")
    print("[results]", args.out_dir / "results.md", flush=True)
    for row in summary:
        print(
            f"[summary] {row['policy']} hit={row['overall_hit']:.4%} "
            f"agent={row['agent_hit']:.4%} request={row['request_hit']:.4%}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
