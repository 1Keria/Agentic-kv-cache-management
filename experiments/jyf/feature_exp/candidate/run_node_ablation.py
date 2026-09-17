#!/usr/bin/env python3
import argparse,json,math
from pathlib import Path
import numpy as np, torch
from torch import nn

OLD10=["node_tokens","path_tokens","age_seconds","idle_seconds","hits","gap_present","recent_gap_seconds","gap_ewma_seconds","gap_std_seconds","is_agent"]
CAND8=["creation_turn_fraction","endpoint_is_tool","tool_schema_count","last_message_is_tool","last_message_is_user","prefix_gap_ewma_rel","prefix_reuse_rate8","prefix_turn_gap_last"]
ALL=OLD10+CAND8
GROUPS={
 "old_structure":["node_tokens","path_tokens"],
 "old_node_time":["age_seconds","idle_seconds"],
 "old_history":["hits","gap_present","recent_gap_seconds","gap_ewma_seconds","gap_std_seconds"],
 "old_workload":["is_agent"],
 "candidate_context":["endpoint_is_tool","tool_schema_count","last_message_is_tool","last_message_is_user"],
 "candidate_history":["prefix_gap_ewma_rel","prefix_reuse_rate8","prefix_turn_gap_last"],
 "candidate_position":["creation_turn_fraction"],
}
EDGES=np.array([.125,.25,.5,1,2,4,8,16,64],dtype=np.float32)
GRID=np.unique(np.r_[np.linspace(0,8,65),.25,.5,1,2,4])

def rank(a):
 o=np.argsort(a,kind="stable"); v=a[o]; out=np.empty(len(a)); s=np.r_[0,np.where(v[1:]!=v[:-1])[0]+1,len(v)]
 for l,r in zip(s[:-1],s[1:]): out[o[l:r]]=(l+r-1)/2
 return out

def auc_score(p,y):
 y=np.asarray(y).astype(bool); n1=int(y.sum()); n0=len(y)-n1
 if n1==0 or n0==0:return float("nan")
 rr=rank(np.asarray(p)); return float((rr[y].sum()-n1*(n1-1)/2)/(n1*n0))

def load(path):
 z=np.load(path,allow_pickle=True); keep=np.isfinite(z["tau"])&(z["tau"]>0)&np.isfinite(z["duration_relative"])
 return {k:z[k][keep] for k in z.files}

class Net(nn.Module):
 def __init__(self,d):
  super().__init__(); self.net=nn.Sequential(nn.Linear(d,64),nn.ReLU(),nn.Linear(64,64),nn.ReLU(),nn.Linear(64,9))
 def forward(self,x):return self.net(x)

def nll(logits,d,e):
 ls=torch.nn.functional.logsigmoid(-logits); lh=torch.nn.functional.logsigmoid(logits)
 ed=torch.tensor(EDGES,device=d.device); idx=torch.bucketize(d,ed,right=True)
 ll=(ls*(torch.arange(9,device=d.device)[None,:]<idx[:,None])).sum(1)
 hit=(e>.5)&(idx<9); ii=torch.where(hit)[0]; ll[ii]+=lh[ii,idx[ii]]
 ce=(e<.5)&(idx<9); ii=torch.where(ce)[0]; j=idx[ii]; left=torch.where(j==0,0.,ed[(j-1).clamp_min(0)])
 ll[ii]+=((d[ii]-left)/(ed[j]-left)).clamp(0,1)*ls[ii,j]
 return -ll.mean()

def surv(h,t):
 ans=np.zeros(len(h)); left=0.
 for j,right in enumerate(EDGES): ans += np.clip((t-left)/(right-left),0,1)*np.log(np.clip(1-h[:,j],1e-8,1)); left=right
 return np.exp(ans)

def metrics(h,d,e,ix):
 h=h[ix]; d=d[ix]; e=e[ix]>.5; curves=[]
 for t in GRID:
  p=1-surv(h,t); y=e&(d<=t); alive=d>t; known=y|alive
  curves.append(np.mean(np.where(known,(p-y.astype(float))**2,0)))
 out={"ibs_0_8":float(np.trapezoid(curves,GRID)/8)}
 for t in (1.,2.,4.):
  p=1-surv(h,t); y=e&(d<=t); known=y|(d>t)
  out[f"auc@{int(t)}tau"]=auc_score(p[known],y[known])
  out[f"brier@{int(t)}tau"]=float(np.mean((p[known]-y[known])**2))
 return out

