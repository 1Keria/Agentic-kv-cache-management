"""Final validation check of near-complement last-role indicators."""
import argparse,json
from pathlib import Path
import numpy as np
import run_candidate as e
root=Path(__file__).resolve().parent;out=root/'runs/20260916_session_v3';z=np.load(out/'samples.npz');d={k:z[k] for k in z.files};args=argparse.Namespace(device='cuda:0',epochs=60)
val=np.where(d['split']==1)[0];test=np.where(d['split']==2)[0];r=json.loads((out/'final_selection.json').read_text());base=r['models'][r['chosen']];res={'eight_feature_base':base}
for drop in ('last_message_is_user','last_message_is_tool'):
 names=[n for n in base['features'] if n!=drop];cols=[e.NAMES.index(n) for n in names];key='final_without_'+drop;hs=[];runs=[]
 for seed in (41,42,43):
  h,run=e.fit(d,cols,seed,args,out/f'{key}_{seed}.pt');hs.append(h);runs.append(run)
 h=np.mean(hs,axis=0);vm,vc=e.evaluation(h,d,val);tm,tc=e.evaluation(h,d,test)
 res[key]={'features':names,'validation':vm,'test':tm,'runs':runs};np.savez_compressed(out/f'{key}_predictions.npz',val_h=h[val],test_h=h[test],val_ibs=vc,test_ibs=tc)
 print(key,vm,tm,flush=True)
best=min(v['validation']['ibs_0_8_relative'] for v in res.values());eligible=[n for n,v in res.items() if v['validation']['ibs_0_8_relative']<=best*1.01]
chosen=min(eligible,key=lambda n:(len(res[n]['features']),res[n]['validation']['ibs_0_8_relative']))
(out/'recommended.json').write_text(json.dumps({'chosen':chosen,'models':res,'policy':'smallest within 1% best validation; test not used for choice'},indent=2));print('CHOSEN',chosen,flush=True)
