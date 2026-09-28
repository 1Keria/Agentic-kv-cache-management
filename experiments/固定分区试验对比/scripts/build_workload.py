#!/usr/bin/env python3
"""Build a token-balanced OpenHands/WildChat workload for partition validation.

The builder reuses a frozen workload and its successful DeepSeek-V4-Flash
replay. It balances the two classes by the sum of each selected session's
final prompt-token count, which approximates the committed KV footprint much
better than call counts or serialized character counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))

from build_mix_workload import (  # noqa: E402
    SessionMeta,
    Turn,
    sha256_file,
    summarize,
    write_jsonl,
)


DEFAULT_SOURCE_WORKLOAD = REPO_ROOT / "workloads/ratio_train_v4flash/agent_050"
DEFAULT_TOKEN_REPLAY = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/ratio_daily_models/agent_050/replay/"
    "run_mix_train_lru/replay.jsonl"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "experiments/固定分区试验对比/data/token_balanced_openhands_wildchat"
)
GENERATED_FILENAMES = {
    "README.md",
    "manifest.json",
    "sessions.jsonl",
    "spec.json",
    "workload.jsonl",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def session_identity(meta: SessionMeta) -> str:
    source = meta.source or {}
    return str(source.get("content_sha256") or source.get("parent_session_id") or meta.session_id)


def select_agent_sessions(
    candidates: list[tuple[list[Turn], SessionMeta]],
    final_prompt_tokens: dict[str, int],
    target_tokens: int,
) -> tuple[list[tuple[list[Turn], SessionMeta]], int]:
    unique: dict[str, tuple[list[Turn], SessionMeta]] = {}
    for session in candidates:
        turns, meta = session
        identity = session_identity(meta)
        current = unique.get(identity)
        if current is None:
            unique[identity] = session
            continue
        current_meta = current[1]
        new_rank = (
            final_prompt_tokens[meta.session_id],
            meta.n_turns,
            meta.session_id,
        )
        current_rank = (
            final_prompt_tokens[current_meta.session_id],
            current_meta.n_turns,
            current_meta.session_id,
        )
        if new_rank > current_rank:
            unique[identity] = session

    ordered = sorted(unique.values(), key=lambda item: item[1].session_id)
    previous: dict[int, tuple[int, int] | None] = {0: None}
    for index, (_, meta) in enumerate(ordered):
        weight = final_prompt_tokens[meta.session_id]
        for total in sorted(tuple(previous), reverse=True):
            next_total = total + weight
            if next_total not in previous:
                previous[next_total] = (total, index)

    best_total = min(
        previous,
        key=lambda total: (
            abs(total - target_tokens),
            total > target_tokens,
            total,
        ),
    )
    chosen_indices: list[int] = []
    cursor = best_total
    while cursor:
        link = previous[cursor]
        assert link is not None
        cursor, index = link
        chosen_indices.append(index)
    return [ordered[index] for index in sorted(chosen_indices)], best_total


def cap_session(
    session: tuple[list[Turn], SessionMeta],
    *,
    gap_cap_s: float,
    max_output_tokens: int,
) -> tuple[list[Turn], SessionMeta]:
    turns, meta = session
    capped = [
        replace(
            turn,
            pre_gap_s=(
                0.0
                if turn.turn_idx == 0
                else round(min(float(turn.pre_gap_s), gap_cap_s), 6)
            ),
            max_tokens=min(int(turn.max_tokens), max_output_tokens),
        )
        for turn in turns
    ]
    return (
        capped,
        replace(
            meta,
            orig_span_s=round(sum(turn.pre_gap_s for turn in capped), 6),
            max_tokens_sum=sum(turn.max_tokens for turn in capped),
        ),
    )


def assign_mixed_waves(
    sessions: list[tuple[list[Turn], SessionMeta]],
    *,
    horizon_s: float,
    wave_count: int,
    wave_width_s: float,
    seed: int,
) -> list[tuple[list[Turn], SessionMeta]]:
    by_class: dict[str, list[int]] = defaultdict(list)
    for index, (_, meta) in enumerate(sessions):
        by_class[meta.traffic_class].append(index)

    random_generator = random.Random(seed)
    waves: list[list[int]] = [[] for _ in range(wave_count)]
    for indices in by_class.values():
        shuffled = list(indices)
        random_generator.shuffle(shuffled)
        for position, index in enumerate(shuffled):
            waves[position % wave_count].append(index)

    starts: dict[int, float] = {}
    for wave_index, indices in enumerate(waves):
        indices.sort(
            key=lambda index: (
                sessions[index][1].traffic_class,
                sessions[index][1].session_id,
            )
        )
        anchor = 0.0 if wave_count == 1 else wave_index * horizon_s / (wave_count - 1)
        wave_start = min(anchor, max(0.0, horizon_s - wave_width_s))
        spacing = 0.0 if len(indices) <= 1 else wave_width_s / (len(indices) - 1)
        for position, index in enumerate(indices):
            starts[index] = round(wave_start + position * spacing, 6)

    assigned: list[tuple[list[Turn], SessionMeta]] = []
    for index, (turns, meta) in enumerate(sessions):
        start = starts[index]
        assigned.append(
            (
                [replace(turn, session_start_s=start) for turn in turns],
                replace(meta, session_start_s=start),
            )
        )
    return assigned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-workload", type=Path, default=DEFAULT_SOURCE_WORKLOAD)
    parser.add_argument("--token-replay", type=Path, default=DEFAULT_TOKEN_REPLAY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--horizon-s", type=float, default=1800.0)
    parser.add_argument("--wave-count", type=int, default=6)
    parser.add_argument("--wave-width-s", type=float, default=20.0)
    parser.add_argument("--gap-cap-s", type=float, default=30.0)
    parser.add_argument("--max-output-tokens", type=int, default=208)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace only the known generated files in the output directory",
    )
    args = parser.parse_args()

    source_workload = resolve(args.source_workload)
    token_replay = resolve(args.token_replay)
    out_dir = resolve(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        existing_names = {path.name for path in out_dir.iterdir()}
        unexpected_names = existing_names - GENERATED_FILENAMES
        if not args.overwrite or unexpected_names:
            details = (
                f"; unexpected entries: {sorted(unexpected_names)}"
                if unexpected_names
                else "; pass --overwrite to replace the frozen generated files"
            )
            raise SystemExit(f"Output directory is not replaceable: {out_dir}{details}")
        for filename in sorted(existing_names):
            path = out_dir / filename
            if not path.is_file():
                raise SystemExit(f"Refusing to replace non-file output entry: {path}")
            path.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    source_turn_rows = read_jsonl(source_workload / "workload.jsonl")
    source_meta_rows = read_jsonl(source_workload / "sessions.jsonl")
    replay_rows = read_jsonl(token_replay)

    replay_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in replay_rows:
        if row.get("status") != "200" or row.get("error"):
            continue
        replay_by_session[str(row["session_id"])].append(row)

    final_prompt_tokens: dict[str, int] = {}
    for session_id, rows in replay_by_session.items():
        rows.sort(key=lambda row: int(row["turn_index"]))
        final_prompt_tokens[session_id] = int(rows[-1]["prompt_tokens"])

    turns_by_session: dict[str, list[Turn]] = defaultdict(list)
    for row in source_turn_rows:
        turns_by_session[str(row["session_id"])].append(Turn(**row))

    sessions: list[tuple[list[Turn], SessionMeta]] = []
    for row in source_meta_rows:
        meta = SessionMeta(**row)
        turns = sorted(turns_by_session[meta.session_id], key=lambda turn: turn.turn_idx)
        if len(turns) != meta.n_turns:
            raise SystemExit(f"Turn-count mismatch for {meta.session_id}")
        if meta.session_id not in final_prompt_tokens:
            raise SystemExit(f"Missing successful token replay for {meta.session_id}")
        sessions.append((turns, meta))

    request_sessions = [session for session in sessions if session[1].traffic_class == "request"]
    agent_candidates = [session for session in sessions if session[1].traffic_class == "openhands"]
    if not request_sessions or not agent_candidates:
        raise SystemExit("Source workload must contain OpenHands and request sessions")

    request_final_tokens = sum(
        final_prompt_tokens[meta.session_id] for _, meta in request_sessions
    )
    selected_agents, agent_final_tokens = select_agent_sessions(
        agent_candidates,
        final_prompt_tokens,
        request_final_tokens,
    )
    selected = [
        cap_session(
            session,
            gap_cap_s=float(args.gap_cap_s),
            max_output_tokens=int(args.max_output_tokens),
        )
        for session in selected_agents + request_sessions
    ]
    selected = assign_mixed_waves(
        selected,
        horizon_s=float(args.horizon_s),
        wave_count=int(args.wave_count),
        wave_width_s=float(args.wave_width_s),
        seed=int(args.seed),
    )

    turns = sorted(
        (turn for group, _ in selected for turn in group),
        key=lambda turn: (turn.session_start_s, turn.session_id, turn.turn_idx),
    )
    metas = sorted(
        (meta for _, meta in selected),
        key=lambda meta: (meta.session_start_s, meta.session_id),
    )
    workload_sha = write_jsonl(out_dir / "workload.jsonl", [asdict(turn) for turn in turns])
    sessions_sha = write_jsonl(out_dir / "sessions.jsonl", [asdict(meta) for meta in metas])
    summary = summarize(metas, turns)

    selected_agent_ids = {meta.session_id for _, meta in selected_agents}
    selected_token_rows = {
        session_id: {
            "final_prompt_tokens": final_prompt_tokens[session_id],
            "n_turns": len(replay_by_session[session_id]),
        }
        for session_id in sorted(
            selected_agent_ids | {meta.session_id for _, meta in request_sessions}
        )
    }
    spec = {
        "name": out_dir.name,
        "protocol": "partition-quick-openhands-request-token-balanced-v1",
        "purpose": (
            "Quick two-run validation of unified LRU versus an offline-selected "
            "fixed Agent/request KV-token partition. GLM is intentionally excluded "
            "and reserved for later online validation."
        ),
        "seed": int(args.seed),
        "selection": {
            "metric": "sum of final prompt_tokens per selected session",
            "token_source": "successful DeepSeek-V4-Flash replay usage",
            "request_policy": "keep every request session in the source workload",
            "openhands_policy": (
                "keep at most one strict segment per source trajectory and choose "
                "the exact subset whose final prompt-token sum is closest to request"
            ),
            "request_final_prompt_tokens": request_final_tokens,
            "openhands_final_prompt_tokens": agent_final_tokens,
            "absolute_difference_tokens": abs(agent_final_tokens - request_final_tokens),
            "selected_openhands_session_ids": sorted(selected_agent_ids),
            "token_rows": selected_token_rows,
        },
        "transformations": {
            "intra_session_gap_cap_s": float(args.gap_cap_s),
            "max_output_tokens_per_call": int(args.max_output_tokens),
            "prompt_bodies_unchanged": True,
            "session_boundaries_unchanged": True,
        },
        "arrival": {
            "type": "frozen_mixed_waves",
            "horizon_s": float(args.horizon_s),
            "wave_count": int(args.wave_count),
            "wave_width_s": float(args.wave_width_s),
            "note": "Replay with --arrival frozen; starts are stored in workload.jsonl.",
        },
        "sources": {
            "source_workload": str(source_workload.relative_to(REPO_ROOT)),
            "token_replay": str(token_replay.relative_to(REPO_ROOT)),
            "source_workload_sha256": sha256_file(source_workload / "workload.jsonl"),
            "source_sessions_sha256": sha256_file(source_workload / "sessions.jsonl"),
            "token_replay_sha256": sha256_file(token_replay),
        },
        "summary": summary,
    }
    spec_text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "spec.json").write_text(spec_text, encoding="utf-8")
    spec_sha = hashlib.sha256(spec_text.encode()).hexdigest()
    manifest = {
        "name": out_dir.name,
        "workload_jsonl_sha256": workload_sha,
        "sessions_jsonl_sha256": sessions_sha,
        "spec_json_sha256": spec_sha,
        "n_turns": summary["n_turns"],
        "n_sessions_by_class": summary["n_sessions_by_class"],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme = f"""# {out_dir.name}

