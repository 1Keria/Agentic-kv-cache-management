#!/usr/bin/env python3
"""Freeze a mixed serving workload.

Session-internal content and gaps come from the sources. Cross-session starts
are explicit staggered arrivals. Replay should read the frozen jsonl, not
resample.

Two recipes:

  Two-class (legacy): OpenHands from one directory + WildChat.
    traffic_class = agent | request

  Three-class: unique Flash OpenHands across runners + inferred GLM-online
    agent sessions + WildChat.
    traffic_class = openhands | glm | request
    GLM sessions are inferred (first user hash + messages exact prefix),
    not official session ids.

Example:
  bash scripts/shell/build_mix.sh
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLSBENCH_V11 = (
    REPO_ROOT / "third_party/skillsbench/submissions/skillsbench/v1.1"
)
DEFAULT_AGENT_DIR = (
    SKILLSBENCH_V11
    / "openhands-with-skills__deepseek-deepseek-v4-flash-src-runner03"
)
FLASH_CONFIG_PREFIX = "openhands-with-skills__deepseek-deepseek-v4-flash"
DEFAULT_WILDCHAT_DIR = REPO_ROOT / "third_party/wildchat"
DEFAULT_GLM_JSONL = (
    REPO_ROOT
    / "third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl"
)
DEFAULT_OUT_DIR = REPO_ROOT / "workloads/mix_a8_r32"
WILDCHAT_REPO = "allenai/WildChat-1M"

AGENT_LIKE = {"agent", "openhands", "glm"}


@dataclass
class Turn:
    traffic_class: str
    session_id: str
    turn_idx: int
    session_start_s: float
    pre_gap_s: float
    max_tokens: int
    prompt_body: dict[str, Any]
    source: dict[str, Any]


@dataclass
class SessionMeta:
    session_id: str
    traffic_class: str
    session_start_s: float
    n_turns: int
    orig_span_s: float
    max_tokens_sum: int
    source: dict[str, Any]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        dt = value
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, rest = text.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        text = f"{head}.{(frac + '000000')[:6]}{tz}"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float(dt.timestamp())


def estimate_tokens(text: str) -> int:
    """Cheap length proxy: CJK ≈ 1 token, other ≈ 4 chars/token."""
    if not text:
        return 1
    n_cjk = 0
    for ch in text:
        o = ord(ch)
        if (
            0x4E00 <= o <= 0x9FFF
            or 0x3400 <= o <= 0x4DBF
            or 0x3040 <= o <= 0x30FF
            or 0xAC00 <= o <= 0xD7AF
        ):
            n_cjk += 1
    n_other = len(text) - n_cjk
    return max(1, n_cjk + (n_other + 3) // 4)


def sanitize_agent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        item: dict[str, Any] = {"role": msg.get("role") or "user"}
        if "content" in msg:
            item["content"] = msg.get("content")
        if msg.get("tool_calls"):
            item["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            item["tool_call_id"] = msg["tool_call_id"]
        if item["role"] == "tool" and msg.get("name"):
            item["name"] = msg["name"]
        out.append(item)
    return out


def sanitize_glm_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep OpenAI-compatible fields; drop GLM-only reasoning blobs."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        item: dict[str, Any] = {"role": role}
        content = msg.get("content")
        if content is None:
            content = ""
        item["content"] = content
        if role == "assistant" and msg.get("tool_calls"):
            tcs = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                tcs.append(
                    {
                        "id": tc.get("id") or f"call_{len(tcs)}",
                        "type": tc.get("type") or "function",
                        "function": {
                            "name": fn.get("name") or "unknown",
                            "arguments": fn.get("arguments") or "{}",
                        },
                    }
                )
            item["tool_calls"] = tcs
            if not item["content"]:
                item["content"] = ""
        if role == "tool":
            item["tool_call_id"] = msg.get("tool_call_id") or "missing_tool_call_id"
            if msg.get("name"):
                item["name"] = msg["name"]
        out.append(item)
    return out


def list_agent_trials(agent_dir: Path) -> list[Path]:
    # Each llm_trajectory.jsonl is one OpenHands run. Same content may appear
    # in multiple run folders; replay treats them as distinct sessions.
    return sorted(agent_dir.rglob("llm_trajectory.jsonl"))


def list_flash_configs(skillsbench_root: Path) -> list[Path]:
    if not skillsbench_root.is_dir():
        raise FileNotFoundError(skillsbench_root)
    return sorted(
        p
        for p in skillsbench_root.iterdir()
        if p.is_dir() and p.name.startswith(FLASH_CONFIG_PREFIX)
    )


def list_openhands_unique(skillsbench_root: Path) -> list[tuple[str, Path]]:
    """One path per content hash across all local Flash OpenHands configs."""
    by_hash: dict[str, Path] = {}
    for cfg in list_flash_configs(skillsbench_root):
        for path in sorted(cfg.rglob("llm_trajectory.jsonl")):
            digest = sha256_file(path)
            by_hash.setdefault(digest, path)
    return sorted(by_hash.items(), key=lambda kv: str(kv[1]))


def load_agent_session(
    path: Path,
    *,
    rel_root: Path,
    traffic_class: str,
    content_sha256: str | None = None,
) -> tuple[list[Turn], SessionMeta] | None:
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return None

    req_ts = [parse_ts((r.get("request") or {}).get("timestamp")) for r in rows]
    resp_ts = [parse_ts((r.get("response") or {}).get("timestamp")) for r in rows]
    for i, r in enumerate(rows):
        if resp_ts[i] is None and req_ts[i] is not None:
            dur_ms = r.get("duration_ms")
            if dur_ms is not None:
                resp_ts[i] = req_ts[i] + float(dur_ms) / 1000.0

    task_id = path.parent.parent.name
    run_id = path.parent.parent.parent.name
    config = path.parent.parent.parent.parent.name
    digest = content_sha256 or sha256_file(path)
    session_id = f"{traffic_class}:{digest[:12]}:{task_id}"
    source_path = str(path.relative_to(rel_root))

    turns: list[Turn] = []
    for i, row in enumerate(rows):
        body = (row.get("request") or {}).get("body") or {}
        messages = sanitize_agent_messages(list(body.get("messages") or []))
        if not messages:
            continue
        usage = ((row.get("response") or {}).get("body") or {}).get("usage") or {}
        max_tokens = max(1, int(usage.get("completion_tokens") or 1))
        if i == 0:
            pre_gap = 0.0
        else:
            prev_resp = resp_ts[i - 1]
            this_req = req_ts[i]
            if prev_resp is None or this_req is None:
                pre_gap = 0.0
            else:
                pre_gap = max(0.0, this_req - prev_resp)
        prompt_body: dict[str, Any] = {"messages": messages}
        if body.get("tools"):
            prompt_body["tools"] = body["tools"]
        turns.append(
            Turn(
                traffic_class=traffic_class,
                session_id=session_id,
                turn_idx=len(turns),
                session_start_s=0.0,
                pre_gap_s=round(pre_gap, 6),
                max_tokens=max_tokens,
                prompt_body=prompt_body,
                source={
                    "kind": "skillsbench",
                    "path": source_path,
                    "config": config,
                    "task_id": task_id,
                    "run_id": run_id,
                    "call_idx": i,
                    "content_sha256": digest,
                },
            )
        )
    if not turns:
        return None

    orig_span = 0.0
    if req_ts[0] is not None and req_ts[-1] is not None:
        orig_span = max(0.0, req_ts[-1] - req_ts[0])
    meta = SessionMeta(
        session_id=session_id,
        traffic_class=traffic_class,
        session_start_s=0.0,
        n_turns=len(turns),
        orig_span_s=round(orig_span, 6),
        max_tokens_sum=sum(t.max_tokens for t in turns),
        source={
            "kind": "skillsbench",
            "path": source_path,
            "config": config,
            "task_id": task_id,
            "run_id": run_id,
            "content_sha256": digest,
        },
    )
    return turns, meta


def cap_session_turns(
    loaded: tuple[list[Turn], SessionMeta],
    max_turns: int | None,
) -> tuple[list[Turn], SessionMeta]:
    """Keep the first max_turns so OpenHands depth can match short GLM chains."""
    turns, meta = loaded
    if max_turns is None or len(turns) <= max_turns:
        return loaded
    turns = turns[: int(max_turns)]
    meta = replace(
        meta,
        n_turns=len(turns),
        orig_span_s=round(sum(t.pre_gap_s for t in turns), 6),
        max_tokens_sum=sum(t.max_tokens for t in turns),
    )
    return turns, meta


def strict_prefix_turn_count(turns: list[Turn]) -> int:
    """Count the initial turns whose message lists grow by exact prefix."""
    if not turns:
        return 0
    count = 1
    for prev, nxt in zip(turns, turns[1:]):
        prev_messages = list(prev.prompt_body.get("messages") or [])
        next_messages = list(nxt.prompt_body.get("messages") or [])
        if len(prev_messages) >= len(next_messages):
            break
        if prev_messages != next_messages[: len(prev_messages)]:
            break
        count += 1
    return count


def glm_msg_hash(msg: dict[str, Any]) -> str:
    sig = {
        "role": msg.get("role"),
        "content": msg.get("content"),
        "tool_calls": msg.get("tool_calls"),
        "tool_call_id": msg.get("tool_call_id"),
        "name": msg.get("name"),
    }
    blob = json.dumps(sig, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def first_system_text(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg.get("role") != "system":
            continue
        content = msg.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
    return ""


def lcp_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def peek_openhands_system(path: Path) -> str:
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            msgs = ((row.get("request") or {}).get("body") or {}).get("messages") or []
            return first_system_text(msgs)
    return ""


def count_jsonl_rows(path: Path) -> int:
    n = 0
    with path.open() as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def greedy_prefix_diverse(
    candidates: list[dict[str, Any]],
    *,
    max_lcp_chars: int,
    max_per_kind: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Keep sessions whose system strings share fewer than max_lcp_chars."""
    ordered = sorted(
        candidates,
        key=lambda c: (-int(c["n_turns"]), -float(c.get("span") or 0.0), str(c.get("id") or "")),
    )
    kept: list[dict[str, Any]] = []
    kind_count: dict[str, int] = defaultdict(int)
    limits = max_per_kind or {}
    for cand in ordered:
        kind = str(cand.get("kind") or "")
        if kind in limits and kind_count[kind] >= limits[kind]:
            continue
        sys_txt = str(cand.get("system") or "")
        if any(lcp_len(sys_txt, str(k.get("system") or "")) >= max_lcp_chars for k in kept):
            continue
        kept.append(cand)
        kind_count[kind] += 1
    return kept