def fit(data,cols,seed,epochs=45,device="cuda:0"):
 torch.manual_seed(seed); np.random.seed(seed)
 x=data["x"].astype(np.float32).copy(); tr=np.where(data["split"]==0)[0]; va=np.where(data["split"]==1)[0]
 mu=x[tr].mean(0); sd=np.maximum(x[tr].std(0),1e-5); x=(x-mu)/sd
 mask=np.ones(len(ALL),bool); mask[cols]=False; x[:,mask]=0
 xx=torch.tensor(x,device=device); dd=torch.tensor(data["duration_relative"],dtype=torch.float32,device=device); ee=torch.tensor(data["event"],dtype=torch.float32,device=device)
 m=Net(len(ALL)).to(device); opt=torch.optim.AdamW(m.parameters(),lr=1e-3,weight_decay=1e-4)
 best=1e99; state=None; stale=0; rng=np.random.default_rng(seed)
 for ep in range(epochs):
  m.train()
  for pos in np.array_split(rng.permutation(len(tr)),max(1,math.ceil(len(tr)/8192))):
   ii=tr[pos]; loss=nll(m(xx[ii]),dd[ii],ee[ii]); opt.zero_grad(); loss.backward(); opt.step()
  m.eval()
  with torch.no_grad(): vl=float(nll(m(xx[va]),dd[va],ee[va]).cpu())
  if vl<best-1e-5: best=vl; state={k:v.detach().cpu().clone() for k,v in m.state_dict().items()}; stale=0
  else: stale+=1
  if stale>=6:break
 m.load_state_dict(state); m.eval()
 with torch.no_grad(): h=torch.sigmoid(m(xx)).cpu().numpy()
 return metrics(h,data["duration_relative"],data["event"],np.where(data["split"]==2)[0]),best,ep+1

def corr(data,out):
 tr=np.where(data["split"]==0)[0]; x=data["x"][tr]; y=data["duration_relative"][tr]; e=data["event"][tr]>.5
 res=[]
 for j,n in enumerate(ALL):
  v=x[:,j]; res.append({"feature":n,"spearman_abs_duration":float(np.corrcoef(rank(v),rank(y))[0,1]),"spearman_event":float(np.corrcoef(rank(v),rank(e.astype(float)))[0,1]),"std":float(v.std()),"unique":int(np.unique(v).size)})
 mat=np.corrcoef(np.array([rank(x[:,j]) for j in range(len(ALL))]))
 (out/"correlations.json").write_text(json.dumps({"features":res,"spearman_matrix":mat.tolist(),"names":ALL},indent=2))
 return res

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--data",type=Path,required=True); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--device",default="cuda:0"); ap.add_argument("--epochs",type=int,default=45); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
 d=load(a.data/"node_samples.npz"); out=a.out; corr(d,out)
 sets={"full18":list(range(len(ALL))),"old10":list(range(10)),"candidate8":list(range(10,18))}
 for g,names in GROUPS.items(): sets["without_"+g]=[i for i,n in enumerate(ALL) if n not in names]
 for n in ALL: sets["without_"+n]=[i for i,x in enumerate(ALL) if x!=n]
 results={}
 for name,cols in sets.items():
  seeds=(41,42,43) if name in ("full18","old10","candidate8") else (41,)
  runs=[]
  for s in seeds:
   met,vl,ep=fit(d,cols,s,a.epochs,a.device); runs.append({"seed":s,"val_nll":vl,"epochs":ep,"test":met})
  def avg(k): return float(np.nanmean([r["test"][k] for r in runs]))
  results[name]={"features":[ALL[i] for i in cols],"n_seeds":len(seeds),"test_mean":{k:avg(k) for k in runs[0]["test"]},"runs":runs}
 (out/"ablation_results.json").write_text(json.dumps(results,indent=2))
 lines=["# Node-level correlation and ablation","",f"Samples used: {len(d['x'])}; duration: session-relative next demand time; node-level persistent prefix; no eviction.","","## Main models"]
 for n in ("full18","old10","candidate8"):
  r=results[n]["test_mean"]; lines.append(f"- {n}: IBS={r['ibs_0_8']:.5f}; AUC@1/2/4tau={r['auc@1tau']:.4f}/{r['auc@2tau']:.4f}/{r['auc@4tau']:.4f}")
 lines += ["","## Group/leave-one-out ablation","|set|IBS|AUC@1|AUC@2|AUC@4|","|-|-|-|-|-|"]
 for n,r in results.items():
  if n in ("full18","old10","candidate8"):continue
  q=r["test_mean"]; lines.append(f"|{n}|{q['ibs_0_8']:.5f}|{q['auc@1tau']:.4f}|{q['auc@2tau']:.4f}|{q['auc@4tau']:.4f}|")
 (out/"report.md").write_text("\n".join(lines))
 print(json.dumps({"samples":len(d["x"]),"output":str(out)},indent=2))

if __name__=="__main__": main()

