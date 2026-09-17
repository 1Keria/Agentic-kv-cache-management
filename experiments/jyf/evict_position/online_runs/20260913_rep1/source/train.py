"""Export the seconds model; never select a checkpoint on serving results."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import torch
import training_base as t

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--trace-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=Path('training'))
    p.add_argument('--seeds', type=int, nargs='+', default=[41,42,43])
    a = p.parse_args()
    torch.set_num_threads(4)
    a.device, a.epochs, a.patience, a.batch_size = 'cpu', 100, 12, 4096
    a.checkpoint_dir = a.output_dir / 'checkpoints'
    a.checkpoint_dir.mkdir(parents=True, exist_ok=False)
    trace = t.choose_trace(a.trace_dir)
    data = t.build_dataset(*t.load_trace(trace))
    np.savez_compressed(a.output_dir / 'samples.npz', **{k:v for k,v in data.items() if k!='meta'})
    runs = []
    for seed in a.seeds:
        r, _ = t.fit_one(data, t.BOTH_CANDIDATE16, seed, a)
        runs.append(r)
        print(json.dumps(r), flush=True)
    best = min(runs, key=lambda r:r['best_val_nll'])
    shutil.copyfile(a.checkpoint_dir / f"seed_{best['seed']}.pt", a.output_dir/'model.pt')
    result = dict(trace=str(trace), trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
                  meta=data['meta'], runs=runs, selected_seed=best['seed'],
                  feature_names=t.BOTH_CANDIDATE16,
                  limitation='Training observations are eviction-frontier landmarks, not request-end landmarks; validation is prefix-isolated, not session-isolated.')
    (a.output_dir/'results.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__': main()