def max_pairwise_lcp(systems: list[str]) -> int:
    best = 0
    for i, a in enumerate(systems):
        for b in systems[i + 1 :]:
            best = max(best, lcp_len(a, b))
    return best


def first_user_hash(messages: list[dict[str, Any]]) -> str | None:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        if not str(text).strip():
            continue
        return hashlib.sha256(str(text).encode("utf-8")).hexdigest()
    return None


def is_hash_prefix(prev: list[str], nxt: list[str]) -> bool:
    if len(prev) >= len(nxt):
        return False
    return prev == nxt[: len(prev)]


def index_glm_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    bad = 0
    with path.open("rb") as f:
        line_no = 0
        while True:
            offset = f.tell()
            raw = f.readline()
            if not raw:
                break
            line_no += 1
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pb = json.loads(obj["prompt_body"])
                rb = json.loads(obj.get("response_body") or "{}")
            except Exception:
                bad += 1
                continue
            messages = list(pb.get("messages") or [])
            user_h = first_user_hash(messages)
            if user_h is None:
                continue
            usage = rb.get("usage") or {}
            created = rb.get("created")
            created_s = float(created) if isinstance(created, (int, float)) else None
            sys_txt = first_system_text(messages)
            records.append(
                {
                    "line_no": line_no,
                    "offset": offset,
                    "trace_id": obj.get("trace_id"),
                    "start_s": parse_ts(obj.get("start_time")),
                    "user_hash": user_h,
                    "system": sys_txt,
                    "msg_hashes": [glm_msg_hash(m) for m in messages],
                    "completion_tokens": max(1, int(usage.get("completion_tokens") or 1)),
                    "created_s": created_s,
                }
            )
            if line_no % 4000 == 0:
                print(f"[glm] indexed {line_no} lines / {len(records)} records", flush=True)
    print(f"[glm] index done records={len(records)} bad_lines={bad}", flush=True)
    return records


