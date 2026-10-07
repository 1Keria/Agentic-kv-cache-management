#!/usr/bin/env python3
"""Replay a phased workload at predetermined request arrival times.

Unlike ``replay_partition_phases.py``, this runner never waits for a previous
turn to finish before issuing the next scheduled turn.  The schedule is
derived once from the workload and is therefore identical for every cache
policy.  It is intended for separating cache effects from closed-loop
completion-time feedback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
import replay_mix_workload as replay


async def run(args: argparse.Namespace) -> None:
    workload = args.workload_dir.resolve()
    replay.verify_manifest(workload, workload / "workload.jsonl")
    sessions = dict(replay.load_sessions(workload / "workload.jsonl"))
    plan = json.loads((workload / "replay_plan.json").read_text())
    assigned = [sid for phase in plan["phases"] for sid in phase["session_ids"]]
    if len(set(assigned)) != len(assigned) or set(assigned) != set(sessions):
        raise ValueError("each session must belong to exactly one phase")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    replay.health_check(args.base_url)
    replay.maybe_flush_cache(args.base_url, True)
    response = replay.requests.get(f"{args.base_url}/v1/models", timeout=30)
    response.raise_for_status()
    model = response.json()["data"][0]["id"]
    client = replay.AsyncOpenAI(
        base_url=f"{args.base_url}/v1", api_key="EMPTY", timeout=600, max_retries=0
    )

    phase_starts = {
        "ordinary_warm": 0.0,
        "agent_pressure": float(args.agent_phase_start_s),
        "ordinary_return": float(args.return_phase_start_s),
    }
    schedule: list[dict] = []
    phase_meta: list[dict] = []
    for phase in plan["phases"]:
        name = str(phase["name"])
        if name not in phase_starts:
            raise ValueError(f"unsupported phase in replay_plan.json: {name}")
        sids = list(phase["session_ids"])
        origin = min(float(sessions[sid][0].session_start_s) for sid in sids)
        for sid_index, sid in enumerate(sids):
            turns = sessions[sid]
            # Preserve the workload's relative start for the serial ordinary
            # sessions.  Agent sessions get a deterministic stagger so that
            # the full workload does not arrive as one artificial burst.
            if name == "agent_pressure":
                session_offset = sid_index * float(args.session_stagger_s)
            else:
                session_offset = float(turns[0].session_start_s) - origin
            elapsed = 0.0
            for turn in turns:
                if turn.turn_idx > 0:
                    elapsed += max(0.0, float(turn.pre_gap_s) * args.gap_scale)
                target_s = phase_starts[name] + session_offset + elapsed
                schedule.append(
                    {
                        "target_s": target_s,
                        "phase": name,
                        "session_id": sid,
                        "turn": turn,
                    }
                )
        phase_meta.append(
            {
                "phase": name,
                "start_s": phase_starts[name],
                "session_ids": sids,
                "n_requests": sum(len(sessions[sid]) for sid in sids),
            }
        )
    schedule.sort(key=lambda row: (row["target_s"], row["turn"].index))

    handle = (output / "replay.jsonl").open("w", encoding="utf-8")
    write_lock = asyncio.Lock()
    results: list[replay.RequestResult] = []
    started = time.perf_counter()

    async def execute(item: dict) -> None:
        turn = item["turn"]
        target_s = float(item["target_s"])
        delay = target_s - (time.perf_counter() - started)
        if delay > 0:
            await asyncio.sleep(delay)
        queued = time.perf_counter()
        rec = replay.RequestResult(
            index=turn.index,
            trace_id=f"{turn.session_id}#{turn.turn_idx}",
            start_time_orig=f"{target_s:.6f}",
            t_sched_ms=target_s * 1000.0,
            s_time_ms=(queued - started) * 1000.0,
            s_time_drift_ms=(queued - started - target_s) * 1000.0,
            traffic_class=turn.traffic_class,
            session_id=turn.session_id,
            turn_index=turn.turn_idx,
            pre_gap_s=turn.pre_gap_s,
            sleep_before_s=(turn.pre_gap_s * args.gap_scale if turn.turn_idx > 0 else 0.0),
            max_tokens=args.max_output_tokens_override or turn.max_tokens,
        )
        try:
            metrics = await replay.measure_chat(
                client,
                model,
                replay.api_messages(turn.messages),
                rec.max_tokens,
                turn.tools,
                args.fixed_output_tokens,
                custom_params={
                    "session_id": turn.session_id,
                    "turn_idx": turn.turn_idx,
                    "traffic_class": turn.traffic_class,
                    "has_tools": bool(turn.tools),
                },
            )
            for field in (
                "ttft_ms",
                "tpot_ms",
                "e2e_ms",
                "prompt_tokens",
                "cached_tokens",
                "completion_tokens",
                "cache_hit_ratio",
                "status",
            ):
                setattr(rec, field, metrics[field])
            rec.e_time_ms = rec.s_time_ms + rec.e2e_ms
        except Exception as exc:  # noqa: BLE001
            rec.error = f"{type(exc).__name__}: {exc}"
            rec.status = "error"
            rec.e_time_ms = (time.perf_counter() - started) * 1000.0
        async with write_lock:
            results.append(rec)
            row = {**asdict(rec), "phase": item["phase"], "target_s": target_s}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
        print(
            f"[{rec.status}] phase={item['phase']} sid={turn.session_id} "
            f"turn={turn.turn_idx} target={target_s:.3f}s "
            f"sent={rec.s_time_ms / 1000.0:.3f}s cached={rec.cached_tokens}/{rec.prompt_tokens}",
            flush=True,
        )

    try:
        await asyncio.gather(*(execute(item) for item in schedule))
    finally:
        handle.close()
        await client.close()
        wall = time.perf_counter() - started
        summary = replay.build_summary(sorted(results, key=lambda row: row.index), wall)
        summary["protocol"] = {
            "name": "open_loop_fixed_arrival",
            "gap_scale": args.gap_scale,
            "agent_phase_start_s": args.agent_phase_start_s,
            "return_phase_start_s": args.return_phase_start_s,
            "session_stagger_s": args.session_stagger_s,
            "schedule_count": len(schedule),
            "phase_meta": phase_meta,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        )
        (output / "meta.json").write_text(
            json.dumps(
                {
                    "workload_sha256": replay.sha256_file(workload / "workload.jsonl"),
                    "plan": plan,
                    "protocol": summary["protocol"],
                    "schedule": [
                        {
                            "index": item["turn"].index,
                            "trace_id": f"{item['session_id']}#{item['turn'].turn_idx}",
                            "phase": item["phase"],
                            "target_s": item["target_s"],
                        }
                        for item in schedule
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(
            f"[done] issued={summary['integrity']['n_issued']} "
            f"ok={summary['integrity'].get('n_ok')} err={summary['integrity'].get('n_err')} "
            f"wall={wall:.1f}s",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workload-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    # Kept for compatibility with run_controlled_experiment.py.  Open-loop
    # scheduling is defined below and does not use the session-arrival mode.
    parser.add_argument("--arrival", choices=("frozen",), default="frozen")
    parser.add_argument("--gap-scale", type=float, default=0.1)
    parser.add_argument("--agent-phase-start-s", type=float, default=20.0)
    parser.add_argument("--return-phase-start-s", type=float, default=100.0)
    parser.add_argument("--session-stagger-s", type=float, default=2.0)
    parser.add_argument("--max-output-tokens-override", type=int, default=16)
    parser.add_argument("--fixed-output-tokens", action="store_true")
    args = parser.parse_args()
    if args.gap_scale < 0 or args.session_stagger_s < 0:
        parser.error("gap-scale and session-stagger-s must be non-negative")
    if args.return_phase_start_s <= args.agent_phase_start_s:
        parser.error("return phase must start after agent phase")
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
