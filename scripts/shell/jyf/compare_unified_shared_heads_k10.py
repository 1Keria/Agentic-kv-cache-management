#!/usr/bin/env python3
"""Ten-bucket censored reuse-distance comparison for unified vs two-head MLP."""

import argparse, bisect, hashlib, json, math, random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

EDGES = (1, 2, 5, 10, 20, 50, 100, 200, 500)  # tenth bucket is >500
FEATURES = ["log_node_tokens","log_path_tokens","log_depth","log_age_events","lru_frac","log_parent_hits","log_siblings","warm_sibling_fraction","log_owner_turn","is_cold","log_hits","gap_present","log_recent_gap_events","is_openhands","is_request","is_swa"]

def split_of(d):
    v=int.from_bytes(hashlib.blake2b(d.encode(),digest_size=8).digest(),"big")%100
    return 0 if v<70 else (1 if v<85 else 2)

def feat(c):
    sib=max(0,int(c.get("siblings",0))); gap=int(c.get("recent_gap_req",-1)); tr=c.get("owner_traffic","")
    return [math.log1p(max(0,int(c.get("node_tokens",0)))),math.log1p(max(0,int(c.get("path_tokens",0)))),math.log1p(max(0,int(c.get("depth",0)))),math.log1p(max(0,int(c.get("age_requests",0)))),float(c.get("lru_frac",0)),math.log1p(max(0,int(c.get("parent_hits",0)))),math.log1p(sib),max(0,int(c.get("warm_siblings",0)))/max(sib,1),math.log1p(max(0,int(c.get("owner_turn",0)))),float(c.get("cold",0)),math.log1p(max(0,int(c.get("hits",0)))),float(gap>=0),math.log1p(max(gap,0)),float(tr=="openhands"),float(tr=="request"),float(c.get("frontier")=="swa")]

def bucket(d): return bisect.bisect_left(EDGES,d)

def load(trace):
    ev=[]; dem=defaultdict(list); end=0
    for line in trace.open():
        r=json.loads(line); q=int(r.get("req_seq") or 0); end=max(end,q)
        if r.get("kind")=="frontier": ev.append(r)
        elif r.get("kind")=="demand": dem[r["digest"]].append(q)
    for x in dem.values(): x.sort()
    rows=[]
    for e in ev:
        q=int(e.get("req_seq") or 0)
        for c in e.get("candidates") or []:
            ds=dem.get(c["digest"],()); j=bisect.bisect_right(ds,q); nxt=ds[j] if j<len(ds) else None
            if nxt is not None:
                target=bucket(nxt-q); allowed=1<<target; exact=1
            else:
                censor=end-q; first=bisect.bisect_right(EDGES,censor); allowed=sum(1<<k for k in range(first,10)); exact=0
                if not allowed: continue
            rows.append((c["digest"],feat(c),target if exact else -1,allowed,exact,max(1,int(c.get("kv_tokens",0))),int(c.get("cold",0))))
    return rows,end

class Unified(nn.Module):
    def __init__(self,n): super().__init__(); self.t=nn.Sequential(nn.Linear(n,64),nn.ReLU(),nn.Linear(64,32),nn.ReLU()); self.h=nn.Linear(32,10)
    def forward(self,x,c): return self.h(self.t(x))
class Heads(nn.Module):
    def __init__(self,n): super().__init__(); self.t=nn.Sequential(nn.Linear(n,56),nn.ReLU(),nn.Linear(56,28),nn.ReLU()); self.c=nn.Linear(28,10); self.w=nn.Linear(28,10)
    def forward(self,x,cold):
        z=self.t(x); return torch.where(cold[:,None]>.5,self.c(z),self.w(z))

def censored_losses(logits,allowed):
    lp=torch.log_softmax(logits,1); bits=torch.arange(10,device=logits.device)[None,:]
    ok=((allowed[:,None]>>bits)&1).bool(); return -torch.logsumexp(lp.masked_fill(~ok,float("-inf")),1)
def loss(logits,allowed,cold):
    raw=censored_losses(logits,allowed); vals=[]
    for f in (0,1):
        z=raw[cold==f]
        if len(z): vals.append(z.mean())
    return torch.stack(vals).mean()

def train(kind,x,allowed,cold,sp,out,seed):
    torch.manual_seed(seed);np.random.seed(seed);random.seed(seed); tr=np.where(sp==0)[0];va=np.where(sp==1)[0]
    mu=x[tr].mean(0);sd=x[tr].std(0);sd[sd<1e-5]=1;z=((x-mu)/sd).astype("float32")
    model=(Unified if kind=="unified" else Heads)(x.shape[1]);opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4)
    ds=TensorDataset(torch.from_numpy(z[tr]),torch.from_numpy(allowed[tr]),torch.from_numpy(cold[tr]));dl=DataLoader(ds,2048,shuffle=True,generator=torch.Generator().manual_seed(seed))
    best=1e9;state=None;pat=7
    for epoch in range(70):
        model.train()
        for xb,ab,cb in dl:
            l=loss(model(xb,cb),ab,cb);opt.zero_grad();l.backward();opt.step()
        model.eval()
        with torch.no_grad():vl=loss(model(torch.from_numpy(z[va]),torch.from_numpy(cold[va])),torch.from_numpy(allowed[va]),torch.from_numpy(cold[va])).item()
        if vl<best-1e-5:best=vl;state={k:v.detach().clone() for k,v in model.state_dict().items()};pat=7
        else:
            pat-=1
            if pat==0:break
    model.load_state_dict(state);model.eval()
    with torch.no_grad():p=torch.softmax(model(torch.from_numpy(z),torch.from_numpy(cold)),1).numpy()
    out.mkdir(parents=True,exist_ok=True);torch.save({"kind":kind,"seed":seed,"features":FEATURES,"bucket_upper_edges":EDGES,"mean":mu,"std":sd,"state_dict":state,"best_val_loss":best},out/f"seed_{seed}.pt")
    return p,sum(v.numel() for v in model.parameters()),best

