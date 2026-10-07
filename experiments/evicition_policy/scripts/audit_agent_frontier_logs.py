#!/usr/bin/env python3
"""Audit existing log coverage without treating client events as KV events.

Only structure, field names, counts, numeric aggregate metrics and hashes are
exported. Prompt text and token ID arrays are never emitted. Relative --suite
and --output arguments, and all relative paths in the report, use this
experiment directory as their base. Existing output files are never replaced.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = Path("results/runs/20260928T015431Z_a6d1c132")
POLICIES = {"lru": "01_lru", "lfu": "02_lfu", "slru": "03_slru"}
JSONL_FILES = (
    "measurement/events.jsonl",
    "measurement/requests.jsonl",
    "warmup/events.jsonl",
    "warmup/requests.jsonl",
    "monitor.jsonl",
)
METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+(\S+)")
SELECTED_METRICS = {
    "sglang:evicted_tokens_total",
    "sglang:eviction_duration_seconds_count",
    "sglang:eviction_duration_seconds_sum",
    "sglang:kv_available_tokens",
    "sglang:kv_evictable_tokens",
    "sglang:kv_used_tokens",
    "sglang:swa_available_tokens",
    "sglang:swa_evictable_tokens",
    "sglang:swa_used_tokens",
    "sglang:cached_tokens_total",
    "sglang:num_retracted_reqs",
}
COUNTER_PREFIXES = (
    "sglang:evicted_tokens_total",
    "sglang:eviction_duration_seconds_count",
    "sglang:eviction_duration_seconds_sum",
    "sglang:cached_tokens_total",
)
SERVER_PATTERNS = {
    "evict": r"evict",
    "candidate": r"candidate",
    "frontier": r"frontier",
    "victim": r"victim",
    "parent_exposure": r"parent[_ -]?expos|expos(?:ed|ure).*parent",
    "lock_word": r"\block(?:ed|ing|s)?\b|ref_count|lock_ref",
    "split_word": r"\bsplit(?:s|ting)?\b",
    "stable_prefix_digest": r"stable_prefix_digest",
    "parent_stable_prefix_digest": r"parent_stable_prefix_digest",
    "node_identifier": r"\bnode_id\b|transient_node_id",
    "page_identifier": r"\bpage_id\b|\bblock_hash\b",
    "demand_count": r"demand_count",
    "hit_count": r"hit_count",
    "cache_namespace_hash": r"cache_namespace_hash",
    "event_seq": r"event_seq",
    "kv_cache_event_config": r"kv_events_config|kv_events",
}


def resolve_argument(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def missing_file(path: Path) -> dict[str, Any]:
    return {
        "path": path_label(path),
        "status": "missing_file",
        "bytes": None,
        "sha256": None,
        "parsed_records": None,
    }


def fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"path": path_label(path), "bytes": size, "sha256": digest.hexdigest()}


def field_paths(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Inspect dictionary structure without visiting scalar token arrays."""
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else key
            yield name, child
            if isinstance(child, dict):
                yield from field_paths(child, name)


def parse_metrics(text: str) -> tuple[set[str], dict[str, float], dict[str, str]]:
    names: set[str] = set()
    selected: dict[str, float] = {}
    help_text: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("# HELP "):
            parts = line.split(" ", 3)
            if len(parts) == 4 and (
                parts[2] in SELECTED_METRICS
                or parts[2] == "sglang:eviction_duration_seconds"
            ):
                help_text[parts[2]] = parts[3]
            continue
        match = METRIC_RE.match(line)
        if not match:
            continue
        name, labels, raw_value = match.groups()
        names.add(name)
        if name in SELECTED_METRICS:
            numeric = float(raw_value)
            if math.isfinite(numeric):
                series = name + ("{" + labels + "}" if labels else "")
                selected[series] = numeric
    return names, selected, help_text


