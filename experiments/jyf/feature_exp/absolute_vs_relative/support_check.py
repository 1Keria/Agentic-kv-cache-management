"""Post-hoc common-support sensitivity, explicitly separate from primary IBS."""
import json
from pathlib import Path
import numpy as np
from run_experiment import survival,hashnum
root=Path(__file__).resolve().parent; run=root/'runs/20260915_v1'
z=np.load(run/'samples.npz'); ix=np.where(z['split']==2)[0]; tau=z['tau'][ix]; sid=z['sid'][ix]; dur=z['duration'][ix]; ev=z['event'][ix].astype(bool)
assert np.min(dur[~ev])>120
rr=json.loads((run/'results.json').read_text()); edges=np.array([2,5,10,20,60,180,600,1800,7200.])
groups,gi=np.unique(sid,return_inverse=True); rng=np.random.default_rng(822); boots=rng.multinomial(len(groups),np.ones(len(groups))/len(groups),size=500)
res={}; lines=['','## 追加核查：共同有限支持区间 0–120 秒','',
'此项是发现尾部覆盖问题后的敏感性分析，不取代预先定义的 0–600s IBS。ID 中 84.5% 样本在 600s 已超出 Relative 最后有限边界。0–120s 对所有样本、所有缩放场景都在两个模型的有限支持区间内，且删失均晚于 120s，无需 IPCW。','',
'|训练规模|场景|Absolute IBS120|Relative IBS120|相对变化|差值95% CI|','|---|---|---:|---:|---:|---|']
for frac,r in rr.items():
 res[frac]={}
 for scen in ('ID','x5','x10','mixed'):
  f=np.ones(len(ix)) if scen=='ID' else np.full(len(ix),5 if scen=='x5' else 10) if scen!='mixed' else np.array([[1,5,10][hashnum('scale'+s)%3] for s in sid])
  cs={}
  for kind in ('absolute','relative'):
   h=np.load(run/f'{frac}_{kind}_{scen}_predictions.npz')['hazards']; e=edges/(r['default_tau'] if kind=='relative' else 1); scale=tau*f if kind=='relative' else np.ones(len(ix))
   assert np.min(e[-1]*scale)>120
   grid=np.linspace(0,120,241); losses=[]
   for t in grid:
    p=1-survival(h,e,t/scale); y=ev&(dur*f<=t); losses.append((p-y)**2)
   cs[kind]=np.trapezoid(losses,grid,axis=0)/120
  a=cs['absolute'].mean(); b=cs['relative'].mean(); sums=np.bincount(gi,weights=cs['relative']-cs['absolute']); counts=np.bincount(gi)
  ci=np.quantile((boots@sums)/(boots@counts),[.025,.975])
  res[frac][scen]={'absolute':a,'relative':b,'delta_ci95':ci.tolist()}
  lines.append('|%s|%s|%.5f|%.5f|%+.1f%%|[%+.5f,%+.5f]|'%(frac,scen,a,b,100*(b/a-1),*ci))
(run/'common_support.json').write_text(json.dumps(res,indent=2))
with (root/'conclusion_zh.md').open('a') as f: f.write('\n'.join(lines)+'\n')
print('\n'.join(lines))