def reconstruct_glm_chains(
    records: list[dict[str, Any]],
    *,
    min_turns: int,
    break_gap_s: float,
) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        groups[rec["user_hash"]].append(rec)
    chains: list[list[dict[str, Any]]] = []
    for recs in groups.values():
        recs = sorted(
            recs,
            key=lambda r: (
                r["start_s"] is None,
                r["start_s"] or 0.0,
                r["line_no"],
            ),
        )
        cur: list[dict[str, Any]] = [recs[0]]
        pieces: list[list[dict[str, Any]]] = []

        def flush() -> None:
            if len(cur) >= min_turns:
                pieces.append(list(cur))

        for rec in recs[1:]:
            prev = cur[-1]
            gap = None
            if rec["start_s"] is not None and prev["start_s"] is not None:
                gap = rec["start_s"] - prev["start_s"]
            grow = is_hash_prefix(prev["msg_hashes"], rec["msg_hashes"])
            time_ok = rec["start_s"] is None or prev["start_s"] is None or rec["start_s"] >= prev["start_s"]
            gap_ok = gap is None or gap <= break_gap_s
            if grow and time_ok and gap_ok:
                cur.append(rec)
            else:
                flush()
                cur = [rec]
        flush()
        chains.extend(pieces)
    chains.sort(key=lambda c: (c[0]["line_no"], c[0]["trace_id"] or ""))
    return chains


def load_glm_payloads(
    path: Path, offsets: list[int]
) -> dict[int, dict[str, Any]]:
    need = set(offsets)
    out: dict[int, dict[str, Any]] = {}
    with path.open("rb") as f:
        while need:
            offset = f.tell()
            raw = f.readline()
            if not raw:
                break
            if offset not in need:
                continue
            obj = json.loads(raw)
            pb = json.loads(obj["prompt_body"])
            out[offset] = {
                "messages": list(pb.get("messages") or []),
                "tools": pb.get("tools"),
            }
            need.remove(offset)
    if need:
        raise RuntimeError(f"Missing {len(need)} GLM offsets in {path}")
    return out


def build_glm_session(
    chain: list[dict[str, Any]],
    payloads: dict[int, dict[str, Any]],
    *,
    jsonl_rel: str,
    gap_cap_s: float,
) -> tuple[list[Turn], SessionMeta]:
    user_h = chain[0]["user_hash"]
    session_id = f"glm:{user_h[:16]}:{str(chain[0]['trace_id'] or 'na')[:12]}"
    turns: list[Turn] = []
    for i, rec in enumerate(chain):
        payload = payloads[rec["offset"]]
        messages = sanitize_glm_messages(payload["messages"])
        if i == 0:
            pre_gap = 0.0
        else:
            prev = chain[i - 1]
            if rec["start_s"] is None or prev["start_s"] is None:
                pre_gap = 0.0
            else:
                delta = rec["start_s"] - prev["start_s"]
                prev_e2e = 0.0
                if prev["created_s"] is not None and prev["start_s"] is not None:
                    prev_e2e = max(0.0, prev["created_s"] - prev["start_s"])
                pre_gap = max(0.0, delta - prev_e2e)
            pre_gap = min(gap_cap_s, pre_gap)
        prompt_body: dict[str, Any] = {"messages": messages}
        if payload.get("tools"):
            prompt_body["tools"] = payload["tools"]
        turns.append(
            Turn(
                traffic_class="glm",
                session_id=session_id,
                turn_idx=i,
                session_start_s=0.0,
                pre_gap_s=round(pre_gap, 6),
                max_tokens=int(rec["completion_tokens"]),
                prompt_body=prompt_body,
                source={
                    "kind": "glm_online",
                    "inferred": True,
                    "jsonl": jsonl_rel,
                    "line_no": rec["line_no"],
                    "trace_id": rec["trace_id"],
                    "call_idx": i,
                },
            )
        )
    start0 = chain[0]["start_s"]
    startn = chain[-1]["start_s"]
    orig_span = 0.0
    if start0 is not None and startn is not None:
        orig_span = max(0.0, startn - start0)
    meta = SessionMeta(
        session_id=session_id,
        traffic_class="glm",
        session_start_s=0.0,
        n_turns=len(turns),
        orig_span_s=round(orig_span, 6),
        max_tokens_sum=sum(t.max_tokens for t in turns),
        source={
            "kind": "glm_online",
            "inferred": True,
            "method": "first_user_hash + messages exact prefix + start_time",
            "jsonl": jsonl_rel,
            "user_hash": user_h,
            "line_nos": [r["line_no"] for r in chain],
            "trace_ids": [r["trace_id"] for r in chain],
        },
    )
    return turns, meta


