#!/usr/bin/env python3
"""Compare one unified MLP with a shared trunk and cold/warm heads."""

import argparse, bisect, hashlib, json, math, random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

HORIZONS = (5, 20, 100)
FEATURES = [
    "log_node_tokens", "log_path_tokens", "log_depth", "log_age_events",
    "lru_frac", "log_parent_hits", "log_siblings", "warm_sibling_fraction",
    "log_owner_turn", "is_cold", "log_hits", "gap_present",
    "log_recent_gap_events", "is_openhands", "is_request", "is_swa",
]


def digest_split(d):
    v = int.from_bytes(hashlib.blake2b(d.encode(), digest_size=8).digest(), "big") % 100
    return 0 if v < 70 else (1 if v < 85 else 2)


def features(c):
    siblings = max(0, int(c.get("siblings", 0))); gap = int(c.get("recent_gap_req", -1))
    traffic = c.get("owner_traffic", "")
    return [
        math.log1p(max(0, int(c.get("node_tokens", 0)))), math.log1p(max(0, int(c.get("path_tokens", 0)))),
        math.log1p(max(0, int(c.get("depth", 0)))), math.log1p(max(0, int(c.get("age_requests", 0)))),
        float(c.get("lru_frac", 0)), math.log1p(max(0, int(c.get("parent_hits", 0)))),
        math.log1p(siblings), max(0, int(c.get("warm_siblings", 0))) / max(siblings, 1),
        math.log1p(max(0, int(c.get("owner_turn", 0)))), float(c.get("cold", 0)),
        math.log1p(max(0, int(c.get("hits", 0)))), float(gap >= 0), math.log1p(max(gap, 0)),
        float(traffic == "openhands"), float(traffic == "request"), float(c.get("frontier") == "swa"),
    ]


def load_rows(trace):
    events=[]; demands=defaultdict(list); max_req=0
    for line in trace.open():
        r=json.loads(line); req=int(r.get("req_seq") or 0); max_req=max(max_req,req)
        if r.get("kind")=="frontier": events.append(r)
        elif r.get("kind")=="demand": demands[r["digest"]].append(req)
    for x in demands.values(): x.sort()
    rows=[]
    for e in events:
        req=int(e.get("req_seq") or 0)
        for c in e.get("candidates") or []:
            ds=demands.get(c["digest"],()); j=bisect.bisect_right(ds,req)
            nxt=ds[j] if j<len(ds) else None
            y=[]; mask=[]
            for h in HORIZONS:
                positive=nxt is not None and nxt-req<=h
                observed=positive or req+h<=max_req
                y.append(float(positive)); mask.append(float(observed))
            if any(mask):
                rows.append((c["digest"],features(c),y,mask,max(1,int(c.get("kv_tokens",0))),int(c.get("cold",0))))
    return rows,max_req


class Unified(nn.Module):
    def __init__(self,n):
        super().__init__(); self.trunk=nn.Sequential(nn.Linear(n,64),nn.ReLU(),nn.Linear(64,32),nn.ReLU()); self.head=nn.Linear(32,3)
    def forward(self,x,cold): return self.head(self.trunk(x))


class SharedHeads(nn.Module):
    def __init__(self,n):
        super().__init__(); self.trunk=nn.Sequential(nn.Linear(n,56),nn.ReLU(),nn.Linear(56,28),nn.ReLU())
        self.cold_head=nn.Linear(28,3); self.warm_head=nn.Linear(28,3)
    def forward(self,x,cold):
        z=self.trunk(x); return torch.where(cold[:,None]>0.5,self.cold_head(z),self.warm_head(z))


def balanced_loss(logits,y,mask,cold):
    raw=nn.functional.binary_cross_entropy_with_logits(logits,y,reduction="none")*mask
    vals=[]
    for flag in (0,1):
        g=(cold==flag)[:,None]*mask; den=g.sum()
        if den>0: vals.append((raw*g).sum()/den)
    return torch.stack(vals).mean()


