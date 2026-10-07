#!/usr/bin/env python3
"""Compare runtime cache hits with an infinite input-prefix shadow index.

The runtime reports how many prompt tokens were cached, but that value alone
does not say whether a miss was caused by eviction.  This tool rebuilds the
same page-aligned prompt tokens from the frozen workload and keeps every
previous input prefix in an unbounded radix trie.  For request ``r`` it
records::

    extra_recompute_r = max(0, h_inf_r - h_actual_r)

where ``h_inf`` is the longest page-aligned prefix that had appeared in an
earlier completed request and ``h_actual`` is the runtime ``cached_tokens``.
The shadow is deliberately input-only: generated output token ids are not
available in the ordinary mixed replay logs.  A coverage gap is reported when
the runtime hit exceeds the input-only shadow, which makes that limitation
visible instead of silently treating the shadow as exact.

The completion order in ``replay.jsonl`` is used as the insertion order.  The
session replay writes a row after its response completes, so this is the
closest observable order to finished-request insertion without adding a
runtime instrumentation patch.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
BASE_SCRIPT = ROOT / "experiments/固定分区试验对比/scripts/select_agent_cache_capacity_ratio.py"
DEFAULT_MODEL = Path(
    "/mnt/public/dai-sys/.cache/hub/hub/models--deepseek-ai--DeepSeek-V4-Flash/"
    "snapshots/fd53f944496234770ba80e15004f9b6d269a71f5"
)
AGENT_LIKE = {"agent", "openhands", "glm"}


def load_base_module():
    spec = importlib.util.spec_from_file_location("agentkv_ratio_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PrefixTrie:
    """Unbounded page-prefix trie; no region quota or eviction is applied."""

    __slots__ = ("children", "terminal")

    def __init__(self) -> None:
        self.children: dict[tuple[int, ...], PrefixTrie] = {}
        self.terminal = False

    def match_pages(self, pages: tuple[tuple[int, ...], ...]) -> int:
        node = self
        matched = 0
        for page in pages:
            child = node.children.get(page)
            if child is None:
                break
            matched += 1
            node = child
        return matched

    def insert_pages(self, pages: tuple[tuple[int, ...], ...]) -> None:
        node = self
        for page in pages:
            node = node.children.setdefault(page, PrefixTrie())
        node.terminal = True


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def workload_index(workload_path: Path, tokenizer: Any, base: Any, page_size: int):
    rows = load_jsonl(workload_path)
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["session_id"]), int(row["turn_idx"]))
        if key in result:
            raise ValueError(f"duplicate workload key: {key}")
        token_ids = base.encode_prompt(tokenizer, dict(row["prompt_body"]))
        pages = base.page_chunks(token_ids, page_size)
        result[key] = {
            "traffic_class": str(row["traffic_class"]),
            "session_id": key[0],
            "turn_index": key[1],
            "token_ids": token_ids,
            "pages": pages,
            "encoded_prompt_tokens": len(token_ids),
        }
    return result


def order_replay(rows: list[dict[str, Any]], order: str) -> list[dict[str, Any]]:
    if order == "file":
        return rows
    if order == "start":
        return sorted(rows, key=lambda row: (float(row.get("s_time_ms") or 0.0), int(row.get("index", 0))))
    if order == "end":
        return sorted(rows, key=lambda row: (float(row.get("e_time_ms") or 0.0), int(row.get("index", 0))))
    raise ValueError(f"unknown order: {order}")


def empty_group() -> dict[str, Any]:
    return {
        "requests": 0,
        "prompt_tokens": 0,
        "page_aligned_prompt_tokens": 0,
        "shadow_cached_tokens": 0,
        "runtime_cached_tokens": 0,
        "extra_recompute_tokens": 0,
        "coverage_gap_tokens": 0,
        "requests_with_extra_recompute": 0,
        "requests_with_runtime_hit": 0,
        "requests_with_shadow_hit": 0,
        "encoded_prompt_mismatch_requests": 0,
        "encoded_prompt_delta_tokens": 0,
    }


def add_group(group: dict[str, Any], item: dict[str, Any]) -> None:
    group["requests"] += 1
    group["prompt_tokens"] += item["prompt_tokens"]
    group["page_aligned_prompt_tokens"] += item["page_aligned_prompt_tokens"]
    group["shadow_cached_tokens"] += item["shadow_cached_tokens"]
    group["runtime_cached_tokens"] += item["runtime_cached_tokens"]
    group["extra_recompute_tokens"] += item["extra_recompute_tokens"]
    group["coverage_gap_tokens"] += item["coverage_gap_tokens"]
    group["requests_with_extra_recompute"] += int(item["extra_recompute_tokens"] > 0)
    group["requests_with_runtime_hit"] += int(item["runtime_cached_tokens"] > 0)
    group["requests_with_shadow_hit"] += int(item["shadow_cached_tokens"] > 0)
    group["encoded_prompt_mismatch_requests"] += int(item["encoded_prompt_mismatch"])
    group["encoded_prompt_delta_tokens"] += item["encoded_prompt_delta_tokens"]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    aligned = group["page_aligned_prompt_tokens"]
    prompt = group["prompt_tokens"]
    shadow = group["shadow_cached_tokens"]
    runtime = group["runtime_cached_tokens"]
    h_inf = shadow / aligned if aligned else 0.0
    actual = runtime / prompt if prompt else 0.0
    group.update(
        {
            "shadow_hit_ratio_page_aligned": h_inf,
            "runtime_hit_ratio_prompt": actual,
            "extra_recompute_ratio_of_shadow": (
                group["extra_recompute_tokens"] / shadow if shadow else 0.0
            ),
            "extra_recompute_ratio_of_prompt": (
                group["extra_recompute_tokens"] / prompt if prompt else 0.0
            ),
            "coverage_gap_ratio_of_prompt": (
                group["coverage_gap_tokens"] / prompt if prompt else 0.0
            ),
        }
    )
    return group


def analyze_case(
    workload_path: Path,
    replay_path: Path,
    tokenizer: Any,
    base: Any,
    page_size: int,
    order: str,
) -> dict[str, Any]:
    index = workload_index(workload_path, tokenizer, base, page_size)
    replay_rows = [
        row
        for row in load_jsonl(replay_path)
        if row.get("status") == "200" and not row.get("error")
    ]
    replay_rows = order_replay(replay_rows, order)
    if not replay_rows:
        raise ValueError(f"no successful requests in {replay_path}")
    trie = PrefixTrie()
    rows: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = defaultdict(empty_group)
    missing = []
    encoded_lengths: list[int] = []
    actual_lengths: list[int] = []
    for shadow_seq, runtime in enumerate(replay_rows, start=1):
        key = (str(runtime["session_id"]), int(runtime.get("turn_index", runtime.get("turn_idx", -1))))
        source = index.get(key)
        if source is None:
            missing.append({"session_id": key[0], "turn_index": key[1], "index": runtime.get("index")})
            continue
        pages = source["pages"]
        shadow_pages = trie.match_pages(pages)
        shadow_cached = shadow_pages * page_size
        prompt_tokens = int(runtime.get("prompt_tokens") or 0)
        runtime_cached = max(0, int(runtime.get("cached_tokens") or 0))
        encoded_tokens = int(source["encoded_prompt_tokens"])
        encoded_delta = encoded_tokens - prompt_tokens
        encoded_lengths.append(encoded_tokens)
        actual_lengths.append(prompt_tokens)
        aligned_prompt = (prompt_tokens // page_size) * page_size
        shadow_cached = min(shadow_cached, (encoded_tokens // page_size) * page_size)
        extra = max(0, shadow_cached - runtime_cached)
        gap = max(0, runtime_cached - shadow_cached)
        item = {
            "shadow_sequence": shadow_seq,
            "runtime_index": runtime.get("index"),
            "session_id": key[0],
            "turn_index": key[1],
            "traffic_class": source["traffic_class"],
            "region_group": "agent" if source["traffic_class"] in AGENT_LIKE else "request",
            "prompt_tokens": prompt_tokens,
            "encoded_prompt_tokens": encoded_tokens,
            "encoded_prompt_delta_tokens": encoded_delta,
            "encoded_prompt_mismatch": encoded_delta != 0,
            "page_aligned_prompt_tokens": aligned_prompt,
            "shadow_cached_tokens": shadow_cached,
            "runtime_cached_tokens": runtime_cached,
            "extra_recompute_tokens": extra,
            "coverage_gap_tokens": gap,
            "runtime_hit_ratio": runtime_cached / prompt_tokens if prompt_tokens else 0.0,
            "shadow_hit_ratio": shadow_cached / aligned_prompt if aligned_prompt else 0.0,
            "s_time_ms": runtime.get("s_time_ms"),
            "e_time_ms": runtime.get("e_time_ms"),
        }
        rows.append(item)
        add_group(groups["all"], item)
        add_group(groups[item["region_group"]], item)
        turn_group = "first_turn" if key[1] == 0 else "within_session"
        add_group(groups[turn_group], item)
        add_group(groups[f"{item['region_group']}_{turn_group}"], item)
        trie.insert_pages(pages)
    for group in groups.values():
        finalize_group(group)
    return {
        "schema": "agentkv_shadow_recompute_v1",
        "workload": str(workload_path.resolve()),
        "replay": str(replay_path.resolve()),
        "page_size": page_size,
        "shadow_order": order,
        "shadow_definition": (
            "Unbounded trie of prior page-aligned input prompts, same token encoding; "
            "generated completion ids are unavailable in mixed replay logs."
        ),
        "requests_in_replay": len(replay_rows),
        "requests_analyzed": len(rows),
        "missing_workload_rows": missing,
        "encoded_prompt_mismatch_count": sum(item["encoded_prompt_mismatch"] for item in rows),
        "encoded_prompt_delta_min": min((item["encoded_prompt_delta_tokens"] for item in rows), default=0),
        "encoded_prompt_delta_max": max((item["encoded_prompt_delta_tokens"] for item in rows), default=0),
        "encoded_prompt_delta_mean": statistics.fmean(encoded_lengths[i] - actual_lengths[i] for i in range(len(rows))) if rows else 0.0,
        "groups": dict(groups),
        "requests": rows,
    }


def discover_cases(run_root: Path, workload_dir: Path | None) -> tuple[Path, dict[str, Path]]:
    config_path = run_root / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text())
        configured_workload = Path(config["workload_dir"])
        if workload_dir is None:
            workload_dir = configured_workload
        cases = {}
        for mode in config.get("modes", []):
            replay = run_root / mode / "run_mix_replay/replay.jsonl"
            if replay.is_file():
                cases[mode] = replay
        return workload_dir.resolve(), cases
    if workload_dir is None:
        raise ValueError("run root must contain config.json or --workload-dir is required")
    cases = {
        path.parent.parent.name: path
        for path in run_root.glob("*/run_mix_replay/replay.jsonl")
    }
    return workload_dir.resolve(), cases


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Shadow 额外重算分析",
        "",
        f"- workload: `{payload['workload']}`",
        f"- page_size: `{payload['page_size']}`",
        f"- shadow order: `{payload['shadow_order']}`（按 replay.jsonl 完成/写入顺序）",
        "- shadow 只保存历史输入前缀；混合回放没有输出 token id，因此 coverage gap 用于标记该限制。",
        "",
    ]
    for name, case in payload["cases"].items():
        lines.extend([f"## {name}", ""])
        lines.append(
            f"请求 {case['requests_analyzed']}/{case['requests_in_replay']}，"
            f"编码长度不一致 {case['encoded_prompt_mismatch_count']} 条；"
            f"缺少 workload 行 {len(case['missing_workload_rows'])} 条。"
        )
        lines.extend(
            [
                "",
                "| 分组 | 请求数 | shadow h_inf token | 实际 cached token | 额外重算 token | shadow 命中率 | 实际命中率 | coverage gap |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for group in ("all", "agent", "request", "first_turn", "within_session"):
            item = case["groups"].get(group)
            if item is None:
                continue
            lines.append(
                f"| {group} | {item['requests']} | {item['shadow_cached_tokens']:,} | "
                f"{item['runtime_cached_tokens']:,} | {item['extra_recompute_tokens']:,} | "
                f"{item['shadow_hit_ratio_page_aligned']:.4%} | "
                f"{item['runtime_hit_ratio_prompt']:.4%} | {item['coverage_gap_tokens']:,} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--workload-dir", type=Path)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--order", choices=("file", "start", "end"), default="file")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    workload_dir, cases = discover_cases(run_root, args.workload_dir)
    workload_path = workload_dir / "workload.jsonl"
    if not workload_path.is_file():
        raise SystemExit(f"missing workload: {workload_path}")
    if not cases:
        raise SystemExit(f"no replay.jsonl cases under {run_root}")
    if not args.model_path.is_dir():
        raise SystemExit(f"missing model directory: {args.model_path}")
    base = load_base_module()
    from transformers import AutoTokenizer

    print(f"[tokenizer] loading {args.model_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True, local_files_only=True)
    payload = {
        "schema": "agentkv_shadow_recompute_suite_v1",
        "workload": str(workload_path.resolve()),
        "page_size": args.page_size,
        "shadow_order": args.order,
        "cases": {},
    }
    for name, replay_path in sorted(cases.items()):
        print(f"[case] {name}: {replay_path}", flush=True)
        payload["cases"][name] = analyze_case(
            workload_path, replay_path, tokenizer, base, args.page_size, args.order
        )
        all_group = payload["cases"][name]["groups"]["all"]
        print(
            f"[summary] {name} requests={all_group['requests']} "
            f"shadow={all_group['shadow_cached_tokens']:,} "
            f"runtime={all_group['runtime_cached_tokens']:,} "
            f"extra={all_group['extra_recompute_tokens']:,}",
            flush=True,
        )
    output = (args.output or (run_root / "shadow_recompute.json")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    report_path = output.with_suffix(".md")
    report_path.write_text(render_report(payload))
    print(f"[results] {output}")
    print(f"[report] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