用于固定分区机制快速验证的冻结混合流量，仅包含 OpenHands 和 WildChat，不包含 GLM。

## 选择原则

- token 依据：已有 DeepSeek V4 Flash 实际重放返回的 `prompt_tokens`；
- 普通请求：保留源 workload 中全部 {len(request_sessions)} 个 WildChat Session；
- OpenHands：同一原始轨迹最多保留一个严格前缀段，通过确定性子集选择配平最终上下文；
- OpenHands 最终 prompt token：{agent_final_tokens:,}；
- 普通请求最终 prompt token：{request_final_tokens:,}；
- 两类差值：{abs(agent_final_tokens - request_final_tokens):,} token。

调用次数不做均衡，因为固定分区按 KV token 容量划分，而不是按请求次数划分。

## 规模

- OpenHands：{summary['n_sessions_by_class'].get('openhands', 0)} 个 Session，{summary['n_turns_by_class'].get('openhands', 0)} 次调用；
- 普通请求：{summary['n_sessions_by_class'].get('request', 0)} 个 Session，{summary['n_turns_by_class'].get('request', 0)} 次调用；
- 总计：{summary['n_sessions']} 个 Session，{summary['n_turns']} 次调用；
- Session 启动时间冻结为 6 个混合波次，覆盖 30 分钟；
- Session 内等待最多 30 秒；每次生成最多 {int(args.max_output_tokens)} token；prompt 内容保持不变。

## 回放

```bash
bash experiments/固定分区试验对比/scripts/replay_workload.sh
```

离线选择固定分区比例和两次 GPU 实验都必须使用本目录同一份 `workload.jsonl`。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(
        f"[balance] openhands={agent_final_tokens} request={request_final_tokens} "
        f"difference={abs(agent_final_tokens - request_final_tokens)}"
    )
    print(f"[done] {out_dir} workload_sha256={workload_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