def train(kind,x,y,mask,cold,split,out,seed):
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    tr=np.where(split==0)[0]; va=np.where(split==1)[0]
    mu=x[tr].mean(0); sd=x[tr].std(0); sd[sd<1e-5]=1; z=((x-mu)/sd).astype("float32")
    cls=Unified if kind=="unified" else SharedHeads; model=cls(x.shape[1]); opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4)
    ds=TensorDataset(torch.from_numpy(z[tr]),torch.from_numpy(y[tr]),torch.from_numpy(mask[tr]),torch.from_numpy(cold[tr]))
    loader=DataLoader(ds,batch_size=2048,shuffle=True,generator=torch.Generator().manual_seed(seed))
    best=1e9; state=None; patience=6
    for epoch in range(60):
        model.train()
        for xb,yb,mb,cb in loader:
            loss=balanced_loss(model(xb,cb),yb,mb,cb); opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad(): vl=balanced_loss(model(torch.from_numpy(z[va]),torch.from_numpy(cold[va])),torch.from_numpy(y[va]),torch.from_numpy(mask[va]),torch.from_numpy(cold[va])).item()
        if vl<best-1e-5: best=vl; state={k:v.detach().clone() for k,v in model.state_dict().items()}; patience=6
        else:
            patience-=1
            if patience==0: break
    model.load_state_dict(state); model.eval()
    with torch.no_grad(): p=torch.sigmoid(model(torch.from_numpy(z),torch.from_numpy(cold))).numpy()
    out.mkdir(parents=True,exist_ok=True)
    torch.save({"kind":kind,"seed":seed,"features":FEATURES,"horizons":HORIZONS,"mean":mu,"std":sd,"state_dict":state,"best_val_loss":best},out/f"seed_{seed}.pt")
    return p, sum(v.numel() for v in model.parameters()), best


def auc(y,p):
    pos=y==1; n1=pos.sum(); n0=(~pos).sum()
    if not n1 or not n0:return None
    order=np.argsort(p,kind="stable"); ranks=np.empty(len(p)); ranks[order]=np.arange(1,len(p)+1)
    for v in np.unique(p):
        ii=np.where(p==v)[0]
        if len(ii)>1:ranks[ii]=ranks[ii].mean()
    return float((ranks[pos].sum()-n1*(n1+1)/2)/(n1*n0))


def ap(y,p):
    if not y.sum():return None
    o=np.argsort(-p,kind="stable"); yy=y[o]; pp=p[o]; ends=np.r_[np.where(pp[1:]!=pp[:-1])[0],len(pp)-1]
    tp=np.cumsum(yy)[ends]; return float(np.sum(tp/(ends+1)*np.diff(np.r_[0,tp/y.sum()])))


def evaluate(y,mask,cold,tokens,split,p):
    out={}
    for group,gsel in (("overall",np.ones(len(y),bool)),("cold",cold==1),("warm",cold==0)):
        out[group]={}
        for j,h in enumerate(HORIZONS):
            ix=np.where((split==2)&gsel&(mask[:,j]>0))[0]; yy=y[ix,j]; pp=np.clip(p[ix,j],1e-6,1-1e-6); w=tokens[ix]
            br=(pp-yy)**2; nl=-(yy*np.log(pp)+(1-yy)*np.log(1-pp))
            out[group][str(h)]={"n":len(ix),"positive_rate":float(yy.mean()),"auc":auc(yy,pp),"ap":ap(yy,pp),"brier":float(br.mean()),"token_brier":float(np.average(br,weights=w)),"nll":float(nl.mean())}
    return out


def main():
    a=argparse.ArgumentParser(); a.add_argument("--trace-dir",type=Path,required=True); a.add_argument("--unified-out",type=Path,required=True); a.add_argument("--heads-out",type=Path,required=True); args=a.parse_args()
    trace=max(args.trace_dir.glob("frontier_pid*.jsonl"),key=lambda p:p.stat().st_size); rows,max_req=load_rows(trace)
    x=np.asarray([r[1] for r in rows],np.float32); y=np.asarray([r[2] for r in rows],np.float32); mask=np.asarray([r[3] for r in rows],np.float32)
    tokens=np.asarray([r[4] for r in rows],np.float32); cold=np.asarray([r[5] for r in rows],np.float32); split=np.asarray([digest_split(r[0]) for r in rows],np.uint8)
    summary={"trace":str(trace),"max_cache_access_event":max_req,"rows":len(rows),"features":FEATURES,"horizons":HORIZONS,"split_by":"prefix_digest","loss":"equal-weight cold/warm masked BCE","models":{}}
    for kind,outdir in (("unified",args.unified_out),("shared_and_heads",args.heads_out)):
        ps=[]; info=[]
        for seed in (41,42,43):
            pred,nparams,val=train(kind,x,y,mask,cold,split,outdir/"checkpoints",seed); ps.append(pred); info.append({"seed":seed,"parameters":nparams,"best_val_loss":val})
        pred=np.mean(ps,axis=0); block={"runs":info,"ensemble_test":evaluate(y,mask,cold,tokens,split,pred)}; summary["models"][kind]=block
        outdir.mkdir(parents=True,exist_ok=True); (outdir/"results.json").write_text(json.dumps({**summary,"selected_model":kind,"result":block},indent=2)+"\n")
    for outdir in (args.unified_out,args.heads_out): (outdir/"comparison.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary["models"],indent=2))

if __name__=="__main__": main()
