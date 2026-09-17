"""Real-checkpoint thread timings + held-out frozen-frontier shadow ranking.

The trace contains eviction snapshots, NOT request-unlock episodes. Timing
workloads below are controlled synthetic arrivals with real feature snapshots.
Shadow decisions are counterfactual one-victim rankings, not stateful hit rates.
"""
import argparse
import bisect
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import time

import numpy as np
import torch

from predictor import Model, Node, Worker, predict_sync, reuse_probability


def stats(a):
    if not len(a):
        return {"n": 0}
    a = np.asarray(a)
    return {"n": len(a), "mean": float(a.mean()), "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95)), "p99": float(np.percentile(a, 99)),
            "max": float(a.max())}


def split_of(d):
    v = int.from_bytes(hashlib.blake2b(d.encode(), digest_size=8).digest(), "big") % 100
    return 0 if v < 70 else (1 if v < 85 else 2)


def load_trace(path):
    frames, candidates = [], []
    demand = defaultdict(list)
    end = 0
    for line in path.open():
        r = json.loads(line)
        q = int(r.get("req_seq") or 0)
        end = max(end, q)
        if r["kind"] == "frontier":
            frames.append(r)
            candidates.extend(r.get("candidates", []))
        elif r["kind"] == "demand":
            demand[r["digest"]].append(q)
    for d in demand.values():
        d.sort()
    return frames, candidates, demand, end


def timing(model, raw, mode, n_requests, nodes_per_request, period_ms,
           batch_size, capacity, delay_ms, seed):
    worker = Worker(model, batch_size, capacity, delay_ms) if mode == "async" else None
    for _ in range(20):
        model.predict(raw[:nodes_per_request])
    rng = random.Random(seed)
    offsets = [rng.randrange(len(raw)) for _ in range(n_requests)]
    latency, lag, records = [], [], []
    start = time.perf_counter_ns()
    for i, offset in enumerate(offsets):
        target = start + int(i * period_ms * 1e6)
        if period_ms:
            remaining = (target - time.perf_counter_ns()) / 1e9
            if remaining > 0:
                time.sleep(remaining)
        entered = time.perf_counter_ns()
        lag.append(max(0, entered - target) / 1000)
        tickets = []
        # Includes episode state creation, raw snapshot copy, and queue overhead.
        if mode != "lru":
            for j in range(nodes_per_request):
                n = Node((i, j))
                tickets.append(n.begin(raw[(offset + j) % len(raw)]))
            if worker:
                for t in tickets:
                    worker.submit(t)
            else:
                predict_sync(model, tickets, delay_ms)
        returned = time.perf_counter_ns()
        latency.append((returned - entered) / 1000)
        records.append((returned, tickets))
    serving_s = (time.perf_counter_ns() - start) / 1e9
    if worker:
        worker.close()  # Only after every measured serving operation returned.
    total = n_requests * nodes_per_request
    tickets = [t for _, ts in records for t in ts]
    out = dict(mode=mode, requests=n_requests, nodes_per_request=nodes_per_request,
               period_ms=period_ms, batch_size=batch_size, capacity=capacity,
               injected_delay_ms=delay_ms, seed=seed, serving_wall_s=serving_s,
               request_end_us=stats(latency), schedule_lag_us=stats(lag),
               dropped=worker.dropped if worker else 0,
               worker_error=worker.error if worker else None)
    if mode != "lru":
        out["enqueue_to_ready_us"] = stats([(t.result.ready_ns - t.enqueued_ns) / 1000
                                             for t in tickets if t.result])
        out["ready_after_return"] = {
            str(ms): sum(t.result is not None and t.result.ready_ns <= returned + ms * 1e6
                         for returned, ts in records for t in ts) / total
            for ms in (0, 0.1, 0.5, 1, 5, 10, 50, 100)}
        out["all_nodes_ready_after_return"] = {
            str(ms): sum(all(t.result is not None and t.result.ready_ns <= returned + ms * 1e6
                             for t in ts) for returned, ts in records) / n_requests
            for ms in (0, 0.1, 0.5, 1, 5, 10, 50, 100)}
    if worker:
        out["worker_batch_size"] = stats(worker.batch_sizes)
        out["worker_batch_us"] = stats(worker.batch_us)
        out["queue_wait_us"] = stats(worker.queue_us)
    return out


