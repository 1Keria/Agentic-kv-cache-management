"""CPU kernel-only cost diagnostic, not an end-to-end eviction benchmark."""
import json
from pathlib import Path
import time
import numpy as np
from predictor import Model,values
from training_base import ALL_NAMES
root=Path(__file__).resolve().parent
d=np.load(root/'training/samples.npz')
x=d['x'][d['split']==2]
m=Model(root/'training/model.pt')
rows=[]
for n in (32,128,512,2048):
    z=x[:n]
    paths=np.expm1(z[:,ALL_NAMES.index('path_tokens')])
    sizes=np.maximum(1,np.expm1(z[:,ALL_NAMES.index('node_tokens')]))
    ages=np.full(n,5.)
    h=m.predict(z)
    for _ in range(10):m.predict(z);values(h,ages,paths,sizes)
    infer,score=[],[]
    for _ in range(100):
        start=time.perf_counter_ns();m.predict(z);infer.append((time.perf_counter_ns()-start)/1000)
        start=time.perf_counter_ns();values(h,ages,paths,sizes);score.append((time.perf_counter_ns()-start)/1000)
    rows.append(dict(nodes=n,mlp_p50_us=float(np.median(infer)),mlp_p99_us=float(np.percentile(infer,99)),
                     conditioning_value_p50_us=float(np.median(score)),conditioning_value_p99_us=float(np.percentile(score,99))))
(root/'predictor_benchmark.json').write_text(json.dumps(dict(torch_threads=1,rows=rows,
 limitation='Kernel-only microbenchmark. Excludes metadata snapshots, frontier traversal, queueing, future waits and TP communication. Host concurrently runs another GPU benchmark.'),indent=2))
print(json.dumps(rows,indent=2))
