#!/usr/bin/env python3
"""Ideal single-session, non-evicting radix-node experiment."""
from __future__ import annotations
import argparse, collections, hashlib, json
from datetime import datetime
from pathlib import Path
import numpy as np

OLD10=["node_tokens","path_tokens","age_seconds","idle_seconds","hits","gap_present","recent_gap_seconds","gap_ewma_seconds","gap_std_seconds","is_agent"]
CAND8=["creation_turn_fraction","endpoint_is_tool","tool_schema_count","last_message_is_tool","last_message_is_user","prefix_gap_ewma_rel","prefix_reuse_rate8","prefix_turn_gap_last"]
ALL=OLD10+CAND8

def dg(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def msg_size(m):
    return max(1,len(json.dumps({k:m.get(k) for k in ("content","reasoning_content","tool_calls") if k in m},sort_keys=True,ensure_ascii=False,separators=(",",":"))))
def robust_stats(gs):
    if not gs:return (0.,0.,0.)
    a=np.asarray(gs[-8:],dtype=np.float64); ew=a[0]
    for v in a[1:]:ew=.6*v+.4*ew
    return float(a[-1]),float(ew),float(a.std())

def build(inp:Path,out:Path):
    sessions=collections.defaultdict(list); audit=collections.Counter()
    for line in inp.open(encoding="utf-8"):
        try:
            r=json.loads(line); q=json.loads(r["prompt_body"]); ms=q["messages"]
            ui=next(i for i,m in enumerate(ms) if m.get("role")=="user")
            t=datetime.fromisoformat(r["start_time"].replace("Z","+00:00")).timestamp()
            sid=dg([r.get("tenant_id",""),ms[ui]]); schema=q.get("tools") or []
            md=[dg(m) for m in ms]; sizes=[msg_size(m) for m in ms]
            sessions[sid].append(dict(t=t,md=md,sizes=sizes,roles=[m.get("role","") for m in ms],schema=dg(schema),tool_count=len(schema)))
            audit["requests_parsed"]+=1
        except Exception:audit["malformed"]+=1
    keys=sorted(sessions,key=lambda s:int(dg(s)[:12],16)); n=len(keys)
    tr=set(keys[:int(.70*n)]); va=set(keys[int(.70*n):int(.85*n)])
    rows=[]; durations=[]; events=[]; row_sid=[]; split=[]; taus=[]
    for sid in keys:
        reqs=sorted(sessions[sid],key=lambda r:r["t"])
        if len(reqs)<2: audit["sessions_lt2"]+=1; continue
        sp=0 if sid in tr else 1 if sid in va else 2
        states={}; req_gaps=[]; prev=None; turn=0; seen=set(); session_end=reqs[-1]["t"]
        for r in reqs:
            sig=(r["t"],tuple(r["md"]))
            if sig in seen: audit["duplicate_request"]+=1; continue
            seen.add(sig)
            if prev is not None and r["t"]<=prev["t"]: audit["non_monotone"]+=1; continue
            turn+=1
            if prev is not None:req_gaps.append(r["t"]-prev["t"])
            tau=float(np.median(req_gaps[-8:])) if req_gaps else np.nan
            total=float(sum(r["sizes"])); cumulative=np.cumsum(r["sizes"]).astype(float)
            for end in range(len(r["md"])):
                nk=dg({"schema":r["schema"],"messages":r["md"][:end+1]})
                st=states.setdefault(nk,dict(created_turn=turn,created_t=r["t"],last_t=None,turns=[],gaps=[]))
                if st["last_t"] is not None:
                    j=st["pending"]; durations[j]=r["t"]-st["last_t"]; events[j]=1.; st["gaps"].append(r["t"]-st["last_t"])
                last_gap,ewma,gstd=robust_stats(st["gaps"]); last_turn=st["turns"][-1] if st["turns"] else turn
                role=r["roles"][end] if end<len(r["roles"]) else ""
                vals=[float(r["sizes"][end]),float(cumulative[end]),float(r["t"]-st["created_t"]),float(0 if st["last_t"] is None else r["t"]-st["last_t"]),float(len(st["turns"])),float(bool(st["gaps"])),last_gap,ewma,gstd,0.,
                      float(st["created_turn"]/max(turn,1)),float(role=="tool"),float(r["tool_count"]),float(r["roles"][-1]=="tool"),float(r["roles"][-1]=="user"),
                      float(ewma/tau) if np.isfinite(tau) and tau>0 else np.nan,float(sum(v>turn-8 for v in st["turns"])/max(1,min(8,turn-st["created_turn"]+1))),float(turn-last_turn)]
                row=len(rows); rows.append(vals); durations.append(session_end-r["t"]); events.append(0.); row_sid.append(sid); split.append(sp); taus.append(tau)
                st["pending"]=row; st["last_t"]=r["t"]; st["turns"].append(turn)
            prev=r
    x=np.asarray(rows,np.float32); d=np.asarray(durations,np.float32); e=np.asarray(events,np.float32); tau=np.asarray(taus,np.float32); sp=np.asarray(split,np.int8)
    for name in ("node_tokens","path_tokens","age_seconds","idle_seconds","hits","recent_gap_seconds","gap_ewma_seconds","gap_std_seconds","tool_schema_count","prefix_turn_gap_last"):
        j=ALL.index(name); x[:,j]=np.log1p(np.maximum(x[:,j],0))
    np.savez_compressed(out/"node_samples.npz",x=x,duration_seconds=d,duration_relative=d/np.maximum(tau,1e-6),event=e,split=sp,tau=tau,session=np.asarray(row_sid))
    meta={"feature_names":ALL,"old10":OLD10,"candidate8":CAND8,"audit":dict(audit,rows=len(rows),sessions=len(keys),train_sessions=len(tr),val_sessions=len(va),test_sessions=len(keys)-len(tr)-len(va),uncensored=int(e.sum()),censored=int((1-e).sum()),relative_tau_known=int(np.isfinite(tau).sum())),"unit":"persistent radix prefix node demand inside one session","session_policy":"one independent tree per inferred session; no cross-session node/history sharing","eviction":"disabled","node_key":"schema hash plus cumulative message-digest prefix; message is an edge segment, not a sample node","label":"next demand wall-clock seconds for the same node; final demand censored at session end","is_agent":"input has no explicit workload field; stored as constant zero"}
    (out/"node_dataset_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)); return meta

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--data",type=Path,required=True); ap.add_argument("--out",type=Path,required=True); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True); print(json.dumps(build(a.data,a.out),ensure_ascii=False,indent=2))