def shadow(model, frames, demand, end):
    groups = []
    for frame in frames:
        q = int(frame["req_seq"])
        # A fixed follow-up window avoids labelling censored examples as negative.
        if end - q < 100:
            continue
        for kind in ("full", "swa"):
            cs = [c for c in frame.get("candidates", [])
                  if c["frontier"] == kind and split_of(c["digest"]) == 2]
            cs = sorted(cs, key=lambda c: c["lru_rank"])[:16]
            if len(cs) >= 2:
                groups.append((q, kind, cs))
    rows = []
    # Separate actual worker pass: hypothetical eviction deadlines are applied
    # to recorded completion timestamps without waiting in the serving loop.
    worker = Worker(model, 64, 4096)
    records = []
    for i, (q, kind, cs) in enumerate(groups):
        ts = [Node((i, j)).begin(c, q) for j, c in enumerate(cs)]
        for t in ts:
            worker.submit(t)
        records.append((time.perf_counter_ns(), ts))
        time.sleep(0.001)  # Controlled 1-ms snapshot spacing, not original wall time.
    worker.close()
    for (q, kind, cs), (returned, ts) in zip(groups, records):
        p, hazard = model.predict(cs)
        scores = [reuse_probability(h, 0, 20) for h in hazard]
        mlp_choice = min(range(len(cs)), key=lambda j: (scores[j], j))
        choices = {"lru": (0, False), "sync": (mlp_choice, True)}
        if all(t.result is not None for t in ts):
            np.testing.assert_allclose(np.asarray([t.result.probabilities for t in ts]), p,
                                       rtol=1e-5, atol=1e-6)
            async_scores = [reuse_probability(t.result.hazard, 0, 20) for t in ts]
            async_choice = min(range(len(cs)), key=lambda j: (async_scores[j], j))
        else:
            async_choice = 0
        for deadline in (0, 0.1, 0.5, 1, 5, 10):
            ready = all(t.result is not None and t.result.ready_ns <= returned + deadline * 1e6
                        for t in ts)
            # Conservative explicit mixed-candidate rule: any pending => pure LRU.
            choices[f"async_{deadline}ms"] = (async_choice if ready else 0, ready)
        for policy, (idx, used_mlp) in choices.items():
            c = cs[idx]
            ds = demand.get(c["digest"], [])
            j = bisect.bisect_right(ds, q)
            gap = ds[j] - q if j < len(ds) else float("inf")
            rows.append(dict(kind=kind, policy=policy, q=q, used_mlp=used_mlp,
                             different=idx != 0, tokens=max(1, c["kv_tokens"]),
                             reuse5=gap <= 5, reuse20=gap <= 20, reuse100=gap <= 100))
    output = {}
    for kind in ("full", "swa"):
        output[kind] = {}
        for policy in sorted({r["policy"] for r in rows}):
            rs = [r for r in rows if r["kind"] == kind and r["policy"] == policy]
            if not rs:
                continue
            b = dict(decisions=len(rs), mlp_used_fraction=float(np.mean([r["used_mlp"] for r in rs])),
                     differs_from_lru=float(np.mean([r["different"] for r in rs])),
                     total_chosen_tokens=sum(r["tokens"] for r in rs))
            for h in (5, 20, 100):
                b[f"soon_reuse_node_{h}"] = float(np.mean([r[f"reuse{h}"] for r in rs]))
                b[f"soon_reuse_token_{h}"] = sum(r["tokens"] * r[f"reuse{h}"] for r in rs) / b["total_chosen_tokens"]
            output[kind][policy] = b
    return {"results": output, "groups": len(groups), "worker_dropped": worker.dropped,
            "selection": "one victim from oldest 16 held-out digests; horizon=20 events",
            "limitations": ["fixed LRU frontier, not stateful cache replay", "same-trace digest test split, not independent workload",
                            "snapshot enqueue, not observed request unlock", "1ms controlled snapshot spacing",
                            "no TTFT, decode, or KV hit-rate measurement"], "rows": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path("/share/dai-sys/zhoulongsheng/agentkv"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--shadow-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    trace_dir = args.base / "experiments/nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace"
    trace = max(trace_dir.glob("frontier_pid*.jsonl"), key=lambda p: p.stat().st_size)
    checkpoint = args.base / "experiments/nn_exp/uniform_mlp_exp/k10/checkpoints/seed_42.pt"
    model = Model(checkpoint)
    frames, raw, demand, end = load_trace(trace)
    if args.shadow_only:
        result = json.loads((args.output / "results.json").read_text())
        sh = shadow(model, frames, demand, end)
        (args.output / "shadow_decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sh.pop("rows")))
        result["shadow"] = sh
        (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
        print("SHADOW COMPLETE", args.output, flush=True)
        return
    result = {"checkpoint": str(checkpoint), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "trace": str(trace), "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
              "environment": dict(platform=platform.platform(), python=platform.python_version(), torch=torch.__version__,
                                  torch_threads=torch.get_num_threads(), affinity=sorted(os.sched_getaffinity(0))),
              "frontiers": len(frames), "candidate_exposures": len(raw), "end_event": end,
              "timings": []}
    # normal, batch-size sweep, saturation, and deliberately slow inference.
    scenarios = [(1, 1, 64, 4096, 0), (8, 1, 64, 4096, 0), (32, 1, 64, 4096, 0),
                 (128, 1, 64, 4096, 0), (32, 0, 64, 256, 0),
                 (32, 1, 64, 256, 1), (32, 1, 64, 256, 10),
                 (32, 1, 1, 4096, 0), (32, 1, 16, 4096, 0), (32, 1, 128, 4096, 0)]
    if args.quick:
        scenarios = scenarios[:2]
    for repeat in range(1 if args.quick else 3):
        for n, period, batch, cap, delay in scenarios:
            modes = ["lru", "sync", "async"]
            random.Random(100 + repeat).shuffle(modes)
            for mode in modes:
                r = timing(model, raw, mode, 40 if args.quick else 300, n, period, batch, cap, delay, 41 + repeat)
                result["timings"].append(r)
                print(json.dumps({k: r[k] for k in ("mode", "nodes_per_request", "batch_size", "injected_delay_ms", "request_end_us", "dropped")}), flush=True)
                (args.output / "results.partial.json").write_text(json.dumps(result, indent=2))
    sh = shadow(model, frames, demand, end)
    (args.output / "shadow_decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sh.pop("rows")))
    result["shadow"] = sh
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print("COMPLETE", args.output, flush=True)


if __name__ == "__main__":
    main()
