"""Compact read-only status for the three-arm experiment."""
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("run", type=Path)
a = p.parse_args()
out = {"status": (a.run / "status").read_text().strip(), "arms": {}}
def rows(path):
    result = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return result
for mode in ("lru", "sync", "async", "sync_fill"):
    arm = a.run / mode
    if not arm.exists():
        continue
    rs = rows(arm / "replay/replay.jsonl")
    logs = list((arm / "metrics").glob("rank0_*.jsonl"))
    ms = rows(logs[0]) if logs else []
    es = [r for r in ms if r["kind"] == "evict"]
    fs = [r for r in ms if r["kind"] == "finish"]
    b = dict(completed=len(rs), evictions=len(es), choices=sum(e["choices"] for e in es),
             mlp_choices=sum(e["mlp_choices"] for e in es), changed=sum(e["changed_choices"] for e in es),
             worker_error=fs[-1].get("worker_error") if fs else None,
             dropped=fs[-1].get("dropped") if fs else None)
    if rs:
        b["last_request"] = {k: rs[-1].get(k) for k in ("status", "error")}
        b["errors"] = sum(r.get("error") is not None or str(r.get("status")) != "200" for r in rs)
    if mode == "sync_fill":
        b["fill_nodes"] = sum(e.get("fill_nodes", 0) for e in es)
        b["fill_batches"] = sum(e.get("fill_batches", 0) for e in es)
    summary = arm / "replay/summary.json"
    if summary.exists():
        s = json.loads(summary.read_text())
        b["integrity"] = s["integrity"]
        b["kv"] = s["kv"]
    out["arms"][mode] = b
print(json.dumps(out, indent=2))
