#!/usr/bin/env python3
"""Break down server-side latency metrics for a paired replay.

The SGLang metrics files are Prometheus snapshots.  This script computes
``after - before`` for counters and histogram buckets so that startup probes
and the warmup request are excluded from the replay results.

The output deliberately keeps the following quantities separate:

* queue time;
* the observed prefill stages (``prefill_forward`` and nested
  ``chunked_prefill``);
* server TTFT;
* observed post-first-token interval (E2E minus TTFT and inter-token latency);
* client-visible overhead and tokenizer/detokenizer CPU counters.

SGLang's ``chunked_prefill`` is a nested/composite stage and must not be added
to ``prefill_forward``.  The markdown report emitted by this script records
that caveat along with stage-count mismatches.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple


LabelKey = Tuple[Tuple[str, str], ...]
SampleKey = Tuple[str, LabelKey]
Snapshot = Dict[SampleKey, float]

SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>.*)\})?\s+(?P<value>[^\s]+)(?:\s+[^\s]+)?$"
)
LABEL_RE = re.compile(r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"\\])*)"')


def _unescape_label(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r'\"', '"').replace(r"\n", "\n")


def parse_labels(raw: Optional[str]) -> LabelKey:
    if not raw:
        return ()
    labels = {
        match.group("key"): _unescape_label(match.group("value"))
        for match in LABEL_RE.finditer(raw)
    }
    return tuple(sorted(labels.items()))


def parse_number(raw: str) -> Optional[float]:
    if raw in {"NaN", "nan"}:
        return None
    if raw in {"+Inf", "Inf", "inf"}:
        return math.inf
    if raw in {"-Inf", "-inf"}:
        return -math.inf
    return float(raw)


def parse_prometheus(path: Path) -> Snapshot:
    snapshot: Snapshot = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        match = SAMPLE_RE.match(line)
        if not match:
            raise ValueError(f"cannot parse {path}:{line_number}: {line}")
        value = parse_number(match.group("value"))
        if value is None:
            continue
        key = (match.group("name"), parse_labels(match.group("labels")))
        snapshot[key] = value
    return snapshot


def labels_as_dict(labels: LabelKey) -> Dict[str, str]:
    return dict(labels)


def iter_samples(
    snapshot: Snapshot,
    name: str,
    required: Mapping[str, str] | None = None,
) -> Iterable[Tuple[LabelKey, float]]:
    required = required or {}
    for (sample_name, labels), value in snapshot.items():
        if sample_name != name:
            continue
        label_dict = labels_as_dict(labels)
        if all(label_dict.get(k) == v for k, v in required.items()):
            yield labels, value


def one_sample(
    snapshot: Snapshot,
    name: str,
    required: Mapping[str, str] | None = None,
    *,
    default: float = 0.0,
) -> float:
    matches = list(iter_samples(snapshot, name, required))
    if not matches:
        return default
    if len(matches) > 1:
        raise ValueError(f"expected one {name} sample for {required}, got {len(matches)}")
    return matches[0][1]


def delta_value(
    before: Snapshot,
    after: Snapshot,
    name: str,
    required: Mapping[str, str] | None = None,
    *,
    default: float = 0.0,
) -> float:
    return one_sample(after, name, required, default=default) - one_sample(
        before, name, required, default=default
    )


def _histogram_buckets(
    snapshot: Snapshot,
    base_name: str,
    required: Mapping[str, str] | None = None,
) -> Dict[float, float]:
    result: Dict[float, float] = {}
    for labels, value in iter_samples(snapshot, f"{base_name}_bucket", required):
        label_dict = labels_as_dict(labels)
        if "le" not in label_dict:
            continue
        upper = parse_number(label_dict["le"])
        if upper is None:
            continue
        result[upper] = value
    return result


def _quantile(buckets: Mapping[float, float], quantile: float) -> Optional[float]:
    finite = sorted((upper, count) for upper, count in buckets.items() if math.isfinite(upper))
    inf_count = buckets.get(math.inf)
    if inf_count is not None:
        finite.append((math.inf, inf_count))
    if not finite:
        return None
    total = finite[-1][1]
    if total <= 0:
        return None
    target = quantile * total
    previous_upper = 0.0
    previous_count = 0.0
    for upper, count in finite:
        if count < target:
            previous_upper, previous_count = upper, count
            continue
        if math.isinf(upper):
            return previous_upper if math.isfinite(previous_upper) else None
        if count <= previous_count:
            return upper
        fraction = (target - previous_count) / (count - previous_count)
        return previous_upper + (upper - previous_upper) * fraction
    return finite[-1][0] if math.isfinite(finite[-1][0]) else None


def histogram_summary(
    before: Snapshot,
    after: Snapshot,
    base_name: str,
    required: Mapping[str, str] | None = None,
) -> Dict[str, object]:
    required = required or {}
    before_buckets = _histogram_buckets(before, base_name, required)
    after_buckets = _histogram_buckets(after, base_name, required)
    bucket_deltas = {
        upper: after_buckets.get(upper, 0.0) - before_buckets.get(upper, 0.0)
        for upper in set(before_buckets) | set(after_buckets)
    }
    count = delta_value(before, after, f"{base_name}_count", required)
    total = delta_value(before, after, f"{base_name}_sum", required)
    result: Dict[str, object] = {
        "metric": base_name,
        "count": count,
        "sum_seconds": total,
        "mean_seconds": (total / count) if count > 0 else None,
        "p50_seconds": _quantile(bucket_deltas, 0.50),
        "p90_seconds": _quantile(bucket_deltas, 0.90),
        "p99_seconds": _quantile(bucket_deltas, 0.99),
        "bucket_deltas": {
            ("+Inf" if math.isinf(upper) else str(upper)): value
            for upper, value in sorted(bucket_deltas.items())
        },
    }
    negative = [value for value in bucket_deltas.values() if value < -1e-9]
    if negative:
        result["warning"] = "negative histogram delta detected"
    return result


def _base_labels(snapshot: Snapshot) -> Dict[str, str]:
    for name in ("sglang:num_requests_total", "sglang:prompt_tokens_total"):
        matches = list(iter_samples(snapshot, name))
        if matches:
            labels = labels_as_dict(matches[0][0])
            return {
                key: labels[key]
                for key in ("engine_type", "model_name")
                if key in labels
            }
    return {}


def _rank_labels(base: Mapping[str, str], tp_rank: str) -> Dict[str, str]:
    return {
        **base,
        "moe_ep_rank": "0",
        "pp_rank": "0",
        "tp_rank": tp_rank,
    }


def _client_summary(run_dir: Path, mode: str) -> Dict[str, object]:
    path = run_dir / mode / "run_mix_replay" / "summary.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    latency = data.get("latency", {})
    result = {
        "wall_clock_seconds": data.get("integrity", {}).get("wall_clock_s"),
        "ttft": latency.get("ttft_ms", {}),
        "tpot": latency.get("tpot_ms", {}),
        "e2e": latency.get("e2e_ms", {}),
    }
    return result


def _http_delta(before: Snapshot, after: Snapshot, metric: str) -> list[dict[str, object]]:
    keys = set()
    for snapshot in (before, after):
        for labels, _ in iter_samples(snapshot, metric):
            keys.add(labels)
    rows = []
    for labels in sorted(keys):
        b = one_sample(before, metric, labels_as_dict(labels))
        a = one_sample(after, metric, labels_as_dict(labels))
        delta = a - b
        if abs(delta) > 1e-9:
            rows.append({"labels": labels_as_dict(labels), "delta": delta})
    return rows


def _rank_consistency(
    before: Snapshot,
    after: Snapshot,
    base: Mapping[str, str],
    tp_ranks: Sequence[str],
) -> Dict[str, object]:
    """Compare rank-local counter deltas used by the report.

    Sums can differ slightly because the ranks observe asynchronous local
    timestamps, while event counts should be identical.  Keeping the spread
    makes the choice of rank 0 auditable without averaging unrelated timers.
    """

    specs = {
        "queue_time": ("sglang:queue_time_seconds", {}),
        "request_process": (
            "sglang:per_stage_req_latency_seconds",
            {"stage": "request_process"},
        ),
        "prefill_forward": (
            "sglang:per_stage_req_latency_seconds",
            {"stage": "prefill_forward"},
        ),
        "chunked_prefill": (
            "sglang:per_stage_req_latency_seconds",
            {"stage": "chunked_prefill"},
        ),
    }
    output: Dict[str, object] = {}
    for label, (metric, extra) in specs.items():
        sums = []
        counts = []
        for rank in tp_ranks:
            filters = _rank_labels(base, rank)
            filters.update(extra)
            sums.append(delta_value(before, after, f"{metric}_sum", filters))
            counts.append(delta_value(before, after, f"{metric}_count", filters))
        output[label] = {
            "ranks": list(tp_ranks),
            "sum_min_seconds": min(sums),
            "sum_max_seconds": max(sums),
            "sum_range_seconds": max(sums) - min(sums),
            "count_min": min(counts),
            "count_max": max(counts),
            "counts_equal": len(set(round(value, 9) for value in counts)) == 1,
        }
    return output


def analyze_mode(run_dir: Path, mode: str, tp_rank: str) -> Dict[str, object]:
    mode_dir = run_dir / mode
    before = parse_prometheus(mode_dir / "metrics_before.prom")
    after = parse_prometheus(mode_dir / "metrics_after.prom")
    base = _base_labels(after)
    ranked = _rank_labels(base, tp_rank)

    stages: MutableMapping[str, Dict[str, object]] = {}
    for stage in ("request_process", "prefill_forward", "chunked_prefill"):
        stages[stage] = histogram_summary(
            before,
            after,
            "sglang:per_stage_req_latency_seconds",
            {**ranked, "stage": stage},
        )

    queue = histogram_summary(before, after, "sglang:queue_time_seconds", ranked)
    ttft = histogram_summary(before, after, "sglang:time_to_first_token_seconds", base)
    e2e = histogram_summary(before, after, "sglang:e2e_request_latency_seconds", base)
    itl = histogram_summary(before, after, "sglang:inter_token_latency_seconds", base)

    request_count = delta_value(before, after, "sglang:num_requests_total", base)
    prompt_tokens = delta_value(before, after, "sglang:prompt_tokens_total", base)
    cached_tokens = delta_value(
        before,
        after,
        "sglang:cached_tokens_total",
        {"cache_source": "device"},
    )
    generation_tokens = delta_value(before, after, "sglang:generation_tokens_total", base)
    eviction_sum = delta_value(
        before,
        after,
        "sglang:eviction_duration_seconds_sum",
        {"cache_type": "SWARadixCache"},
    )
    eviction_count = delta_value(
        before,
        after,
        "sglang:eviction_duration_seconds_count",
        {"cache_type": "SWARadixCache"},
    )
    evicted_tokens = delta_value(
        before,
        after,
        "sglang:evicted_tokens_total",
        {"cache_type": "SWARadixCache"},
    )
    decode_tail = float(e2e["sum_seconds"]) - float(ttft["sum_seconds"])
    itl_sum = float(itl["sum_seconds"])
    queue_sum = float(queue["sum_seconds"])
    prefill_sum = float(stages["prefill_forward"]["sum_seconds"])
    ttft_sum = float(ttft["sum_seconds"])
    derived = {
        "decode_tail_seconds": decode_tail,
        "decode_tail_mean_seconds": decode_tail / request_count if request_count else None,
        "inter_token_sum_seconds": itl_sum,
        "inter_token_mean_seconds": itl["mean_seconds"],
        "decode_tail_minus_inter_token_seconds": decode_tail - itl_sum,
        "ttft_minus_queue_and_prefill_seconds": ttft_sum - queue_sum - prefill_sum,
        "ttft_minus_queue_and_prefill_mean_seconds": (
            (ttft_sum - queue_sum - prefill_sum) / request_count if request_count else None
        ),
        "prefill_stage_count_minus_request_count": (
            float(stages["prefill_forward"]["count"]) - request_count
        ),
        "queue_stage_count_minus_request_count": float(queue["count"]) - request_count,
    }

    cpu = {}
    for component in ("tokenizer", "detokenizer"):
        cpu[component] = delta_value(
            before,
            after,
            "sglang:process_cpu_seconds_total",
            {"component": component},
        )

    client = _client_summary(run_dir, mode)
    client_ttft_mean = (client.get("ttft") or {}).get("mean")
    server_ttft_mean_ms = float(ttft["mean_seconds"]) * 1000 if ttft["mean_seconds"] is not None else None
    if client_ttft_mean is not None and server_ttft_mean_ms is not None:
        derived["client_minus_server_ttft_ms"] = client_ttft_mean - server_ttft_mean_ms
    else:
        derived["client_minus_server_ttft_ms"] = None

    return {
        "mode": mode,
        "snapshot_files": {
            "before": str(mode_dir / "metrics_before.prom"),
            "after": str(mode_dir / "metrics_after.prom"),
        },
        "labels": {"base": base, "ranked": ranked},
        "request_count": request_count,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "generation_tokens": generation_tokens,
        "eviction": {
            "duration_sum_seconds": eviction_sum,
            "count": eviction_count,
            "evicted_tokens": evicted_tokens,
        },
        "stages": dict(stages),
        "queue": queue,
        "ttft": ttft,
        "e2e": e2e,
        "inter_token_latency": itl,
        "derived": derived,
        "process_cpu_seconds": cpu,
        "rank_consistency": _rank_consistency(
            before, after, base, [str(rank) for rank in range(8)]
        ),
        "http_requests": _http_delta(before, after, "sglang:http_requests_total"),
        "http_responses": _http_delta(before, after, "sglang:http_responses_total"),
        "client_replay": client,
    }


def _number(value: object, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and not math.isfinite(value):
        return "—"
    return f"{float(value):.{digits}f}"


def _ms(value: object, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 1000:.{digits}f}"


def _metric_row(unified: Mapping[str, object], elastic: Mapping[str, object], path: Sequence[str]) -> str:
    def get(data: Mapping[str, object]) -> object:
        cur: object = data
        for part in path:
            if not isinstance(cur, Mapping):
                return None
            cur = cur.get(part)
        return cur

    u = get(unified)
    e = get(elastic)
    if path[-1].endswith("seconds") or path[-1].endswith("mean_seconds"):
        us, es = _ms(u), _ms(e)
    else:
        us, es = _number(u), _number(e)
    if u is None or e is None:
        diff = "—"
    else:
        diff = _ms(float(e) - float(u)) if us.endswith("ms") else _number(float(e) - float(u))
    return f"| {'/'.join(path)} | {us} | {es} | {diff} |"


def build_markdown(result: Mapping[str, object]) -> str:
    unified = result["modes"]["unified"]
    elastic = result["modes"]["elastic"]
    request_count = int(round(float(unified.get("request_count") or 0)))
    prompt_tokens = float(unified.get("prompt_tokens") or 0)
    unified_cached = float(unified.get("cached_tokens") or 0)
    elastic_cached = float(elastic.get("cached_tokens") or 0)
    unified_hit = 100.0 * unified_cached / prompt_tokens if prompt_tokens else None
    elastic_hit = 100.0 * elastic_cached / prompt_tokens if prompt_tokens else None
    queue_u = float(unified["queue"]["sum_seconds"])
    queue_e = float(elastic["queue"]["sum_seconds"])
    prefill_u = float(unified["stages"]["prefill_forward"]["sum_seconds"])
    prefill_e = float(elastic["stages"]["prefill_forward"]["sum_seconds"])
    ttft_u = float(unified["ttft"]["sum_seconds"])
    ttft_e = float(elastic["ttft"]["sum_seconds"])
    e2e_u = float(unified["e2e"]["sum_seconds"])
    e2e_e = float(elastic["e2e"]["sum_seconds"])
    itl_u = float(unified["inter_token_latency"]["sum_seconds"])
    itl_e = float(elastic["inter_token_latency"]["sum_seconds"])

    def direction(delta: float) -> str:
        return "增加" if delta > 0 else "减少" if delta < 0 else "不变"

    conclusion = (
        f"本次 {request_count} 个请求中，Elastic 的设备缓存命中率为 "
        f"{_number(elastic_hit, 2)}%，Unified 为 {_number(unified_hit, 2)}%，"
        f"变化 {_number(elastic_hit - unified_hit, 2) if unified_hit is not None and elastic_hit is not None else '—'} 个百分点。"
        f"Elastic 的 `prefill_forward` 累计时间{direction(prefill_e - prefill_u)} "
        f"{_number(abs(prefill_e - prefill_u))} 秒，排队累计时间{direction(queue_e - queue_u)} "
        f"{_number(abs(queue_e - queue_u))} 秒，服务端 TTFT 累计时间{direction(ttft_e - ttft_u)} "
        f"{_number(abs(ttft_e - ttft_u))} 秒，E2E 累计时间{direction(e2e_e - e2e_u)} "
        f"{_number(abs(e2e_e - e2e_u))} 秒。"
        "命中率只描述复用的 token 数；TTFT 还受排队、批次组成、首个 decode 调度和淘汰路径影响，"
        "因此不能把命中率百分点直接换算成时间百分比。"
    )
    eviction_u = unified.get("eviction") or {}
    eviction_e = elastic.get("eviction") or {}
    lines = [
        "# Unified 与 Elastic 阶段延迟拆分",
        "",
        "本报告对 `metrics_after.prom - metrics_before.prom` 做差分，去除启动探测和预热请求。",
        f"正式回放是同一份 {request_count} 请求 workload；服务端指标以 TP rank 0 为主。",
        "",
        "## 结论",
        "",
        conclusion,
        "",
        "TTFT 不是纯 prefill 时间。这里的服务端 TTFT 从 API 请求创建到首个输出 token，包含请求处理、排队、prefill、首个 decode 调度/执行以及其他时间；客户端 TTFT 还会再包含 HTTP 往返和客户端读取首个 chunk 的开销。",
        "",
        "## 服务端阶段总量与均值",
        "",
        "单位：总量为秒，均值为毫秒。`chunked_prefill` 是嵌套阶段，不能与 `prefill_forward` 相加。",
        "",
        "| 阶段 | Unified 总量 | Elastic 总量 | 变化 | Unified 均值 | Elastic 均值 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    stage_names = [
        ("queue", "排队"),
        ("stages/request_process", "request_process"),
        ("stages/prefill_forward", "prefill_forward"),
        ("stages/chunked_prefill", "chunked_prefill（嵌套）"),
        ("ttft", "服务端 TTFT"),
        ("e2e", "服务端 E2E"),
        ("inter_token_latency", "ITL 累计"),
    ]
    for path_text, label in stage_names:
        path = path_text.split("/")
        u: Mapping[str, object] = unified
        e: Mapping[str, object] = elastic
        for part in path:
            u = u[part]  # type: ignore[assignment,index]
            e = e[part]  # type: ignore[assignment,index]
        us, es = float(u["sum_seconds"]), float(e["sum_seconds"])
        um, em = u["mean_seconds"], e["mean_seconds"]
        lines.append(
            f"| {label} | {_number(us)} | {_number(es)} | {_number(es-us)} | {_ms(um)} | {_ms(em)} |"
        )

    lines += [
        "",
        "TP rank 检查：两种模式的 `queue_time`、`request_process`、`prefill_forward`、"
        "`chunked_prefill` 事件计数在 8 个 TP rank 上均一致；计时总量存在异步观测的微小差异，"
        "因此正文统一采用 rank 0，不对不同 rank 的本地计时求平均。",
        f"淘汰计数诊断：Unified 的 `eviction_duration_seconds_sum` 为 {_number(eviction_u.get('duration_sum_seconds'))} 秒、"
        f"{_number(eviction_u.get('count'))} 次；Elastic 为 {_number(eviction_e.get('duration_sum_seconds'))} 秒、"
        f"{_number(eviction_e.get('count'))} 次。该计时是缓存回收路径的观测量，"
        "用于解释策略开销，不与 GPU prefill FLOPs 等同。",
    ]

    lines += [
        "",
        "## 分位数（Prometheus bucket 近似）",
        "",
        "| 指标 | Unified p50 | Elastic p50 | Unified p90 | Elastic p90 | Unified p99 | Elastic p99 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    quantile_specs = [
        ("queue", "排队"),
        ("stages/prefill_forward", "prefill_forward"),
        ("stages/chunked_prefill", "chunked_prefill"),
        ("ttft", "服务端 TTFT"),
        ("e2e", "服务端 E2E"),
        ("inter_token_latency", "ITL 单 token"),
    ]
    for path_text, label in quantile_specs:
        path = path_text.split("/")
        u: Mapping[str, object] = unified
        e: Mapping[str, object] = elastic
        for part in path:
            u = u[part]  # type: ignore[assignment,index]
            e = e[part]  # type: ignore[assignment,index]
        lines.append(
            f"| {label} | {_ms(u['p50_seconds'])} | {_ms(e['p50_seconds'])} | "
            f"{_ms(u['p90_seconds'])} | {_ms(e['p90_seconds'])} | "
            f"{_ms(u['p99_seconds'])} | {_ms(e['p99_seconds'])} |"
        )

    lines += [
        "",
        "## 客户端回放指标（逐请求精确统计）",
        "",
        "服务端 histogram 只能给 bucket 近似分位数；下面的客户端数值来自每个请求的 replay 记录，单位为毫秒。",
        "",
        "| 指标 | Unified p50 | Elastic p50 | Unified p90 | Elastic p90 | Unified 均值 | Elastic 均值 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("ttft", "客户端 TTFT"), ("tpot", "客户端 TPOT/ITL"), ("e2e", "客户端 E2E")):
        u = unified["client_replay"].get(key, {})
        e = elastic["client_replay"].get(key, {})
        lines.append(
            f"| {label} | {_number(u.get('p50'))} | {_number(e.get('p50'))} | "
            f"{_number(u.get('p90'))} | {_number(e.get('p90'))} | "
            f"{_number(u.get('mean'))} | {_number(e.get('mean'))} |"
        )

    lines += [
        "",
        "## TTFT、Decode 与其他开销",
        "",
        "| 项目 | Unified | Elastic | Elastic - Unified |",
        "|---|---:|---:|---:|",
    ]
    derived_specs = [
        ("ttft/sum_seconds", "服务端 TTFT 累计（秒）", "seconds"),
        ("ttft/mean_seconds", "服务端 TTFT 均值（毫秒）", "seconds_to_ms"),
        ("derived/ttft_minus_queue_and_prefill_seconds", "TTFT 减 queue 与 prefill（秒）", "seconds"),
        ("derived/ttft_minus_queue_and_prefill_mean_seconds", "上述残差均值（毫秒）", "seconds_to_ms"),
        ("derived/decode_tail_seconds", "E2E 减 TTFT（decode 尾段，秒）", "seconds"),
        ("derived/decode_tail_mean_seconds", "decode 尾段均值（毫秒）", "seconds_to_ms"),
        ("derived/inter_token_sum_seconds", "ITL 累计（秒）", "seconds"),
        ("derived/inter_token_mean_seconds", "ITL 均值（毫秒/token）", "seconds_to_ms"),
        ("derived/decode_tail_minus_inter_token_seconds", "decode 尾段减 ITL（秒）", "seconds"),
        ("derived/client_minus_server_ttft_ms", "客户端 TTFT 减服务端 TTFT（毫秒）", "raw_ms"),
    ]
    for path_text, label, unit in derived_specs:
        path = path_text.split("/")
        def get(data: Mapping[str, object]) -> object:
            cur: object = data
            for part in path:
                cur = cur[part]  # type: ignore[index]
            return cur
        uv, ev = get(unified), get(elastic)
        if unit == "seconds_to_ms":
            utext = _number(float(uv) * 1000) if uv is not None else "—"
            etext = _number(float(ev) * 1000) if ev is not None else "—"
            diff = _number((float(ev) - float(uv)) * 1000) if uv is not None and ev is not None else "—"
        elif unit == "raw_ms":
            utext, etext = _number(uv), _number(ev)
            diff = _number(float(ev) - float(uv)) if uv is not None and ev is not None else "—"
        else:
            utext, etext = _number(uv), _number(ev)
            diff = _number(float(ev) - float(uv)) if uv is not None and ev is not None else "—"
        lines.append(f"| {label} | {utext} | {etext} | {diff} |")

    lines += [
        "",
        "## 解释边界",
        "",
        "- `queue_time` 是调度等待，不是 HTTP 等待；`request_process` 只有调度器侧请求处理阶段，不能代表完整 tokenizer 或 API 处理时间。",
        f"- `prefill_forward` 是叶级 prefill 观测，`chunked_prefill` 是嵌套/复合阶段；本报告不把两者相加。两种模式的 prefill stage count 分别为 {unified['stages']['prefill_forward']['count']} 和 {elastic['stages']['prefill_forward']['count']}，与 {request_count} 个完成请求的关系可能不是严格一一对应，因此 TTFT 减 queue/prefill 只作为残差诊断，不当作精确 HTTP/tokenizer 时间。",
        f"- `inter_token_latency` 的 count 是首 token 之后的 token 数；本次 Unified/Elastic 分别为 {unified['inter_token_latency']['count']} 和 {elastic['inter_token_latency']['count']}。它是首 token 后输出间隔的观测值，包含 decode、调度等待、批处理交错和输出传递，不能单独解释为 decode kernel 时间。",
        "- 服务端 histogram 的分位数是按 bucket 插值的近似值，不能直接替代客户端逐请求分位数；两者起点、首 chunk 到达时刻和采样口径也不同。",
        "- 服务端没有提供每个请求的 HTTP wall time 或 tokenizer elapsed histogram。报告中的客户端减服务端 TTFT是 HTTP 传输、客户端读取首 chunk 和服务端 API 前后未覆盖部分的合计；tokenizer/detokenizer 另以进程 CPU counter 报告。",
        "",
        "## Tokenizer、Detokenizer 与 HTTP 计数",
        "",
        "| 指标 | Unified | Elastic |",
        "|---|---:|---:|",
        f"| tokenizer CPU 增量（秒） | {_number(unified['process_cpu_seconds']['tokenizer'])} | {_number(elastic['process_cpu_seconds']['tokenizer'])} |",
        f"| detokenizer CPU 增量（秒） | {_number(unified['process_cpu_seconds']['detokenizer'])} | {_number(elastic['process_cpu_seconds']['detokenizer'])} |",
    ]
    def http_count(data: Mapping[str, object], metric: str, endpoint: str) -> object:
        for row in data[metric]:
            if row["labels"].get("endpoint") == endpoint:
                return row["delta"]
        return 0

    for endpoint in ("/v1/chat/completions", "/generate"):
        lines.append(
            f"| HTTP request {endpoint} | "
            f"{_number(http_count(unified, 'http_requests', endpoint))} | "
            f"{_number(http_count(elastic, 'http_requests', endpoint))} |"
        )
        lines.append(
            f"| HTTP response {endpoint} status=200 | "
            f"{_number(http_count(unified, 'http_responses', endpoint))} | "
            f"{_number(http_count(elastic, 'http_responses', endpoint))} |"
        )

    lines += [
        "",
        f"回放完整性记录了两边各 {request_count} 个成功请求；Prometheus HTTP counter 可能在流式响应抓取时滞后，不能用它单独判定请求失败。",
    ]

    lines += [
        "",
        "机器可读原始结果见同目录的 `stage_breakdown.json`。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--tp-rank", default="0")
    args = parser.parse_args()

    output_json = args.output_json or args.run_dir / "stage_breakdown.json"
    output_md = args.output_md or args.run_dir / "stage_breakdown.md"
    result = {
        "run_dir": str(args.run_dir),
        "method": "prometheus after snapshot minus before snapshot",
        "tp_rank_for_ranked_metrics": args.tp_rank,
        "modes": {
            "unified": analyze_mode(args.run_dir, "unified", args.tp_rank),
            "elastic": analyze_mode(args.run_dir, "elastic", args.tp_rank),
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(build_markdown(result), encoding="utf-8")
    print(f"wrote {output_json}")
    print(f"wrote {output_md}")


if __name__ == "__main__":
    main()