def audit_jsonl(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return missing_file(path)
    digest = hashlib.sha256()
    size = rows = empty = 0
    fields: Counter[str] = Counter()
    nulls: Counter[str] = Counter()
    types: dict[str, Counter[str]] = defaultdict(Counter)
    events: Counter[str] = Counter()
    event_fields: dict[str, Counter[str]] = defaultdict(Counter)
    metric_presence: Counter[str] = Counter()
    metric_samples: dict[str, dict[str, float | int]] = {}
    errors: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        for lineno, line in enumerate(stream, 1):
            digest.update(line)
            size += len(line)
            if not line.strip():
                empty += 1
                continue
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError) as error:
                errors.append({"line": lineno, "error_type": type(error).__name__})
                continue
            if not isinstance(record, dict):
                errors.append({"line": lineno, "error_type": "NonObjectRecord"})
                continue
            rows += 1
            record_fields = list(field_paths(record))
            for name, value in record_fields:
                fields[name] += 1
                types[name][type(value).__name__] += 1
                if value is None:
                    nulls[name] += 1
            event = record.get("event", record.get("event_type"))
            if isinstance(event, str):
                events[event] += 1
                event_fields[event].update(name for name, _ in record_fields)
            if isinstance(record.get("metrics"), str):
                names, selected, _ = parse_metrics(record["metrics"])
                metric_presence.update(names)
                for series, value in selected.items():
                    summary = metric_samples.setdefault(
                        series,
                        {"samples": 0, "first": value, "last": value, "min": value, "max": value},
                    )
                    summary["samples"] += 1
                    summary["last"] = value
                    summary["min"] = min(summary["min"], value)
                    summary["max"] = max(summary["max"], value)
    result = {
        "path": path_label(path),
        "status": "parsed" if not errors else "parse_errors",
        "bytes": size,
        "sha256": digest.hexdigest(),
        "parsed_records": rows,
        "empty_lines": empty,
        "parse_errors": errors,
        "field_presence_records": dict(sorted(fields.items())),
        "null_records_by_field": dict(sorted(nulls.items())),
        "field_types": {name: dict(sorted(counts.items())) for name, counts in sorted(types.items())},
        "event_name_counts": dict(sorted(events.items())),
        "fields_by_event_name": {name: sorted(counts) for name, counts in sorted(event_fields.items())},
        "field_presence_by_event_name": {
            name: dict(sorted(counts.items())) for name, counts in sorted(event_fields.items())
        },
    }
    if metric_presence:
        result["metric_name_presence_samples"] = dict(sorted(metric_presence.items()))
        result["selected_metric_sample_summaries"] = dict(sorted(metric_samples.items()))
        result["metric_scope_note"] = (
            "定期抓取的进程/池级指标可能跨启动、预热和测量；采样数不是淘汰次数，"
            "池级可回收 token 数不是合法候选节点数。"
        )
    return result