def is_valid_request_conv(conv: list[dict[str, Any]] | None) -> bool:
    if not conv:
        return False
    users = [u for u in conv if u.get("role") == "user"]
    assts = [u for u in conv if u.get("role") == "assistant"]
    if not users or not assts:
        return False
    if not (users[0].get("content") or "").strip():
        return False
    if not any((u.get("content") or "").strip() for u in assts):
        return False
    return True


def iter_wildchat_index(
    wildchat_dir: Path,
    *,
    max_turns: int | None = None,
) -> Iterator[dict[str, Any]]:
    data_dir = wildchat_dir / "data"
    files = sorted(data_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet under {data_dir}")
    for path in files:
        pf = pq.ParquetFile(path)
        row_base = 0
        for rg in range(pf.num_row_groups):
            table = pf.read_row_group(
                rg,
                columns=["conversation_hash", "turn", "conversation"],
            )
            hashes = table.column("conversation_hash").to_pylist()
            turns = table.column("turn").to_pylist()
            convs = table.column("conversation").to_pylist()
            for i, conv in enumerate(convs):
                if not is_valid_request_conv(conv):
                    continue
                n_asst = sum(1 for u in conv if u.get("role") == "assistant")
                n_turn = int(turns[i] or n_asst or 0)
                if max_turns is not None and max(n_asst, n_turn) > max_turns:
                    continue
                yield {
                    "parquet": path.name,
                    "row": row_base + i,
                    "conversation_hash": hashes[i],
                    "turn": n_turn,
                }
            row_base += len(hashes)
        print(f"[wildchat] indexed {path.name}", flush=True)


def load_wildchat_rows(
    wildchat_dir: Path, picks: list[dict[str, Any]]
) -> list[list[dict[str, Any]]]:
    by_file: dict[str, list[tuple[int, int]]] = {}
    for i, pick in enumerate(picks):
        by_file.setdefault(pick["parquet"], []).append((pick["row"], i))
    convs: list[list[dict[str, Any]] | None] = [None] * len(picks)
    data_dir = wildchat_dir / "data"
    for name, items in by_file.items():
        table = pq.read_table(data_dir / name, columns=["conversation"])
        col = table.column("conversation")
        for row, dest in items:
            convs[dest] = col[row].as_py()
    out: list[list[dict[str, Any]]] = []
    for conv in convs:
        if not conv:
            raise RuntimeError("Failed to reload a selected WildChat row")
        out.append(conv)
    return out


def build_request_session(
    conv: list[dict[str, Any]],
    pick: dict[str, Any],
    *,
    gap_cap_s: float,
    max_tokens_cap: int,
) -> tuple[list[Turn], SessionMeta] | None:
    session_id = (
        f"request:{pick['conversation_hash']}:{pick['parquet']}:{pick['row']}"
    )
    history: list[dict[str, Any]] = []
    turns: list[Turn] = []
    prev_asst_ts: float | None = None
    first_asst_ts: float | None = None
    last_asst_ts: float | None = None
    for utt in conv:
        role = utt.get("role")
        content = utt.get("content") or ""
        if role == "user":
            if not history and not str(content).strip():
                continue
            history.append({"role": "user", "content": content})
            continue
        if role != "assistant":
            continue
        if not history:
            continue
        ts = parse_ts(utt.get("timestamp"))
        if prev_asst_ts is None or ts is None:
            pre_gap = 0.0
        else:
            pre_gap = min(gap_cap_s, max(0.0, ts - prev_asst_ts))
        max_tokens = min(max_tokens_cap, estimate_tokens(str(content)))
        turns.append(
            Turn(
                traffic_class="request",
                session_id=session_id,
                turn_idx=len(turns),
                session_start_s=0.0,
                pre_gap_s=round(pre_gap, 6),
                max_tokens=max_tokens,
                prompt_body={"messages": [dict(m) for m in history]},
                source={
                    "kind": "wildchat",
                    "parquet": pick["parquet"],
                    "row": pick["row"],
                    "conversation_hash": pick["conversation_hash"],
                    "turn_identifier": utt.get("turn_identifier"),
                },
            )
        )
        history.append({"role": "assistant", "content": content})
        if ts is not None:
            if first_asst_ts is None:
                first_asst_ts = ts
            last_asst_ts = ts
            prev_asst_ts = ts
    if not turns:
        return None
    orig_span = 0.0
    if first_asst_ts is not None and last_asst_ts is not None:
        orig_span = max(0.0, last_asst_ts - first_asst_ts)
    meta = SessionMeta(
        session_id=session_id,
        traffic_class="request",
        session_start_s=0.0,
        n_turns=len(turns),
        orig_span_s=round(orig_span, 6),
        max_tokens_sum=sum(t.max_tokens for t in turns),
        source={
            "kind": "wildchat",
            "parquet": pick["parquet"],
            "row": pick["row"],
            "conversation_hash": pick["conversation_hash"],
            "orig_turn": pick["turn"],
        },
    )
    return turns, meta


def assign_starts(
    sessions: list[tuple[list[Turn], SessionMeta]],
    delta_s: float,
) -> None:
    for i, (turns, meta) in enumerate(sessions):
        t0 = round(i * delta_s, 6)
        meta.session_start_s = t0
        for turn in turns:
            turn.session_start_s = t0


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            f.write(line)
            f.write("\n")
            h.update(line.encode("utf-8"))
            h.update(b"\n")
    return h.hexdigest()


def summarize(sessions: list[SessionMeta], turns: list[Turn]) -> dict[str, Any]:
    by_cls: dict[str, list[SessionMeta]] = defaultdict(list)
    for s in sessions:
        by_cls[s.traffic_class].append(s)
    turn_by_cls: dict[str, int] = defaultdict(int)
    for t in turns:
        turn_by_cls[t.traffic_class] += 1
    last_start = max((s.session_start_s for s in sessions), default=0.0)
    out: dict[str, Any] = {
        "n_sessions": len(sessions),
        "n_turns": len(turns),
        "last_session_start_s": last_start,
        "n_sessions_by_class": {k: len(v) for k, v in sorted(by_cls.items())},
        "n_turns_by_class": dict(sorted(turn_by_cls.items())),
    }
    for cls, metas in by_cls.items():
        out[f"n_sessions_{cls}"] = len(metas)
        out[f"n_turns_{cls}"] = turn_by_cls[cls]
        out[f"{cls}_orig_span_s_p50"] = _p50([s.orig_span_s for s in metas])
        out[f"{cls}_single_turn"] = sum(1 for s in metas if s.n_turns == 1)
        out[f"{cls}_multi_turn"] = sum(1 for s in metas if s.n_turns >= 2)
    return out


def _p50(xs: list[float]) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[len(xs) // 2], 3)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent-dir", type=Path, default=DEFAULT_AGENT_DIR)
    p.add_argument("--skillsbench-root", type=Path, default=SKILLSBENCH_V11)
    p.add_argument("--wildchat-dir", type=Path, default=DEFAULT_WILDCHAT_DIR)
    p.add_argument("--glm-jsonl", type=Path, default=DEFAULT_GLM_JSONL)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-agent", type=int, default=None, help="legacy alias of --n-openhands")
    p.add_argument("--n-openhands", type=int, default=None)
    p.add_argument(
        "--n-glm",
        type=int,
        default=0,
        help="GLM inferred sessions to keep; negative means all chains",
    )
    p.add_argument("--n-request", type=int, default=None)
    p.add_argument("--request-per-agent", type=float, default=None)
    p.add_argument("--min-glm-turns", type=int, default=4)
    p.add_argument(
        "--openhands-max-turns",
        type=int,
        default=None,
        help="truncate each OpenHands trajectory to the first N turns",
    )
    p.add_argument(
        "--min-openhands-prefix-turns",
        type=int,
        default=None,
        help="keep only OpenHands trajectories with this many initial exact-prefix turns",
    )
    p.add_argument("--glm-break-gap-s", type=float, default=180.0)
    p.add_argument("--glm-gap-cap-s", type=float, default=120.0)
    p.add_argument(
        "--prefix-diverse",
        action="store_true",
        help="keep agent sessions whose system strings share < --max-system-lcp-chars",
    )
    p.add_argument(
        "--max-system-lcp-chars",
        type=int,
        default=256,
        help="reject a candidate if LCP with any kept system is this many chars or more",
    )
    p.add_argument(
        "--max-openhands",
        type=int,
        default=1,
        help="cap OpenHands kept under --prefix-diverse (they share one scaffold)",
    )
    p.add_argument(
        "--dedup-openhands",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="unique Flash trajectories across runners (default: on when GLM is included)",
    )
    p.add_argument("--delta-agent-s", type=float, default=15.0)
    p.add_argument("--delta-openhands-s", type=float, default=None)
    p.add_argument("--delta-glm-s", type=float, default=None)
    p.add_argument("--delta-request-s", type=float, default=5.0)
    p.add_argument("--request-gap-cap-s", type=float, default=900.0)
    p.add_argument(
        "--request-max-turns",
        type=int,
        default=None,
        help="drop WildChat conversations with more assistant turns than this",
    )
    p.add_argument("--request-max-tokens-cap", type=int, default=4096)
    p.add_argument("--name", default="mix_a8_r32")
    args = p.parse_args()

    prefix_diverse = bool(args.prefix_diverse)
    n_openhands = (
        args.n_openhands if args.n_openhands is not None else (args.n_agent if args.n_agent is not None else 8)
    )
    three_class = int(args.n_glm) != 0 or prefix_diverse
    dedup = args.dedup_openhands if args.dedup_openhands is not None else three_class
    oh_class = "openhands" if three_class else "agent"
    delta_oh = float(args.delta_openhands_s if args.delta_openhands_s is not None else args.delta_agent_s)
    delta_glm = float(args.delta_glm_s if args.delta_glm_s is not None else args.delta_agent_s)
    max_lcp = int(args.max_system_lcp_chars)

    agent_dir = args.agent_dir if args.agent_dir.is_absolute() else REPO_ROOT / args.agent_dir
    skillsbench_root = (
        args.skillsbench_root
        if args.skillsbench_root.is_absolute()
        else REPO_ROOT / args.skillsbench_root
    )
    wildchat_dir = (
        args.wildchat_dir if args.wildchat_dir.is_absolute() else REPO_ROOT / args.wildchat_dir
    )
    glm_jsonl = args.glm_jsonl if args.glm_jsonl.is_absolute() else REPO_ROOT / args.glm_jsonl
    out_dir = args.out_dir if args.out_dir.is_absolute() else REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    flash_configs = [p.name for p in list_flash_configs(skillsbench_root)]
    prefix_note: dict[str, Any] | None = None
    chosen_oh: list[tuple[str | None, Path]] = []
    chosen_chains: list[list[dict[str, Any]]] = []
    glm_rel = ""
    n_glm_chains = 0
    records: list[dict[str, Any]] = []

    if prefix_diverse:
        print(
            f"[prefix] diverse systems LCP<{max_lcp} chars; "
            f"max_openhands={args.max_openhands}",
            flush=True,
        )
        print(f"[openhands] unique Flash trajectories under {skillsbench_root}", flush=True)
        print(f"[openhands] configs={flash_configs}", flush=True)
        oh_cands: list[dict[str, Any]] = []
        for digest, path in list_openhands_unique(skillsbench_root):
            n_turns = count_jsonl_rows(path)
            if n_turns <= 0:
                continue
            oh_cands.append(
                {
                    "kind": "openhands",
                    "id": str(path),
                    "n_turns": n_turns,
                    "span": 0.0,
                    "system": peek_openhands_system(path),
                    "digest": digest,
                    "path": path,
                }
            )
        if not glm_jsonl.is_file():
            raise SystemExit(f"Missing GLM jsonl: {glm_jsonl}")
        glm_rel = str(glm_jsonl.relative_to(REPO_ROOT))
        print(f"[glm] infer sessions from {glm_rel}", flush=True)
        records = index_glm_records(glm_jsonl)
        chains = reconstruct_glm_chains(
            records,
            min_turns=int(args.min_glm_turns),
            break_gap_s=float(args.glm_break_gap_s),
        )
        n_glm_chains = len(chains)
        print(
            f"[glm] inferred_chains(n>={args.min_glm_turns}, break_gap={args.glm_break_gap_s}s)="
            f"{n_glm_chains}",
            flush=True,
        )
        glm_cands: list[dict[str, Any]] = []
        for chain in chains:
            start0 = chain[0]["start_s"]
            startn = chain[-1]["start_s"]
            span = 0.0
            if start0 is not None and startn is not None:
                span = max(0.0, startn - start0)
            glm_cands.append(
                {
                    "kind": "glm",
                    "id": f"{chain[0]['line_no']}:{chain[0].get('trace_id') or ''}",
                    "n_turns": len(chain),
                    "span": span,
                    "system": chain[0].get("system") or "",
                    "chain": chain,
                }
            )
        kept = greedy_prefix_diverse(
            oh_cands + glm_cands,
            max_lcp_chars=max_lcp,
            max_per_kind={"openhands": int(args.max_openhands)},
        )
        chosen_oh = [(c["digest"], c["path"]) for c in kept if c["kind"] == "openhands"]
        chosen_chains = [c["chain"] for c in kept if c["kind"] == "glm"]
        if args.n_glm > 0:
            chosen_chains = chosen_chains[: int(args.n_glm)]
        systems = [str(c.get("system") or "") for c in kept]
        prefix_note = {
            "max_system_lcp_chars": max_lcp,
            "max_openhands": int(args.max_openhands),
            "n_openhands_candidates": len(oh_cands),
            "n_glm_candidates": len(glm_cands),
            "n_kept": len(kept),
            "n_kept_openhands": len(chosen_oh),
            "n_kept_glm": len(chosen_chains),
            "max_pairwise_system_lcp_chars": max_pairwise_lcp(systems),
            "note": (
                "OpenHands trajectories share one scaffold, so at most --max-openhands "
                "are kept. GLM chains are inferred sessions; a candidate is rejected if "
                f"its system LCP with any kept system is >= {max_lcp} characters."
            ),
        }
        print(
            f"[prefix] kept openhands={len(chosen_oh)} glm={len(chosen_chains)} "
            f"max_pairwise_lcp={prefix_note['max_pairwise_system_lcp_chars']}",
            flush=True,
        )
        chosen_oh.sort(key=lambda kv: str(kv[1]))
        chosen_chains.sort(key=lambda c: (c[0]["line_no"], c[0]["trace_id"] or ""))
    elif dedup:
        print(f"[openhands] unique Flash trajectories under {skillsbench_root}", flush=True)
        print(f"[openhands] configs={flash_configs}", flush=True)
        pool = list_openhands_unique(skillsbench_root)
        if args.min_openhands_prefix_turns is not None:
            min_prefix_turns = int(args.min_openhands_prefix_turns)
            eligible: list[tuple[str, Path]] = []
            for digest, path in pool:
                candidate = load_agent_session(
                    path,
                    rel_root=REPO_ROOT,
                    traffic_class=oh_class,
                    content_sha256=digest,
                )
                if (
                    candidate is not None
                    and strict_prefix_turn_count(candidate[0]) >= min_prefix_turns
                ):
                    eligible.append((digest, path))
            print(
                f"[openhands] strict_prefix_turns>={min_prefix_turns}: "
                f"{len(eligible)} / {len(pool)}",
                flush=True,
            )
            pool = eligible
        if len(pool) < n_openhands:
            raise SystemExit(f"Need {n_openhands} unique OpenHands trials, found {len(pool)}")
        chosen_oh = rng.sample(pool, n_openhands)
        chosen_oh.sort(key=lambda kv: str(kv[1]))
        print(
            f"[openhands] unique_pool={len(pool)} sampled={n_openhands} class={oh_class}",
            flush=True,
        )
    else:
        print(f"[openhands] list trials under {agent_dir} (no content dedup)", flush=True)
        trials = list_agent_trials(agent_dir)
        if len(trials) < n_openhands:
            raise SystemExit(f"Need {n_openhands} agent trials, found {len(trials)}")
        chosen_paths = rng.sample(trials, n_openhands)
        chosen_oh = [(None, path) for path in sorted(chosen_paths)]

    openhands_sessions: list[tuple[list[Turn], SessionMeta]] = []
    for digest, path in chosen_oh:
        loaded = load_agent_session(
            path,
            rel_root=REPO_ROOT,
            traffic_class=oh_class,
            content_sha256=digest,
        )
        if loaded is None:
            raise SystemExit(f"Empty OpenHands trajectory: {path}")
        if args.min_openhands_prefix_turns is not None:
            prefix_turns = strict_prefix_turn_count(loaded[0])
            if prefix_turns < int(args.min_openhands_prefix_turns):
                raise SystemExit(
                    f"OpenHands strict prefix too short ({prefix_turns}): {path}"
                )
            loaded = cap_session_turns(loaded, prefix_turns)
        loaded = cap_session_turns(loaded, args.openhands_max_turns)
        print(
            f"[{oh_class}] {loaded[1].source['config']}/{loaded[1].source['task_id']} "
            f"turns={loaded[1].n_turns} span={loaded[1].orig_span_s:.1f}s",
            flush=True,
        )
        openhands_sessions.append(loaded)
    assign_starts(openhands_sessions, delta_oh)

    glm_sessions: list[tuple[list[Turn], SessionMeta]] = []
    if three_class:
        if not glm_jsonl.is_file():
            raise SystemExit(f"Missing GLM jsonl: {glm_jsonl}")
        if not glm_rel:
            glm_rel = str(glm_jsonl.relative_to(REPO_ROOT))
        if not prefix_diverse:
            print(f"[glm] infer sessions from {glm_rel}", flush=True)
            records = index_glm_records(glm_jsonl)
            chains = reconstruct_glm_chains(
                records,
                min_turns=int(args.min_glm_turns),
                break_gap_s=float(args.glm_break_gap_s),
            )
            n_glm_chains = len(chains)
            print(
                f"[glm] inferred_chains(n>={args.min_glm_turns}, break_gap={args.glm_break_gap_s}s)="
                f"{n_glm_chains}",
                flush=True,
            )
            if args.n_glm < 0 or args.n_glm >= n_glm_chains:
                chosen_chains = chains
            else:
                if n_glm_chains < args.n_glm:
                    raise SystemExit(f"Need {args.n_glm} GLM sessions, found {n_glm_chains}")
                chosen_chains = rng.sample(chains, args.n_glm)
            chosen_chains.sort(key=lambda c: (c[0]["line_no"], c[0]["trace_id"] or ""))
            print(f"[glm] selected {len(chosen_chains)} / {n_glm_chains} chains", flush=True)
        if not chosen_chains:
            raise SystemExit("No GLM sessions selected")
        offsets = [rec["offset"] for chain in chosen_chains for rec in chain]
        print(f"[glm] reload {len(offsets)} prompts", flush=True)
        payloads = load_glm_payloads(glm_jsonl, offsets)
        for i, chain in enumerate(chosen_chains, 1):
            loaded = build_glm_session(
                chain,
                payloads,
                jsonl_rel=glm_rel,
                gap_cap_s=float(args.glm_gap_cap_s),
            )
            glm_sessions.append(loaded)
            if i == 1 or i % 500 == 0 or i == len(chosen_chains):
                print(
                    f"[glm] built {i}/{len(chosen_chains)} "
                    f"last_turns={loaded[1].n_turns} span={loaded[1].orig_span_s:.1f}s",
                    flush=True,
                )
        assign_starts(glm_sessions, delta_glm)

    n_agent_sessions = len(openhands_sessions) + len(glm_sessions)
    if args.request_per_agent is not None:
        n_request = int(round(float(args.request_per_agent) * n_agent_sessions))
    elif args.n_request is not None:
        n_request = int(args.n_request)
    else:
        n_request = 32
    print(
        f"[counts] openhands={len(openhands_sessions)} glm={len(glm_sessions)} "
        f"request={n_request}",
        flush=True,
    )

    print("[wildchat] index valid conversations", flush=True)
    candidates = list(
        iter_wildchat_index(wildchat_dir, max_turns=args.request_max_turns)
    )
    print(
        f"[wildchat] valid={len(candidates)} max_turns={args.request_max_turns}",
        flush=True,
    )
    if len(candidates) < n_request:
        raise SystemExit(f"Need {n_request} request sessions, found {len(candidates)}")
    rng.shuffle(candidates)
    picks = candidates[:n_request]
    convs = load_wildchat_rows(wildchat_dir, picks)

    request_sessions: list[tuple[list[Turn], SessionMeta]] = []
    for pick, conv in zip(picks, convs):
        loaded = build_request_session(
            conv,
            pick,
            gap_cap_s=args.request_gap_cap_s,
            max_tokens_cap=args.request_max_tokens_cap,
        )
        if loaded is None:
            raise SystemExit(f"Failed to expand WildChat row {pick}")
        request_sessions.append(loaded)
    assign_starts(request_sessions, args.delta_request_s)

    all_sessions = openhands_sessions + glm_sessions + request_sessions
    metas = [m for _, m in all_sessions]
    turns: list[Turn] = []
    for ts, _meta in all_sessions:
        turns.extend(ts)

    workload_rows = [asdict(t) for t in turns]
    session_rows = [asdict(m) for m in metas]
    t0 = time.time()
    workload_sha = write_jsonl(out_dir / "workload.jsonl", workload_rows)
    sessions_sha = write_jsonl(out_dir / "sessions.jsonl", session_rows)

    parquet_files = sorted({p["parquet"] for p in picks})
    source_hashes: dict[str, Any] = {
        "openhands_jsonl": {
            m.source["path"]: m.source.get("content_sha256")
            or sha256_file(REPO_ROOT / m.source["path"])
            for m in metas
            if m.traffic_class in {"agent", "openhands"}
        },
        "wildchat_parquet": {
            name: sha256_file(wildchat_dir / "data" / name) for name in parquet_files
        },
    }
    if three_class:
        source_hashes["glm_jsonl"] = {glm_rel: sha256_file(glm_jsonl)}
    summary = summarize(metas, turns)
    spec = {
        "name": args.name,
        "created_unix": t0,
        "seed": args.seed,
        "n_openhands": len(openhands_sessions),
        "n_glm": len(glm_sessions),
        "n_request": n_request,
        "n_agent": n_agent_sessions,
        "arrival": {
            "type": "staggered",
            "delta_agent_s": args.delta_agent_s,
            "delta_openhands_s": delta_oh,
            "delta_glm_s": delta_glm if three_class else None,
            "delta_request_s": args.delta_request_s,
            "note": (
                "Each traffic_class starts at t=0 and staggers with its own Δ. "
                "OpenHands and GLM therefore overlap. Replay may override Δ. "
                "Counts are frozen session lists, not a renewal process."
            ),
        },
        "gap": {
            "openhands": "response.timestamp -> next request.timestamp",
            "glm": (
                "inferred: max(0, min(cap, Δstart_time - (response.created - start_time))); "
                f"cap_s={args.glm_gap_cap_s}; split chain if Δstart_time > {args.glm_break_gap_s}s"
            ),
            "request": (
                f"assistant timestamp diff, cap_s={args.request_gap_cap_s}"
                + (
                    f", max_turns={args.request_max_turns}"
                    if args.request_max_turns is not None
                    else ""
                )
            ),
            "agent": "response.timestamp -> next request.timestamp",
        },
        "glm_inference": None
        if not three_class
        else {
            "official_session_id": False,
            "method": (
                "Group by sha256(first user content). Sort by start_time. "
                "Adjacent records join a chain iff messages are an exact prefix "
                f"and Δstart_time <= {args.glm_break_gap_s}s. "
                f"Keep chains with n_turns >= {args.min_glm_turns}."
            ),
            "n_inferred_chains": n_glm_chains,
            "min_glm_turns": int(args.min_glm_turns),
            "break_gap_s": float(args.glm_break_gap_s),
            "source": glm_rel,
            "prefix_diverse": prefix_note,
        },
        "request_max_tokens": {
            "method": "cjk=1, other=chars/4",
            "cap": args.request_max_tokens_cap,
        },
        "sources": {
            "openhands_dedup": dedup,
            "openhands_max_turns": args.openhands_max_turns,
            "min_openhands_prefix_turns": args.min_openhands_prefix_turns,
            "prefix_diverse": bool(prefix_diverse),
            "max_system_lcp_chars": max_lcp if prefix_diverse else None,
            "flash_configs": flash_configs if dedup or prefix_diverse else [agent_dir.name],
            "skillsbench_root": str(skillsbench_root.relative_to(REPO_ROOT)),
            "agent_dir": str(agent_dir.relative_to(REPO_ROOT)),
            "wildchat": WILDCHAT_REPO,
            "wildchat_dir": str(wildchat_dir.relative_to(REPO_ROOT)),
            "glm_jsonl": glm_rel or None,
        },
        "openhands_sessions": [asdict(m) for _, m in openhands_sessions],
        "glm_sessions": [asdict(m) for _, m in glm_sessions],
        "agent_sessions": [asdict(m) for _, m in openhands_sessions]
        if not three_class
        else [asdict(m) for _, m in openhands_sessions + glm_sessions],
        "request_sessions": [asdict(m) for _, m in request_sessions],
        "summary": summary,
    }
    spec_text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "spec.json").write_text(spec_text, encoding="utf-8")
    spec_sha = hashlib.sha256(spec_text.encode("utf-8")).hexdigest()

    manifest = {
        "name": args.name,
        "created_unix": t0,
        "workload_jsonl_sha256": workload_sha,
        "sessions_jsonl_sha256": sessions_sha,
        "spec_json_sha256": spec_sha,
        "n_turns": summary["n_turns"],
        "n_sessions_by_class": summary["n_sessions_by_class"],
        "source_sha256": source_hashes,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2), flush=True)
    print(f"[done] {out_dir} workload_sha256={workload_sha[:16]}...", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
