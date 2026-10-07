#!/usr/bin/env python3
"""Replay fixed prompts with completion barriers and a shared inflight limit."""

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


async def run(args) -> None:
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
    client = replay.AsyncOpenAI(base_url=f"{args.base_url}/v1", api_key="EMPTY", timeout=600, max_retries=0)
    limiter = asyncio.Semaphore(args.max_inflight)
    results = []
    phase_events = []
    inflight = 0
    peak_inflight = 0
    started = time.perf_counter()
    write_lock = asyncio.Lock()
    handle = (output / "replay.jsonl").open("w")

    async def execute_session(sid: str, phase_name: str, phase_start: float, phase_origin: float):
        nonlocal inflight, peak_inflight
        turns = sessions[sid]
        # Phase barriers already enforce the original phase order.  Rebase
        # arrivals within each phase so the absolute offset is not slept again
        # after every barrier (or for every session in a serial phase).
        delay = max(0., turns[0].session_start_s - phase_origin - (time.perf_counter() - phase_start))
        if delay:
            await asyncio.sleep(delay)
        for turn in turns:
            gap = max(0., turn.pre_gap_s * args.gap_scale) if turn.turn_idx else 0.
            if gap:
                await asyncio.sleep(gap)
            queued = time.perf_counter()
            async with limiter:
                sent = time.perf_counter()
                inflight += 1
                peak_inflight = max(peak_inflight, inflight)
                rec = replay.RequestResult(
                    index=turn.index, trace_id=f"{sid}#{turn.turn_idx}",
                    start_time_orig=str(turn.session_start_s), t_sched_ms=(queued-started)*1000,
                    s_time_ms=(sent-started)*1000, s_time_drift_ms=(sent-queued)*1000,
                    traffic_class=turn.traffic_class, session_id=sid, turn_index=turn.turn_idx,
                    pre_gap_s=turn.pre_gap_s, sleep_before_s=gap,
                    max_tokens=args.max_output_tokens_override or turn.max_tokens,
                )
                try:
                    metrics = await replay.measure_chat(
                        client, model, replay.api_messages(turn.messages), rec.max_tokens,
                        turn.tools, args.fixed_output_tokens,
                        custom_params={"session_id": sid, "turn_idx": turn.turn_idx, "traffic_class": turn.traffic_class, "has_tools": bool(turn.tools)},
                    )
                    for field in ("ttft_ms", "tpot_ms", "e2e_ms", "prompt_tokens", "cached_tokens", "completion_tokens", "cache_hit_ratio", "status"):
                        setattr(rec, field, metrics[field])
                    rec.e_time_ms = rec.s_time_ms + rec.e2e_ms
                except Exception as exc:
                    rec.error = f"{type(exc).__name__}: {exc}"
                    rec.status = "error"
                    rec.e_time_ms = (time.perf_counter()-started)*1000
                finally:
                    inflight -= 1
                row = {**asdict(rec), "phase": phase_name, "client_queue_ms": (sent-queued)*1000}
                async with write_lock:
                    results.append(rec)
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                print(f"[{rec.status}] phase={phase_name} sid={sid} turn={turn.turn_idx} cached={rec.cached_tokens}/{rec.prompt_tokens}", flush=True)
                if rec.error:
                    raise RuntimeError(rec.error)

    async def snapshot(name, side):
        response = await asyncio.to_thread(replay.requests.get, f"{args.base_url}/server_info", timeout=15)
        response.raise_for_status()
        (output / f"state_{name}_{side}.json").write_text(json.dumps(response.json(), ensure_ascii=False, indent=2)+"\n")

    try:
        for phase in plan["phases"]:
            phase_start = time.perf_counter()
            phase_origin = min(sessions[sid][0].session_start_s for sid in phase["session_ids"])
            before = len(results)
            await snapshot(phase["name"], "before")
            if phase["execution"] == "serial":
                for sid in phase["session_ids"]:
                    await execute_session(sid, phase["name"], phase_start, phase_origin)
            elif phase["execution"] == "parallel":
                await asyncio.gather(*(execute_session(sid, phase["name"], phase_start, phase_origin) for sid in phase["session_ids"]))
            else:
                raise ValueError("unknown phase execution")
            await snapshot(phase["name"], "after")
            current = results[before:]
            event = {"phase": phase["name"], "started_s": phase_start-started, "finished_s": time.perf_counter()-started, "n_requests": len(current)}
            if phase.get("require_warm_hit"):
                evidence = {}
                for sid in phase["session_ids"]:
                    rr = [r for r in current if r.session_id == sid and r.turn_index > 0]
                    hit = sum(r.cached_tokens or 0 for r in rr) / sum(r.prompt_tokens or 0 for r in rr)
                    evidence[sid] = hit
                event["warm_hit_by_session"] = evidence
                if (
                    not args.allow_phase_requirement_failure
                    and any(value < phase["require_warm_hit"] for value in evidence.values())
                ):
                    raise RuntimeError(f"ordinary warmup did not establish reuse: {evidence}")
            if phase.get("require_first_hit") is not None:
                first_evidence = {}
                for sid in phase["session_ids"]:
                    rr = [r for r in current if r.session_id == sid and r.turn_index == 0]
                    prompt = sum(r.prompt_tokens or 0 for r in rr)
                    cached = sum(r.cached_tokens or 0 for r in rr)
                    first_evidence[sid] = cached / prompt if prompt else 0.0
                event["first_turn_hit_by_session"] = first_evidence
                event["first_turn_hit_threshold"] = phase["require_first_hit"]
                if (
                    not args.allow_phase_requirement_failure
                    and any(value < phase["require_first_hit"] for value in first_evidence.values())
                ):
                    raise RuntimeError(
                        "ordinary return did not retain the required first-turn prefix: "
                        f"{first_evidence} < {phase['require_first_hit']}"
                    )
            phase_events.append(event)
            print(json.dumps(event, ensure_ascii=False), flush=True)
    finally:
        handle.close()
        await client.close()
        wall = time.perf_counter()-started
        summary = replay.build_summary(sorted(results, key=lambda row: row.index), wall)
        summary["protocol"] = {"name": "phased_bounded_inflight", "max_inflight": args.max_inflight, "peak_inflight": peak_inflight, "phase_events": phase_events, "all_phases_complete": len(phase_events)==len(plan["phases"])}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
        (output / "meta.json").write_text(json.dumps({"workload_sha256": replay.sha256_file(workload/"workload.jsonl"), "plan": plan, "gap_scale": args.gap_scale, "fixed_output_tokens": args.fixed_output_tokens}, ensure_ascii=False, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workload-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arrival", choices=("frozen",), default="frozen")
    parser.add_argument("--gap-scale", type=float, default=.1)
    parser.add_argument("--max-output-tokens-override", type=int, default=16)
    parser.add_argument("--fixed-output-tokens", action="store_true")
    parser.add_argument("--max-inflight", type=int, default=2)
    parser.add_argument(
        "--allow-phase-requirement-failure",
        action="store_true",
        help="Record, but do not abort on, workload phase hit-rate requirements.",
    )
    args = parser.parse_args()
    if args.max_inflight <= 0:
        parser.error("max-inflight must be positive")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
