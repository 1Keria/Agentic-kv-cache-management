import argparse
import hashlib
import json
from pathlib import Path
import shutil

p = argparse.ArgumentParser()
p.add_argument("--run", type=Path, required=True)
p.add_argument("--modes", nargs="+", default=["lru", "sync", "async"])
a = p.parse_args()
source = Path(__file__).resolve().parent
base = source.parents[2]
work = base / "experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32/workload.jsonl"
checkpoint = base / "experiments/nn_exp/uniform_mlp_exp/k10/checkpoints/seed_42.pt"
snapshot = a.run / "source_snapshot"
snapshot.mkdir(parents=True, exist_ok=True)
files = [source / f for f in ("predictor.py", "sitecustomize.py", "serving_patch.py", "run_online.sh", "test_serving_cache.py", "report_online.py")]
hashes = {}
for f in files:
    shutil.copy2(f, snapshot / f.name)
    hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
payload = dict(source_sha256=hashes, workload=str(work), workload_sha256=hashlib.sha256(work.read_bytes()).hexdigest(),
               checkpoint=str(checkpoint), checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
               modes=a.modes, seed=42, arrival="waves", horizon_s=300,
               waves=9, wave_width_s=20, gap_scale=.02, max_tokens=32, mem_fraction_static=.45, tp=8)
(a.run / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n")
print(a.run / "manifest.json")
