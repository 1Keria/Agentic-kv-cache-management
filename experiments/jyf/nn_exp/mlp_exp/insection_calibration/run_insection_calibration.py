#!/usr/bin/env python3
"""Calibration validation for within-bucket survival interpolation."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn

METHODS=("log_survival","linear_survival","right_step")

class HazardMLP(nn.Module):
    def __init__(self,n_in,n_out):
        super().__init__();self.net=nn.Sequential(nn.Linear(n_in,128),nn.ReLU(),nn.Linear(128,128),nn.ReLU(),nn.Linear(128,n_out))
    def forward(self,x):return self.net(x)

def load_predict(path,x):
    b=torch.load(path,map_location="cpu",weights_only=False);m=HazardMLP(b["n_in"],b["n_out"]);m.load_state_dict(b["state_dict"]);m.eval()
    z=((x-np.asarray(b["x_mean"],np.float32))/np.asarray(b["x_std"],np.float32)).astype(np.float32);out=[]
    with torch.no_grad():
        for i in range(0,len(z),16384):out.append(torch.sigmoid(m(torch.from_numpy(z[i:i+16384]))).numpy())
    return np.concatenate(out),np.asarray(b["edges"],float)

def survival(h,edges,t,method):
    s=np.ones(len(h),float);left=0.
    for j,right in enumerate(edges):
        q=np.clip(1-h[:,j],1e-9,1)
        if t>=right:s*=q
        elif t>left:
            u=(t-left)/(right-left)
            if method=="log_survival":s*=q**u
            elif method=="linear_survival":s*=1-u*h[:,j]
            break
        else:break
        left=right
    return np.clip(s,1e-12,1)

def km_risk(d,e,t,w):
    s=1.;risk=float(w.sum())
    for z in np.unique(d[d<=t]):
        at=d==z;ev=float(w[at&e].sum())
        if risk>0:s*=max(0.,1-ev/risk)
        risk-=float(w[at].sum())
    return 1-s

def reliability(pred,d,e,t,w,method,kind):
    order=np.argsort(pred);groups=np.array_split(order,10);rows=[];total=float(w.sum());ece=0.
    for bi,g in enumerate(groups):
        if not len(g):continue
        pw=float(np.average(pred[g],weights=w[g]));obs=float(km_risk(d[g],e[g],t,w[g]));mass=float(w[g].sum()/total);ece+=mass*abs(pw-obs)
        rows.append({"kind":kind,"method":method,"time_s":t,"bin":bi,"n":len(g),"weight":float(w[g].sum()),"predicted_risk":pw,"km_observed_risk":obs,"abs_error":abs(pw-obs)})
    return ece,rows

def write_csv(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        fields=[]
        for row in rows:
            for key in row:
                if key not in fields: fields.append(key)
        q=csv.DictWriter(f,fieldnames=fields);q.writeheader();q.writerows(rows)

def main():
    a=argparse.ArgumentParser();a.add_argument("--data",type=Path,required=True);a.add_argument("--checkpoint-root",type=Path,required=True);a.add_argument("--out-dir",type=Path,required=True);q=a.parse_args();q.out_dir.mkdir(parents=True,exist_ok=True)
    z=np.load(q.data,allow_pickle=False);sel=(z["split"]==2)&(z["history"]>=1)&(z["duration"]>1e-6);x=z["x"][sel];d=z["duration"][sel].astype(float);e=z["event"][sel].astype(bool);tw=np.maximum(z["weight"][sel].astype(float),1.)
    hs=[];edges=None
    for seed in (41,42,43):
        h,ed=load_predict(q.checkpoint_root/f"seed_{seed}"/"initial.pt",x);hs.append(h);edges=ed
    interior=[];left=0.
    for right in edges:
        for u in (.1,.25,.5,.75,.9):interior.append((left+u*(right-left),left,right,u))
        left=right
    points=sorted(set(edges.tolist()+[x[0] for x in interior]));rels=[];point_rows=[]
    for method in METHODS:
        risks=np.stack([1-np.mean([survival(h,edges,t,method) for h in hs],axis=0) for t in points],axis=1)
        for j,t in enumerate(points):
            for weighting,w in (("object",np.ones(len(d))),("token",tw)):
                ec,rr=reliability(risks[:,j],d,e,t,w,method,"absolute");rels+=rr
                point_rows.append({"method":method,"weighting":weighting,"time_s":t,"is_edge":int(t in set(edges)),"km_ece10":ec,"mean_predicted_risk":float(np.average(risks[:,j],weights=w)),"km_observed_risk":float(km_risk(d,e,t,w))})
    pairs=[(5,5),(5,20),(5,60),(20,5),(20,20),(20,60),(60,20),(60,60),(60,180),(600,600),(600,1800),(600,3600),(1800,600),(1800,1800),(1800,3600)]
    cond=[]
    for method in METHODS:
        for age,hor in pairs:
            if age+hor>edges[-1]:continue
            alive=d>age;dd=d[alive]-age;ee=e[alive];ww=tw[alive]
            sa=np.mean([survival(h[alive],edges,age,method) for h in hs],axis=0);sb=np.mean([survival(h[alive],edges,age+hor,method) for h in hs],axis=0);pr=1-np.clip(sb/sa,0,1)
            for weighting,w in (("object",np.ones(len(dd))),("token",ww)):
                ec,rr=reliability(pr,dd,ee,hor,w,method,"conditional");
                for r in rr:r.update({"age_s":age,"horizon_s":hor})
                rels+=rr;cond.append({"method":method,"weighting":weighting,"age_s":age,"horizon_s":hor,"n_at_risk":len(dd),"km_ece10":ec,"mean_predicted_risk":float(np.average(pr,weights=w)),"km_observed_risk":float(km_risk(dd,ee,hor,w))})
    finite=set(edges);summ=[]
    for method in METHODS:
        for weighting in ("object","token"):
            rr=[r for r in point_rows if r["method"]==method and r["weighting"]==weighting and not r["is_edge"]]
            cc=[r for r in cond if r["method"]==method and r["weighting"]==weighting]
            summ.append({"method":method,"weighting":weighting,"interior_mean_km_ece10":float(np.mean([r["km_ece10"] for r in rr])),"interior_p90_km_ece10":float(np.quantile([r["km_ece10"] for r in rr],.9)),"conditional_mean_km_ece10":float(np.mean([r["km_ece10"] for r in cc])),"conditional_p90_km_ece10":float(np.quantile([r["km_ece10"] for r in cc],.9))})
    payload={"eligible_test_samples":len(d),"events":int(e.sum()),"censored":int((~e).sum()),"edges_s":edges.tolist(),"interior_fractions":[.1,.25,.5,.75,.9],"seeds":[41,42,43],"summary":summ,"point_calibration":point_rows,"conditional_calibration":cond}
    (q.out_dir/"results.json").write_text(json.dumps(payload,indent=2)+"\n");write_csv(q.out_dir/"point_calibration.csv",point_rows);write_csv(q.out_dir/"conditional_calibration.csv",cond);write_csv(q.out_dir/"reliability_bins.csv",rels)
    lines=["# Log-survival interpolation calibration","",f"Held-out samples: {len(d):,}; events: {e.sum():,}; censored: {(~e).sum():,}.","","| weighting | method | interior mean ECE10 | interior p90 | conditional mean ECE10 | conditional p90 |","|---|---|---:|---:|---:|---:|"]
    for r in summ:lines.append(f"| {r['weighting']} | {r['method']} | {r['interior_mean_km_ece10']:.5f} | {r['interior_p90_km_ece10']:.5f} | {r['conditional_mean_km_ece10']:.5f} | {r['conditional_p90_km_ece10']:.5f} |")
    lines += ["","ECE uses deciles of predicted risk and Kaplan–Meier observed risk inside each decile. Lower is better.","","Limitations: the existing training loss used log-survival for partial censoring, so model-level results mildly favor log interpolation; trajectory IDs are not retained in the NPZ, so cluster-bootstrap confidence intervals are not available in this run."]
    (q.out_dir/"report.md").write_text("\n".join(lines)+"\n");print(q.out_dir/"report.md")
if __name__=="__main__":main()
