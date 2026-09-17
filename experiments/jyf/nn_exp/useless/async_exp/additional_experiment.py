"""Eviction read/interpolation overhead and equal-minimum-token shadow check."""
import argparse
import bisect
import json
from pathlib import Path
import time

import numpy as np
import torch

from predictor import Model, Node, choose_candidate, predict_sync, reuse_probability
from run_experiment import load_trace, split_of, stats


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--run", type=Path, required=True)
    args = a.parse_args()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    meta = json.loads((args.run / "results.json").read_text())
    model = Model(meta["checkpoint"])
    frames, raw, demand, end = load_trace(Path(meta["trace"]))
    result = {"eviction_us": [], "equal_minimum_tokens_shadow": {}}
    for n in (1, 8, 16, 32, 64, 128):
        for state in ("lru", "pending", "ready"):
            nodes = [Node(j) for j in range(n)]
            ts = [x.begin(raw[j], 0) for j, x in enumerate(nodes)]
            if state == "ready":
                predict_sync(model, ts)
            for _ in range(100):
                choose_candidate(nodes, 10, 20)
            samples = []
            for _ in range(3000):
                t = time.perf_counter_ns()
                if state == "lru":
                    victim = nodes[0]
                else:
                    victim, _ = choose_candidate(nodes, 10, 20)
                samples.append((time.perf_counter_ns() - t) / 1000)
            result["eviction_us"].append(dict(nodes=n, state=state, latency=stats(samples)))
    # Same smallest eviction target for each policy. Nodes are indivisible, so
    # report overshoot as well as regret per chosen token. This remains static.
    rows = []
    for frame in frames:
        q = int(frame["req_seq"])
        if end - q < 100:
            continue
        for kind in ("full", "swa"):
            cs = sorted([c for c in frame.get("candidates", [])
                         if c["frontier"] == kind and split_of(c["digest"]) == 2],
                        key=lambda c: c["lru_rank"])[:16]
            if len(cs) < 2:
                continue
            _, hazards = model.predict(cs)
            scores = [reuse_probability(h, 0, 20) for h in hazards]
            target = max(1, cs[0]["kv_tokens"])
            for mode, order in (("lru", list(range(len(cs)))),
                                ("mlp", sorted(range(len(cs)), key=lambda j: (scores[j], j)))):
                freed, regret, count = 0, 0, 0
                for j in order:
                    c = cs[j]
                    tok = max(1, c["kv_tokens"])
                    ds = demand.get(c["digest"], [])
                    at = bisect.bisect_right(ds, q)
                    soon = at < len(ds) and ds[at] - q <= 20
                    freed += tok
                    regret += tok * soon
                    count += 1
                    if freed >= target:
                        break
                rows.append(dict(kind=kind, q=q, mode=mode, target=target,
                                 freed=freed, regret=regret, victims=count))
    for kind in ("full", "swa"):
        result["equal_minimum_tokens_shadow"][kind] = {}
        for mode in ("lru", "mlp"):
            rs = [r for r in rows if r["kind"] == kind and r["mode"] == mode]
            total = {key: sum(r[key] for r in rs) for key in ("target", "freed", "regret", "victims")}
            total.update(decisions=len(rs), regret_per_freed=total["regret"] / total["freed"],
                         excess_fraction=total["freed"] / total["target"] - 1)
            result["equal_minimum_tokens_shadow"][kind][mode] = total
    (args.run / "additional_results.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.run / "equal_minimum_tokens_decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