def audit_server(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return missing_file(path)
    raw = path.read_bytes()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    matches = {
        name: [index for index, line in enumerate(lines, 1) if re.search(pattern, line, re.I)]
        for name, pattern in SERVER_PATTERNS.items()
    }
    evict_lines = [lines[index - 1] for index in matches["evict"]]
    split_lines = [lines[index - 1] for index in matches["split_word"]]
    return {
        "path": path_label(path),
        "status": "parsed",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "line_count": len(lines),
        "keyword_regexes": SERVER_PATTERNS,
        "keyword_matching_line_counts": {name: len(values) for name, values in matches.items()},
        "keyword_matching_line_numbers": matches,
        "startup_config_evidence": {
            "kv_events_config_none": any("kv_events_config=None" in line for line in lines),
            "evict_matches_are_policy_flags_or_server_args": (
                all("radix-eviction-policy" in line or "radix_eviction_policy=" in line for line in evict_lines)
                if evict_lines else None
            ),
            "split_matches_are_cp_mode": (
                all("dsa_prefill_cp_mode='round-robin-split'" in line for line in split_lines)
                if split_lines else None
            ),
        },
        "interpretation": (
            "以上仅为文本匹配行数。0 表示没有匹配文本，不表示真实事件从未发生；"
            "非零可能来自启动参数或其他日志，不能等同 KV 事件次数。未输出原始日志行。"
        ),
    }


def audit_prometheus(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return missing_file(path)
    raw = path.read_bytes()
    names, selected, help_text = parse_metrics(raw.decode("utf-8"))
    return {
        "path": path_label(path),
        "status": "parsed",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "metric_names": sorted(names),
        "selected_values": selected,
        "selected_help_text": help_text,
    }


def capability_limits(policies: dict[str, Any]) -> dict[str, Any]:
    reasons = {
        "real_eviction_candidate_frontier": "没有完整合法候选集合；池级可回收 token gauge 无法识别节点。",
        "selected_victims": "没有逐次 victim 稳定 ID、释放预算及节点 evict 记录。",
        "new_tail_legal_candidate_count_and_bytes": "缺少候选身份、插入时序、锁状态及物理占用。",
        "parent_exposed_after_child_eviction": "缺少节点父子关联、child eviction 和候选集合变化事件。",
        "reused_leaf_or_branch_candidate_count": "缺少候选叶子身份及独立请求的精确前缀 demand 计数。",
        "node_lock_unlock_refcount": "客户端在途请求不能等同引擎节点锁或引用计数。",
        "node_split_merge": "客户端字段未记录 radix split/merge；server 关键词不是结构化事件。",
        "stable_prefix_or_page_identity": "完整请求/输出 hash 不能替代缓存命名空间与页前缀 ID。",
        "node_demand_count": "stream token 数、会话轮次和前缀输入出现次数不是节点 demand/hit_count。",
        "actual_frontier_future_reuse_counterfactual": "无法恢复同一合法 frontier 和相同释放预算的反事实。",
    }
    # This utility audits this suite's current client-log contract. If new KV
    # logs are introduced, counts remain unclassified rather than being guessed.
    observed_fields = set()
    observed_event_names = set()
    for policy in policies.values():
        for log in policy["jsonl_logs"].values():
            observed_fields.update(log.get("field_presence_records", {}))
            observed_event_names.update(log.get("event_name_counts", {}))
    possible_new_kv_schema = bool(
        {"evict", "split", "lock", "unlock", "store", "demand"} & observed_event_names
        or {"stable_prefix_digest", "candidate_count", "selected_victim_digests"} & observed_fields
    )
    status = "requires_schema_review" if possible_new_kv_schema else "unsupported"
    result = {
        name: {"status": status, "observed_count": None, "reason": reason}
        for name, reason in reasons.items()
    }
    result["request_level_cache_hit_length"] = {
        "status": "available" if "cached_tokens" in observed_fields else "unsupported",
        "source": "measurement/requests.jsonl: cached_tokens",
        "limitation": "cached_tokens_details 的 device/host 是缓存层级，不是 Full/SWA，不能识别节点。",
    }
    result["request_lifecycle_and_stream_progress"] = {
        "status": "available" if {"submitted", "tokens"} <= observed_event_names else "requires_schema_review",
        "source": "events.jsonl 的 submitted/tokens；requests.jsonl 的 first_token_seconds/completed_seconds",
        "limitation": "客户端观测，与引擎 KV 生命周期不同；完成时间不是独立 completion 事件。",
    }
    result["pool_level_occupancy_samples"] = {
        "status": "available_aggregate" if "metrics" in observed_fields else "unsupported",
        "source": "monitor.jsonl 与 metrics_before/after.prom",
        "limitation": "仅聚合 token slots 采样，不能得到候选组成、物理字节或逐次回收状态。",
    }
    return result


def build_audit(suite: Path) -> dict[str, Any]:
    policies = {}
    for policy, directory in POLICIES.items():
        base = suite / directory
        logs = {name: audit_jsonl(base / name) for name in JSONL_FILES}
        endpoints = {
            name: audit_prometheus(base / name)
            for name in ("metrics_before.prom", "metrics_after.prom")
        }
        before = endpoints["metrics_before.prom"].get("selected_values", {})
        after = endpoints["metrics_after.prom"].get("selected_values", {})
        deltas = {
            key: after[key] - before[key]
            for key in sorted(before.keys() & after.keys())
            if key.startswith(COUNTER_PREFIXES)
        }
        policies[policy] = {
            "directory": path_label(base),
            "jsonl_logs": logs,
            "server_log": audit_server(base / "server.log"),
            "metric_endpoints": endpoints,
            "endpoint_counter_deltas": deltas,
            "endpoint_counter_interpretation": (
                "这里只是端点累计 counter 原值差。eviction 指标按 cache_type 聚合，"
                "埋点语义未在此审计中验证；不能视为独立 Full/SWA 节点、物理页或合法候选数。"
                "histogram count 也不自动等同一次完整淘汰决策。"
            ),
        }
    schema_path = ROOT / "configs/agent_policy_diagnostics_schema.json"
    schema = json.loads(schema_path.read_text()) if schema_path.is_file() else {}
    return {
        "schema_version": "agent_frontier_log_coverage_audit_v2",
        "run_id": suite.name,
        "path_convention": "所有相对路径相对于 experiments/evicition_policy；目录外输入保留绝对路径。CLI 相对参数也使用此基目录。",
        "source_root": path_label(suite),
        "scope": "只读扫描现有日志；无 GPU、新 serving、引擎修改或原始 prompt/token 内容输出。",
        "null_semantics": "unsupported 的真实事件数量为 null；客户端事件计数与文本匹配计数不能当作引擎 KV 事件次数。",
        "generator": fingerprint(Path(__file__)),
        "definition_inputs": [fingerprint(schema_path)] if schema_path.is_file() else [],
        "diagnostics_schema_status": schema.get("status"),
        "diagnostics_schema_status_note": "设计规范中的 required_fields/event_type_values 不代表当前已经采集。",
        "requested_capabilities": capability_limits(policies),
        "policies": policies,
        "directly_computable": [
            "客户端事件数、请求字段覆盖率、命中总长度、首 token/完成时间。",
            "结合冻结 workload，可计算逻辑输入前缀出现次数与增长代理。",
            "Full/SWA 池级占用/可回收 token slots 采样分布和端点累计 counter 差。",
        ],
        "not_directly_computable": [
            "合法候选中新尾部、暴露祖先、已复用叶子/分支的节点数与物理空间占比。",
            "节点真实 demand count、lock、split、逐次 victim 和释放预算。",
            "相同合法候选与相同释放预算下的替代选择净收益。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, required=True, help="New JSON output file; existing files are refused.")
    args = parser.parse_args()
    suite, output = resolve_argument(args.suite), resolve_argument(args.output)
    if not suite.is_dir():
        parser.error(f"suite directory does not exist: {suite}")
    if output.exists():
        parser.error(f"refusing to replace existing output: {output}")
    audit = build_audit(suite)
    serialized = json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    print(json.dumps({"output": path_label(output), "bytes": len(serialized.encode("utf-8"))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
