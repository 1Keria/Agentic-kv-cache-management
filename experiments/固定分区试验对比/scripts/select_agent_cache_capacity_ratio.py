#!/usr/bin/env python3
"""Select the fixed Agent KV-cache capacity ratio for the frozen workload.

The simulator uses the DeepSeek-V4 chat encoder, page-aligned token prefixes,
the historical completion lengths from the source replay, and a page-level
approximation of SGLang's Full/SWA radix LRU behavior. The selected ratio is an
offline starting point; the paired GPU replay remains the acceptance result.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
SGLANG_PYTHON = REPO_ROOT / "Engine/sglang/python"
sys.path.insert(0, str(SGLANG_PYTHON))

from sglang.srt.entrypoints.openai import encoding_dsv4  # noqa: E402
from sglang.srt.mem_cache.request_region import RequestRegionClassifier  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

DEFAULT_MODEL = Path(
    "/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash"
)
DEFAULT_WORKLOAD_DIR = (
    REPO_ROOT / "experiments/固定分区试验对比/data/token_balanced_openhands_wildchat"
)
DEFAULT_COMPLETION_REPLAY = (
    REPO_ROOT / "experiments/sglang_kv_cache/ratio_daily_models/agent_050/replay/"
    "run_mix_train_lru/replay.jsonl"
)
DEFAULT_OUT_DIR = REPO_ROOT / "experiments/固定分区试验对比/results"
DEFAULT_CLASSIFIER = (
    REPO_ROOT
    / "models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt"
)
AGENT_LIKE = {"agent", "openhands", "glm"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def api_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.get("role") or "user"}
        if "content" in message:
            item["content"] = message.get("content")
        if message.get("tool_calls"):
            item["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            item["tool_call_id"] = message["tool_call_id"]
        if message.get("name"):
            item["name"] = message["name"]
        if message.get("reasoning_content"):
            item["reasoning_content"] = message["reasoning_content"]
        output.append(item)
    return output


def encode_prompt(
    tokenizer: Any,
    prompt_body: dict[str, Any],
) -> list[int]:
    messages = copy.deepcopy(api_messages(list(prompt_body.get("messages") or [])))
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": ""})
    tools = prompt_body.get("tools") or []
    if tools:
        messages[0]["tools"] = copy.deepcopy(tools)
    rendered = encoding_dsv4.encode_messages(messages, thinking_mode="chat")
    return list(tokenizer.encode(rendered))


def page_chunks(token_ids: list[int], page_size: int) -> tuple[tuple[int, ...], ...]:
    aligned = len(token_ids) // page_size * page_size
    return tuple(
        tuple(token_ids[start : start + page_size])
        for start in range(0, aligned, page_size)
    )


@dataclass
class EncodedRequest:
    region: str
    traffic_class: str
    session_id: str
    turn_idx: int
    scheduled_time_s: float
    prompt_tokens: int
    completion_tokens: int
    prompt_pages: tuple[tuple[int, ...], ...]
    stored_pages: tuple[tuple[int, ...], ...]


@dataclass(eq=False)
class CacheNode:
    page: tuple[int, ...] | None = None
    parent: CacheNode | None = None
    children: dict[tuple[int, ...], CacheNode] = field(default_factory=dict)
    full_present: bool = True
    swa_present: bool = True
    full_last_access: int = 0
    swa_last_access: int = 0

    @property
    def is_leaf(self) -> bool:
        return not self.children


class HybridRadixSimulator:
    def __init__(
        self,
        *,
        full_capacity_tokens: int,
        swa_capacity_tokens: int,
        page_size: int,
        sliding_window_tokens: int,
    ) -> None:
        self.page_size = page_size
        self.sliding_window_tokens = sliding_window_tokens
        self.full_capacity_pages = full_capacity_tokens // page_size
        self.swa_capacity_pages = swa_capacity_tokens // page_size
        self.root = CacheNode(page=None, parent=None)
        self.full_used_pages = 0
        self.swa_used_pages = 0
        self.clock = 0
        self.full_evicted_pages = 0
        self.swa_evicted_pages = 0
        self.eviction_operations = 0
        self.peak_full_used_pages = 0
        self.peak_swa_used_pages = 0

    def _touch_full(self, node: CacheNode) -> None:
        self.clock += 1
        node.full_last_access = self.clock

    def _touch_swa(self, node: CacheNode) -> None:
        self.clock += 1
        node.swa_last_access = self.clock

    def match(self, pages: tuple[tuple[int, ...], ...]) -> int:
        node = self.root
        best_pages = 0
        tokens_since_tombstone = 0
        saw_tombstone = False
        for depth, page in enumerate(pages, start=1):
            child = node.children.get(page)
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
        return best_pages

    def insert(
        self,
        pages: tuple[tuple[int, ...], ...],
        matched_pages: int,
    ) -> None:
        node = self.root
        for depth, page in enumerate(pages, start=1):
            child = node.children.get(page)
            if child is None:
                child = CacheNode(page=page, parent=node)
                node.children[page] = child
                self.full_used_pages += 1
                self.swa_used_pages += 1
            elif not child.swa_present and depth > matched_pages:
                child.swa_present = True
                self.swa_used_pages += 1
            node = child
            self._touch_full(node)
            if node.swa_present:
                self._touch_swa(node)
        self.peak_full_used_pages = max(self.peak_full_used_pages, self.full_used_pages)
        self.peak_swa_used_pages = max(self.peak_swa_used_pages, self.swa_used_pages)
        self.enforce_capacity()

    def _full_victim(self) -> CacheNode | None:
        candidates: list[CacheNode] = []
        stack = list(self.root.children.values())
        while stack:
            node = stack.pop()
            if node.is_leaf and node.full_present:
                candidates.append(node)
            stack.extend(node.children.values())
        return min(candidates, key=lambda item: item.full_last_access, default=None)

    def _swa_victim(self) -> CacheNode | None:
        candidates: list[CacheNode] = []
        stack = list(self.root.children.values())
        while stack:
            node = stack.pop()
            if node.swa_present:
                candidates.append(node)
            stack.extend(node.children.values())
        return min(candidates, key=lambda item: item.swa_last_access, default=None)

    def _remove_leaf(self, node: CacheNode) -> None:
        if node.parent is None or not node.is_leaf:
            raise RuntimeError("only a non-root leaf can be removed")
        node.parent.children.pop(node.page, None)
        if node.full_present:
            self.full_used_pages -= 1
            self.full_evicted_pages += 1
        if node.swa_present:
            self.swa_used_pages -= 1
            self.swa_evicted_pages += 1

    def _delete_tombstone_ancestors(self, start: CacheNode | None) -> None:
        node = start
        while (
            node is not None
            and node.parent is not None
            and node.is_leaf
            and not node.swa_present
        ):
            parent = node.parent
            self._remove_leaf(node)
            node = parent

    def _evict_full_once(self) -> bool:
        victim = self._full_victim()
        if victim is None:
            return False
        parent = victim.parent
        self._remove_leaf(victim)
        self._delete_tombstone_ancestors(parent)
        self.eviction_operations += 1
        return True

    def _evict_swa_once(self) -> bool:
        victim = self._swa_victim()
        if victim is None:
            return False
        if victim.is_leaf:
            parent = victim.parent
            self._remove_leaf(victim)
            self._delete_tombstone_ancestors(parent)
        else:
            victim.swa_present = False
            self.swa_used_pages -= 1
            self.swa_evicted_pages += 1
        self.eviction_operations += 1
        return True

    def enforce_capacity(self) -> None:
        while self.full_used_pages > self.full_capacity_pages:
            if not self._evict_full_once():
                break
        while self.swa_used_pages > self.swa_capacity_pages:
            if not self._evict_swa_once():
                break


def build_trace(
    workload_rows: list[dict[str, Any]],
    completion_rows: list[dict[str, Any]],
    tokenizer: Any,
    classifier: RequestRegionClassifier,
    page_size: int,
) -> tuple[list[EncodedRequest], dict[str, Any]]:
    completion_by_turn = {
        (str(row["session_id"]), int(row["turn_index"])): int(
            row.get("completion_tokens") or 0
        )
        for row in completion_rows
        if row.get("status") == "200" and not row.get("error")
    }
    elapsed_by_session: dict[str, float] = defaultdict(float)
    trace: list[EncodedRequest] = []
    prompt_deltas: list[int] = []
    historical_prompt_by_turn = {
        (str(row["session_id"]), int(row["turn_index"])): int(
            row.get("prompt_tokens") or 0
        )
        for row in completion_rows
        if row.get("status") == "200" and not row.get("error")
    }
    max_tokens_by_turn = {
        (str(row["session_id"]), int(row["turn_idx"])): max(int(row["max_tokens"]), 0)
        for row in workload_rows
    }
    service_time_by_turn: dict[tuple[str, int], float] = {}
    for row in completion_rows:
        if row.get("status") != "200" or row.get("error"):
            continue
        key = (str(row["session_id"]), int(row["turn_index"]))
        if key not in max_tokens_by_turn:
            continue
        historical_completion = max(int(row.get("completion_tokens") or 0), 0)
        historical_ttft_ms = max(float(row.get("ttft_ms") or 0.0), 0.0)
        historical_e2e_ms = max(
            float(row.get("e2e_ms") or historical_ttft_ms), historical_ttft_ms
        )
        capped_completion = min(
            historical_completion,
            max_tokens_by_turn[key],
        )
        decode_ms = historical_e2e_ms - historical_ttft_ms
        completion_scale = (
            capped_completion / historical_completion if historical_completion else 0.0
        )
        service_time_by_turn[key] = (
            historical_ttft_ms + decode_ms * completion_scale
        ) / 1000.0
    next_synthetic_id = -1
    confusion = {
        "agent_as_agent": 0,
        "agent_as_request": 0,
        "request_as_agent": 0,
        "request_as_request": 0,
    }
    for row in workload_rows:
        session_id = str(row["session_id"])
        turn_idx = int(row["turn_idx"])
        key = (session_id, turn_idx)
        if key not in completion_by_turn:
            raise ValueError(
                f"missing historical completion length for {session_id}#{turn_idx}"
            )
        prompt_ids = encode_prompt(tokenizer, dict(row["prompt_body"]))
        historical_prompt = historical_prompt_by_turn.get(key)
        if historical_prompt is not None:
            prompt_deltas.append(len(prompt_ids) - historical_prompt)
        completion_tokens = min(
            max(completion_by_turn[key], 0),
            max(int(row["max_tokens"]), 0),
        )
        synthetic_completion = list(
            range(next_synthetic_id - completion_tokens + 1, next_synthetic_id + 1)
        )
        next_synthetic_id -= completion_tokens + 1
        prompt_pages = page_chunks(prompt_ids, page_size)
        stored_pages = page_chunks(prompt_ids + synthetic_completion, page_size)
        if turn_idx > 0:
            previous_key = (session_id, turn_idx - 1)
            if previous_key not in service_time_by_turn:
                raise ValueError(
                    f"missing historical service time for {session_id}#{turn_idx - 1}"
                )
            elapsed_by_session[session_id] += service_time_by_turn[previous_key]
        elapsed_by_session[session_id] += float(row.get("pre_gap_s") or 0.0)
        scheduled_time_s = (
            float(row["session_start_s"]) + elapsed_by_session[session_id]
        )
        traffic_class = str(row["traffic_class"])
        expected_region = "agent" if traffic_class in AGENT_LIKE else "request"
        predicted_region = classifier.classify(
            dict(row["prompt_body"]), int(row["max_tokens"])
        )
        confusion[f"{expected_region}_as_{predicted_region}"] += 1
        trace.append(
            EncodedRequest(
                region=predicted_region,
                traffic_class=traffic_class,
                session_id=session_id,
                turn_idx=turn_idx,
                scheduled_time_s=scheduled_time_s,
                prompt_tokens=len(prompt_ids),
                completion_tokens=completion_tokens,
                prompt_pages=prompt_pages,
                stored_pages=stored_pages,
            )
        )
    trace.sort(
        key=lambda item: (
            item.scheduled_time_s,
            item.session_id,
            item.turn_idx,
        )
    )
    calibration = {
        "n_compared": len(prompt_deltas),
        "exact_prompt_token_matches": sum(delta == 0 for delta in prompt_deltas),
        "min_delta_tokens": min(prompt_deltas, default=0),
        "max_delta_tokens": max(prompt_deltas, default=0),
        "mean_delta_tokens": (
            sum(prompt_deltas) / len(prompt_deltas) if prompt_deltas else 0.0
        ),
        "classification_confusion": confusion,
        "uses_historical_service_time": True,
    }
    return trace, calibration


def ratio_values(start: float, stop: float, step: float) -> Iterable[float]:
    count = int(round((stop - start) / step))
    for index in range(count + 1):
        yield round(start + index * step, 6)


def simulate_ratio(
    trace: list[EncodedRequest],
    *,
    ratio: float,
    full_capacity_tokens: int,
    swa_capacity_tokens: int,
    page_size: int,
    sliding_window_tokens: int,
) -> dict[str, Any]:
    agent_full = int(full_capacity_tokens * ratio)
    agent_swa = int(swa_capacity_tokens * ratio)
    capacities = {
        "agent": (agent_full, agent_swa),
        "request": (
            full_capacity_tokens - agent_full,
            swa_capacity_tokens - agent_swa,
        ),
    }
    simulators = {
        region: HybridRadixSimulator(
            full_capacity_tokens=full_capacity,
            swa_capacity_tokens=swa_capacity,
            page_size=page_size,
            sliding_window_tokens=sliding_window_tokens,
        )
        for region, (full_capacity, swa_capacity) in capacities.items()
    }
    totals: dict[str, dict[str, int]] = {
        region: {
            "requests": 0,
            "prompt_tokens": 0,
            "page_aligned_prompt_tokens": 0,
            "cached_prompt_tokens": 0,
            "recomputed_prompt_tokens": 0,
        }
        for region in simulators
    }
    for request in trace:
        simulator = simulators[request.region]
        matched_pages = simulator.match(request.prompt_pages)
        cached_tokens = matched_pages * page_size
        aligned_prompt_tokens = len(request.prompt_pages) * page_size
        block = totals[request.region]
        block["requests"] += 1
        block["prompt_tokens"] += request.prompt_tokens
        block["page_aligned_prompt_tokens"] += aligned_prompt_tokens
        block["cached_prompt_tokens"] += cached_tokens
        block["recomputed_prompt_tokens"] += aligned_prompt_tokens - cached_tokens
        simulator.insert(request.stored_pages, matched_pages)

    overall = {
        key: sum(totals[region][key] for region in totals)
        for key in (
            "requests",
            "prompt_tokens",
            "page_aligned_prompt_tokens",
            "cached_prompt_tokens",
            "recomputed_prompt_tokens",
        )
    }
    for region, block in totals.items():
        denominator = block["page_aligned_prompt_tokens"]
        block["page_aligned_hit_ratio"] = (
            block["cached_prompt_tokens"] / denominator if denominator else 0.0
        )
        simulator = simulators[region]
        block.update(
            {
                "full_capacity_tokens": capacities[region][0],
                "swa_capacity_tokens": capacities[region][1],
                "final_full_used_tokens": simulator.full_used_pages * page_size,
                "final_swa_used_tokens": simulator.swa_used_pages * page_size,
                "peak_full_used_tokens": simulator.peak_full_used_pages * page_size,
                "peak_swa_used_tokens": simulator.peak_swa_used_pages * page_size,
                "full_evicted_tokens": simulator.full_evicted_pages * page_size,
                "swa_evicted_tokens": simulator.swa_evicted_pages * page_size,
                "eviction_operations": simulator.eviction_operations,
            }
        )
    overall_denominator = overall["page_aligned_prompt_tokens"]
    overall["page_aligned_hit_ratio"] = (
        overall["cached_prompt_tokens"] / overall_denominator
        if overall_denominator
        else 0.0
    )
    return {
        "agent_cache_capacity_ratio": ratio,
        "overall": overall,
        "regions": totals,
        "minimum_region_hit_ratio": min(
            block["page_aligned_hit_ratio"] for block in totals.values()
        ),
        "total_full_evicted_tokens": sum(
            block["full_evicted_tokens"] for block in totals.values()
        ),
        "total_swa_evicted_tokens": sum(
            block["swa_evicted_tokens"] for block in totals.values()
        ),
    }


def result_rank(result: dict[str, Any]) -> tuple[float, float, int, int, float]:
    return (
        float(result["overall"]["cached_prompt_tokens"]),
        float(result["minimum_region_hit_ratio"]),
        -int(result["total_full_evicted_tokens"]),
        -int(result["total_swa_evicted_tokens"]),
        -abs(float(result["agent_cache_capacity_ratio"]) - 0.5),
    )


def write_markdown(report: dict[str, Any], path: Path) -> None:
    selected = report["selected"]
    lines = [
        "# Agent 缓存容量比例离线选择",
        "",
        f"- 选中比例：**{selected['agent_cache_capacity_ratio']:.2f}**",
        f"- Full KV 总容量：{report['configuration']['full_cache_capacity_tokens']:,} token",
        f"- 滑动窗口 KV 总容量：{report['configuration']['swa_cache_capacity_tokens']:,} token",
        f"- 页大小：{report['configuration']['page_size']} token",
        f"- 扫描范围：{report['configuration']['ratio_start']:.2f}–{report['configuration']['ratio_stop']:.2f}，步长 {report['configuration']['ratio_step']:.2f}",
        "",
        "## 选中点",
        "",
        "| 指标 | 总体 | Agent | 普通请求 |",
        "|---|---:|---:|---:|",
        f"| 页对齐 prompt token | {selected['overall']['page_aligned_prompt_tokens']:,} | {selected['regions']['agent']['page_aligned_prompt_tokens']:,} | {selected['regions']['request']['page_aligned_prompt_tokens']:,} |",
        f"| 命中 token | {selected['overall']['cached_prompt_tokens']:,} | {selected['regions']['agent']['cached_prompt_tokens']:,} | {selected['regions']['request']['cached_prompt_tokens']:,} |",
        f"| 命中率 | {selected['overall']['page_aligned_hit_ratio']:.4%} | {selected['regions']['agent']['page_aligned_hit_ratio']:.4%} | {selected['regions']['request']['page_aligned_hit_ratio']:.4%} |",
        f"| 重计算 token | {selected['overall']['recomputed_prompt_tokens']:,} | {selected['regions']['agent']['recomputed_prompt_tokens']:,} | {selected['regions']['request']['recomputed_prompt_tokens']:,} |",
        f"| Full 驱逐 token | {selected['total_full_evicted_tokens']:,} | {selected['regions']['agent']['full_evicted_tokens']:,} | {selected['regions']['request']['full_evicted_tokens']:,} |",
        f"| 滑动窗口驱逐 token | {selected['total_swa_evicted_tokens']:,} | {selected['regions']['agent']['swa_evicted_tokens']:,} | {selected['regions']['request']['swa_evicted_tokens']:,} |",
        "",
        "## 最优附近候选",
        "",
        "| Agent 比例 | 总命中率 | Agent 命中率 | 普通请求命中率 | 重计算 token |",
        "|---:|---:|---:|---:|---:|",
    ]
    for item in report["top_candidates"]:
        lines.append(
            f"| {item['agent_cache_capacity_ratio']:.2f} | "
            f"{item['overall']['page_aligned_hit_ratio']:.4%} | "
            f"{item['regions']['agent']['page_aligned_hit_ratio']:.4%} | "
            f"{item['regions']['request']['page_aligned_hit_ratio']:.4%} | "
            f"{item['overall']['recomputed_prompt_tokens']:,} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 使用真实 DeepSeek-V4 tokenizer 和服务端同源消息编码器。",
            "- 使用历史真实回放的 completion token 数，但输出 token ID 使用每次请求唯一的合成值，避免假设下一轮一定复用生成文本。",
            "- 调度顺序使用历史真实 TTFT，并按 completion token 截断比例缩放历史 decode 时间。",
            "- 离线选择仍不模拟新策略引起的排队时间变化与并发锁，因此不替代正式 GPU 配对实验。",
            "- Full/SWA 双池均使用同一比例；结果是正式 GPU 配对实验的比例选择器，不替代线上验收。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--workload-dir", type=Path, default=DEFAULT_WORKLOAD_DIR)
    parser.add_argument(
        "--completion-replay", type=Path, default=DEFAULT_COMPLETION_REPLAY
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--classifier-checkpoint", type=Path, default=DEFAULT_CLASSIFIER
    )
    parser.add_argument("--classifier-threshold", type=float, default=0.5)
    parser.add_argument("--full-cache-capacity-tokens", type=int, default=705_280)
    parser.add_argument("--swa-cache-capacity-tokens", type=int, default=70_400)
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--sliding-window-tokens", type=int, default=128)
    parser.add_argument("--ratio-start", type=float, default=0.05)
    parser.add_argument("--ratio-stop", type=float, default=0.95)
    parser.add_argument("--ratio-step", type=float, default=0.01)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workload_dir = args.workload_dir.resolve()
    workload_path = workload_dir / "workload.jsonl"
    manifest_path = workload_dir / "manifest.json"
    if not args.model_path.is_dir():
        raise SystemExit(f"模型目录不存在：{args.model_path}")
    if not workload_path.is_file() or not manifest_path.is_file():
        raise SystemExit(f"workload 或 manifest 不存在：{workload_dir}")
    if not args.completion_replay.is_file():
        raise SystemExit(f"历史 completion replay 不存在：{args.completion_replay}")
    if not args.classifier_checkpoint.is_file():
        raise SystemExit(f"分类器 checkpoint 不存在：{args.classifier_checkpoint}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = manifest.get("workload_jsonl_sha256")
    actual_hash = sha256_file(workload_path)
    if expected_hash and actual_hash != expected_hash:
        raise SystemExit(
            f"workload 哈希不一致：actual={actual_hash} expected={expected_hash}"
        )
    if args.page_size <= 0:
        raise SystemExit("page-size 必须大于 0")
    if args.ratio_step <= 0 or not 0 < args.ratio_start <= args.ratio_stop < 1:
        raise SystemExit("比例范围必须在 (0, 1) 内，且步长大于 0")

    print(f"[tokenizer] loading {args.model_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=True,
        local_files_only=True,
    )
    classifier = RequestRegionClassifier.load(
        args.classifier_checkpoint,
        threshold=float(args.classifier_threshold),
    )
    workload_rows = read_jsonl(workload_path)
    completion_rows = read_jsonl(args.completion_replay)
    trace, calibration = build_trace(
        workload_rows,
        completion_rows,
        tokenizer,
        classifier,
        int(args.page_size),
    )
    print(
        f"[trace] requests={len(trace)} exact_prompt_matches="
        f"{calibration['exact_prompt_token_matches']}/{calibration['n_compared']}",
        flush=True,
    )
    results = []
    for ratio in ratio_values(args.ratio_start, args.ratio_stop, args.ratio_step):
        result = simulate_ratio(
            trace,
            ratio=ratio,
            full_capacity_tokens=int(args.full_cache_capacity_tokens),
            swa_capacity_tokens=int(args.swa_cache_capacity_tokens),
            page_size=int(args.page_size),
            sliding_window_tokens=int(args.sliding_window_tokens),
        )
        results.append(result)
        print(
            f"[scan] ratio={ratio:.2f} hit="
            f"{result['overall']['page_aligned_hit_ratio']:.4%} "
            f"agent={result['regions']['agent']['page_aligned_hit_ratio']:.4%} "
            f"request={result['regions']['request']['page_aligned_hit_ratio']:.4%}",
            flush=True,
        )
    selected = max(results, key=result_rank)
    top_candidates = sorted(results, key=result_rank, reverse=True)[:10]
    report = {
        "method": "deepseek_v4_page_radix_full_swa_lru_approximation",
        "selection_objective": [
            "maximize_total_cached_prompt_tokens",
            "maximize_minimum_region_hit_ratio",
            "minimize_full_evicted_tokens",
            "minimize_swa_evicted_tokens",
            "prefer_ratio_near_0.5",
        ],
        "configuration": {
            "model_path": str(args.model_path.resolve()),
            "workload_path": str(workload_path),
            "workload_sha256": actual_hash,
            "completion_replay": str(args.completion_replay.resolve()),
            "completion_replay_sha256": sha256_file(args.completion_replay),
            "classifier_checkpoint": str(args.classifier_checkpoint.resolve()),
            "classifier_checkpoint_sha256": sha256_file(args.classifier_checkpoint),
            "classifier_threshold": float(args.classifier_threshold),
            "full_cache_capacity_tokens": int(args.full_cache_capacity_tokens),
            "swa_cache_capacity_tokens": int(args.swa_cache_capacity_tokens),
            "page_size": int(args.page_size),
            "sliding_window_tokens": int(args.sliding_window_tokens),
            "ratio_start": float(args.ratio_start),
            "ratio_stop": float(args.ratio_stop),
            "ratio_step": float(args.ratio_step),
        },
        "trace": {
            "requests": len(trace),
            "agent_requests": sum(item.region == "agent" for item in trace),
            "request_requests": sum(item.region == "request" for item in trace),
            "prompt_token_calibration": calibration,
        },
        "selected": selected,
        "top_candidates": top_candidates,
        "all_candidates": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "offline_ratio_selection.json"
    markdown_path = args.out_dir / "offline_ratio_selection.md"
    env_path = args.out_dir / "selected_ratio.env"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(report, markdown_path)
    env_path.write_text(
        "# Generated by select_agent_cache_capacity_ratio.py\n"
        f"AGENT_CACHE_CAPACITY_RATIO={selected['agent_cache_capacity_ratio']:.2f}\n"
        f"OFFLINE_FULL_CACHE_CAPACITY_TOKENS={int(args.full_cache_capacity_tokens)}\n"
        f"OFFLINE_SWA_CACHE_CAPACITY_TOKENS={int(args.swa_cache_capacity_tokens)}\n",
        encoding="utf-8",
    )
    print(
        f"[selected] AGENT_CACHE_CAPACITY_RATIO="
        f"{selected['agent_cache_capacity_ratio']:.2f}",
        flush=True,
    )
    print(f"[written] {json_path}", flush=True)
    print(f"[written] {markdown_path}", flush=True)
    print(f"[written] {env_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