def auc(y,p):
    pos=y==1;n1=pos.sum();n0=(~pos).sum()
    if not n1 or not n0:return None
    o=np.argsort(p,kind="stable");r=np.empty(len(p));r[o]=np.arange(1,len(p)+1)
    for v in np.unique(p):
        i=np.where(p==v)[0]
        if len(i)>1:r[i]=r[i].mean()
    return float((r[pos].sum()-n1*(n1+1)/2)/(n1*n0))
def ap(y,p):
    if not y.sum():return None
    o=np.argsort(-p,kind="stable");yy=y[o];pp=p[o];ends=np.r_[np.where(pp[1:]!=pp[:-1])[0],len(pp)-1];tp=np.cumsum(yy)[ends]
    return float(np.sum(tp/(ends+1)*np.diff(np.r_[0,tp/y.sum()])))

def eval_all(p,target,allowed,exact,cold,tok,sp):
    out={}; upp=np.asarray(EDGES+(10**18,))
    for name,g in (("overall",np.ones(len(p),bool)),("cold",cold==1),("warm",cold==0)):
        test=(sp==2)&g; ex=test&(exact==1); pred=p.argmax(1); one=np.eye(10)[target[ex]]
        block={"exact_n":int(ex.sum()),"censored_n":int((test&(exact==0)).sum()),"bucket_accuracy":float((pred[ex]==target[ex]).mean()),"multiclass_brier":float(((p[ex]-one)**2).sum(1).mean()),"token_multiclass_brier":float(np.average(((p[ex]-one)**2).sum(1),weights=tok[ex])),"exact_nll":float(-np.log(np.clip(p[ex,target[ex]],1e-8,1)).mean()),"censor_aware_nll":float(censored_losses(torch.from_numpy(p[test]).log(),torch.from_numpy(allowed[test])).mean())}
        for h in (5,20,100):
            obs=test&((exact==1)|((allowed&(1<<bucket(h)))==0)); ix=np.where(obs)[0]; y=(exact[ix]==1)&(upp[target[ix]]<=h); score=p[ix,:bucket(h)+1].sum(1);br=(score-y)**2
            block[f"within_{h}"]={"n":len(ix),"positive_rate":float(y.mean()),"auc":auc(y,score),"ap":ap(y,score),"brier":float(br.mean()),"token_brier":float(np.average(br,weights=tok[ix]))}
        out[name]=block
    return out

def main():
    a=argparse.ArgumentParser();a.add_argument("--trace-dir",type=Path,required=True);a.add_argument("--unified-out",type=Path,required=True);a.add_argument("--heads-out",type=Path,required=True);q=a.parse_args()
    trace=max(q.trace_dir.glob("frontier_pid*.jsonl"),key=lambda p:p.stat().st_size);rows,end=load(trace)
    x=np.asarray([r[1] for r in rows],np.float32);target=np.asarray([r[2] for r in rows],np.int64);allowed=np.asarray([r[3] for r in rows],np.int64);exact=np.asarray([r[4] for r in rows],np.uint8);tok=np.asarray([r[5] for r in rows],np.float32);cold=np.asarray([r[6] for r in rows],np.float32);sp=np.asarray([split_of(r[0]) for r in rows],np.uint8)
    result={"trace":str(trace),"bucket_upper_edges":EDGES,"bucket_count":10,"rows":len(rows),"exact_rows":int(exact.sum()),"censored_rows":int((exact==0).sum()),"models":{}}
    for kind,out in (("unified",q.unified_out),("shared_and_heads",q.heads_out)):
        ps=[];runs=[]
        for seed in (41,42,43):
            p,n,b=train(kind,x,allowed,cold,sp,out/"checkpoints",seed);ps.append(p);runs.append({"seed":seed,"parameters":n,"best_val_loss":b})
        block={"runs":runs,"ensemble_test":eval_all(np.mean(ps,0),target,allowed,exact,cold,tok,sp)};result["models"][kind]=block
    for kind,out in (("unified",q.unified_out),("shared_and_heads",q.heads_out)):
        out.mkdir(parents=True,exist_ok=True);(out/"results.json").write_text(json.dumps({**result,"selected_model":kind},indent=2)+"\n")
    print(json.dumps(result["models"],indent=2))
if __name__=="__main__":main()
