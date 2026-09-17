"""Validate compression within a validation-selected group combination."""
import argparse,json
from pathlib import Path
import numpy as np
import run_candidate as e
root=Path(__file__).resolve().parent;out=root/'runs/20260916_session_v3';z=np.load(out/'samples.npz');d={k:z[k] for k in z.files};args=argparse.Namespace(device='cuda:0',epochs=60)
val=np.where(d['split']==1)[0];test=np.where(d['split']==2)[0]
g=json.loads((out/'group_confirmation.json').read_text());prior=json.loads((out/'results.json').read_text())['models'];g.update(prior)
best=min(v['validation']['ibs_0_8_relative'] for v in g.values())
eligible=[n for n,v in g.items() if v['validation']['ibs_0_8_relative']<=best*1.01]
base=min(eligible,key=lambda n:(len(g[n]['features']),g[n]['validation']['ibs_0_8_relative']))
features=g[base]['features'];cols=[e.NAMES.index(n) for n in features];records={};baseval=g[base]['validation']['ibs_0_8_relative']
def train(name,cc,save=False):
 hs=[];runs=[]
 for seed in (41,42,43):
  h,r=e.fit(d,cc,seed,args,out/f'{name}_{seed}.pt' if save else None);hs.append(h);runs.append(r)
 h=np.mean(hs,axis=0);vm,vc=e.evaluation(h,d,val)
 rec={'features':[e.NAMES[i] for i in cc],'validation':vm,'runs':runs}
 if save:
  tm,tc=e.evaluation(h,d,test);rec['test']=tm;np.savez_compressed(out/f'{name}_predictions.npz',val_h=h[val],test_h=h[test],val_ibs=vc,test_ibs=tc)
 print(name,len(cc),vm['ibs_0_8_relative'],flush=True);return rec
for i in cols:
 name='refine_without_'+e.NAMES[i];records[name]=train(name,[j for j in cols if j!=i])
 (out/'refine_screening.json').write_text(json.dumps(records,indent=2))
# Two fixed compression proposals: individually harmful removal never bundled;
# one removes only features whose omission improves validation, one tolerates .2%.
proposals={}
for label,tolerance in [('strict',1.0),('compact',1.002)]:
 kept=[i for i in cols if records['refine_without_'+e.NAMES[i]]['validation']['ibs_0_8_relative']>baseval*tolerance]
 if kept:proposals[label]=kept
final={base:g[base]}
for label,cc in proposals.items():final[label]=train('refined_'+label,cc,True)
best=min(v['validation']['ibs_0_8_relative'] for v in final.values());eligible=[n for n,v in final.items() if v['validation']['ibs_0_8_relative']<=best*1.01]
chosen=min(eligible,key=lambda n:(len(final[n]['features']),final[n]['validation']['ibs_0_8_relative']))
payload={'group_base':base,'chosen':chosen,'models':final,'policy':'smallest within 1% of best validation IBS; never select on test'}
(out/'final_selection.json').write_text(json.dumps(payload,indent=2));print('DONE',chosen,final[chosen]['features'],flush=True)

