"""Validation-only group combinations and intercept baseline after failed univariate pruning."""
import argparse,itertools,json
from pathlib import Path
import numpy as np
import run_candidate as e
root=Path(__file__).resolve().parent;out=root/'runs/20260916_session_v3';z=np.load(out/'samples.npz');d={k:z[k] for k in z.files}
val=np.where(d['split']==1)[0];test=np.where(d['split']==2)[0];args=argparse.Namespace(device='cuda:0',epochs=60)
sets={'no_features':[]}
# All context-containing combinations, existing full/drop-group/only-context evaluations reused via reports.
others=['position','evolution','session','prefix_history']
for k in (1,2):
 for extra in itertools.combinations(others,k):
  gs=('context',)+extra;sets['plus_'.join(gs)]=[i for i,n in enumerate(e.NAMES) if e.FEATURES[n][1] in gs]
res={}
for name,cols in sets.items():
 hs=[];runs=[]
 for seed in (41,42,43):
  h,run=e.fit(d,cols,seed,args,out/f'{name}_{seed}.pt');hs.append(h);runs.append(run)
 h=np.mean(hs,axis=0);vm,vc=e.evaluation(h,d,val);tm,tc=e.evaluation(h,d,test)
 np.savez_compressed(out/f'{name}_predictions.npz',val_h=h[val],test_h=h[test],val_ibs=vc,test_ibs=tc)
 res[name]={'features':[e.NAMES[i] for i in cols],'validation':vm,'test':tm,'runs':runs}
 (out/'group_confirmation.json').write_text(json.dumps(res,indent=2)); print(name,len(cols),vm['ibs_0_8_relative'],tm['ibs_0_8_relative'],flush=True)
print('DONE',flush=True)

