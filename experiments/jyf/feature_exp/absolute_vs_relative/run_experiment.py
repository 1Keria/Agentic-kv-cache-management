"""Session-isolated absolute vs relative hazard experiment (seconds)."""
import argparse, bisect, hashlib, importlib.util, json
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import torch

def hashnum(s):
    return int(hashlib.sha256(str(s).encode()).hexdigest()[:12],16)

def build(base, trace):
    rows=[json.loads(l) for l in open(trace)]
    requests={r['req_seq']:r for r in rows if r['kind']=='request'}
    session_times=defaultdict(dict)
    for r in requests.values():
        if r.get('traffic') not in ('openhands','request'): continue
        st=session_times[r['sid']]
        st[r['turn']]=min(st.get(r['turn'],float('inf')),r['wall_s'])
    session_times={s:sorted(v.values()) for s,v in session_times.items()}
    owners=defaultdict(set); demands=defaultdict(list)
    for r in rows:
        if r['kind']=='demand':
            q=requests.get(r['req_seq'],{})
            owners[r['digest']].add(q.get('sid',''))
            demands[r['digest']].append((r['req_seq'],r['wall_s']))
    for d in demands: demands[d].sort()
    names=base.BOTH_CANDIDATE16
    cols=[base.ALL_NAMES.index(n) for n in names]
    out=defaultdict(list); audit=Counter(); end=max(r['wall_s'] for r in rows)
    for fi,f in enumerate(r for r in rows if r['kind']=='frontier'):
        for c in f['candidates']:
            audit['raw']+=1; dg=c['digest']; ss=owners[dg]
            if len(ss)!=1: audit['unknown_or_shared_prefix']+=1; continue
            s=next(iter(ss))
            if s not in session_times: audit['unknown_session']+=1; continue
            ds=demands[dg]; k=bisect.bisect_right([v[0] for v in ds],f['req_seq']); past=ds[:k]
            # Never infer current ownership from future demands alone.
            if not past: audit['no_past_owner_demand']+=1; continue
            if any(v[1]>f['wall_s'] for v in past): audit['invalid_chronology']+=1; continue
            # Require logged gap to agree with timestamp-reconstructible history.
            gap=c.get('recent_gap_req',-1)
            if gap>=0 and (len(past)<2 or past[-1][0]-past[-2][0]!=gap):
                audit['gap_not_reconstructible']+=1; continue
            feat,known=base.make_features(c,f['req_seq'],f['wall_s'],past)
            if not known: audit['unknown_idle']+=1; continue
            ts=session_times[s]; j=bisect.bisect_right(ts,f['wall_s'])
            gs=np.diff(ts[max(0,j-9):j]); gs=gs[gs>0]
            tau=float(np.median(gs)) if len(gs) else np.nan
            future=ds[k] if k<len(ds) else None
            dur=(future[1] if future else end)-f['wall_s']
            if dur<=0: audit['nonpositive_duration']+=1; continue
            for key,val in dict(x=np.asarray(feat)[cols],duration=dur,event=int(future is not None),
                                sid=s,digest=dg,frontier=fi,tau=tau,cold=c['cold'],tokens=c['kv_tokens']).items():
                out[key].append(val)
    data={k:np.asarray(v) for k,v in out.items()}
    sessions=sorted(set(data['sid']),key=hashnum); n=len(sessions)
    tr=set(sessions[:int(.7*n)]); va=set(sessions[int(.7*n):int(.85*n)])
    data['split']=np.array([0 if s in tr else 1 if s in va else 2 for s in data['sid']])
    audit.update(used=len(data['sid']),sessions=n)
    audit['splits']={str(i):{'rows':int(sum(data['split']==i)), 'sessions':len(set(data['sid'][data['split']==i]))} for i in range(3)}
    return data,dict(audit),names

def weights(tokens,cold):
    w=np.sqrt(np.maximum(tokens,1.)); out=np.zeros(len(w))
    for c in np.unique(cold):
        m=cold==c; out[m]=w[m]/w[m].sum()*len(w)/len(np.unique(cold))
    return out.astype('float32')

def survival(h,edges,t):
    t=np.broadcast_to(np.asarray(t), (len(h),)); ans=np.zeros(len(h)); left=0.
    for j,right in enumerate(edges):
        ans+=np.clip((t-left)/(right-left),0,1)*np.log(np.clip(1-h[:,j],1e-9,1)); left=right
    return np.exp(ans)

def median_time(h,edges):
    cum=np.cumsum(-np.log(np.clip(1-h,1e-9,1)),axis=1); ans=np.full(len(h),np.inf)
    for j,right in enumerate(edges):
        left=0 if j==0 else edges[j-1]; prior=0 if j==0 else cum[:,j-1]
        m=np.isinf(ans)&(cum[:,j]>=np.log(2))
        ans[m]=left+(np.log(2)-np.broadcast_to(prior,(len(h),))[m])/(cum[m,j]-np.broadcast_to(prior,(len(h),))[m])*(right-left)
    return ans

def fit(base,d,names,train,val,kind,seed,default,args):
    torch.manual_seed(seed); rng=np.random.default_rng(seed)
    tau=np.where(np.isfinite(d['tau']),d['tau'],default)
    x=d['x'].copy(); timecols=[i for i,n in enumerate(names) if n.endswith('_seconds')]
    if kind=='relative': x[:,timecols]=np.log1p(np.expm1(x[:,timecols])/tau[:,None])
    mean=x[train].mean(0); std=np.maximum(x[train].std(0),1e-5)
    xx=torch.tensor((x-mean)/std,dtype=torch.float32,device=args.device)
    scale=tau if kind=='relative' else np.ones(len(tau))
    dd=torch.tensor(d['duration']/scale,dtype=torch.float32,device=args.device)
    ee=torch.tensor(d['event'],dtype=torch.float32,device=args.device)
    edges=np.array(base.EDGES)/(default if kind=='relative' else 1)
    et=torch.tensor(edges,dtype=torch.float32,device=args.device)
    model=base.HazardNet(len(names)).to(args.device)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001)
    tw=torch.tensor(weights(d['tokens'][train],d['cold'][train]),device=args.device)
    vw=torch.tensor(weights(d['tokens'][val],d['cold'][val]),device=args.device)
    best=float('inf'); state=None; stale=0
    for epoch in range(args.epochs):
        model.train()
        for pos in np.array_split(rng.permutation(len(train)),max(1,int(np.ceil(len(train)/4096)))):
            ix=train[pos]; loss=base.hazard_loss(model(xx[ix]),dd[ix],ee[ix],et,tw[pos])
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad(): v=base.hazard_loss(model(xx[val]),dd[val],ee[val],et,vw).item()
        if v<best-1e-5: best=v; state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}; stale=0
        else: stale+=1
        if stale>=12: break
    model.load_state_dict(state)
    return model,mean,std,edges,{'seed':seed,'epochs':epoch+1,'val_own_unit_loss':best},state

def evaluate(h,edges,scale,d,idx,factor,base):
    dur=d['duration'][idx]*factor; ev=d['event'][idx].astype(bool)
    # Common finite interval, right-censor IPCW weights from this evaluation cohort.
    order=np.argsort(dur); u,first,count=np.unique(dur[order],return_index=True,return_counts=True)
    g=1.; before=[]; after=[]
    for t,a,c in zip(u,first,count):
        before.append(g); g*=1-np.sum(~ev[order[a:a+c]])/(len(dur)-a); after.append(g)
    before=np.array(before); after=np.array(after)
    g_event=np.maximum(before[np.searchsorted(u,dur)],1e-5)
    grid=np.unique(np.r_[np.linspace(0,600,121),5,20,60]); bs=[]; cells={}
    for t in grid:
        p=1-survival(h,edges,t/scale)
        y=ev&(dur<=t); alive=dur>t
        loc=np.searchsorted(u,t,side='right')-1; gt=1 if loc<0 else after[loc]
        b=(y*(1-p)**2/g_event+alive*p*p/max(gt,1e-5)).mean(); bs.append(b)
        if t in (5,20,60):
            known=y|alive; pp=np.clip(p[known],1e-7,1-1e-7); yy=y[known].astype(float)
            cells[str(int(t))]={'brier_ipcw':float(b),'n_known':int(known.sum()),'positive_rate_known':float(yy.mean()),
                'nll_known':float(np.mean(-yy*np.log(pp)-(1-yy)*np.log(1-pp))), 'auc_known':base.auc_score(yy,pp)}
    pred=median_time(h,edges)*scale
    # Per-row IPCW integrated Brier contributions for session bootstrap.
    contrib=[]
    for t in grid:
        p=1-survival(h,edges,t/scale); y=ev&(dur<=t); alive=dur>t
        loc=np.searchsorted(u,t,side='right')-1; gt=1 if loc<0 else after[loc]
        contrib.append(y*(1-p)**2/g_event+alive*p*p/max(gt,1e-5))
    integ=np.trapezoid(np.array(contrib),grid,axis=0)/600
    return {'ibs_0_600s':float(integ.mean()),'horizons':cells,'tail_median_fraction':float(np.isinf(pred).mean())},pred,integ

def pairs(d,idx,dur,ev,pred):
    aa=[]; bb=[]; scores=[]
    for f in np.unique(d['frontier'][idx]):
        ix=np.where(d['frontier'][idx]==f)[0]; a,b=np.triu_indices(len(ix),1); a=ix[a]; b=ix[b]
        ok=(d['sid'][idx[a]]!=d['sid'][idx[b]])&(((dur[a]<dur[b])&ev[a])|((dur[b]<dur[a])&ev[b]))
        a=a[ok]; b=b[ok]
        truth=dur[a]<dur[b]; tied=pred[a]==pred[b]
        sc=np.where(tied,.5,((pred[a]<pred[b])==truth).astype(float))
        aa.extend(a); bb.extend(b); scores.extend(sc)
    a=np.array(aa,int); b=np.array(bb,int); sc=np.array(scores)
    return {'accuracy':float(sc.mean()) if len(sc) else None,'n_pairs':len(sc)},(a,b,sc)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--base',type=Path,required=True); p.add_argument('--trace',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--device',default='cuda:0'); p.add_argument('--epochs',type=int,default=180); args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('base',args.base); base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    d,audit,names=build(base,args.trace); np.savez_compressed(args.out/'samples.npz',**d)
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2)); print(audit,flush=True)
    test=np.where(d['split']==2)[0]; val=np.where(d['split']==1)[0]; results={}; train_sessions=sorted(set(d['sid'][d['split']==0]),key=lambda s:hashnum('subset'+s))
    sid_test=d['sid'][test]; sessions=np.unique(sid_test); group=np.searchsorted(sessions,sid_test)
    rng=np.random.default_rng(822); boots=rng.multinomial(len(sessions),np.ones(len(sessions))/len(sessions),size=500)
    for fraction in (.25,1.):
        chosen=train_sessions[:max(1,int(len(train_sessions)*fraction))]; train=np.where((d['split']==0)&np.isin(d['sid'],chosen))[0]
        # One scale per training session avoids exposure-frequency weighted fallback.
        taus=[np.nanmedian(d['tau'][train][d['sid'][train]==s]) for s in chosen if np.isfinite(d['tau'][train][d['sid'][train]==s]).any()]
        default=float(np.median(taus)); result={'default_tau':default,'train_sessions':len(chosen),'train_rows':len(train),'models':{}}
        preds={}; contribs={}; pairdata={}
        scenarios={'ID':np.ones(len(test)),'x5':np.full(len(test),5.),'x10':np.full(len(test),10.),'mixed':np.array([ [1.,5.,10.][hashnum('scale'+s)%3] for s in sid_test])}
        for kind in ('absolute','relative'):
            forecasts=defaultdict(list); result['models'][kind]={'seeds':[],'scenarios':{}}
            for seed in range(41,46):
                model,mean,std,edges,meta,state=fit(base,d,names,train,val,kind,seed,default,args)
                torch.save({'state_dict':state,'mean':mean,'std':std,'edges':edges,'default_tau':default,'features':names,'kind':kind},args.out/f'{fraction}_{kind}_{seed}.pt')
                result['models'][kind]['seeds'].append(meta); print(fraction,kind,meta,flush=True)
                for scen,factor in scenarios.items():
                    tau=np.where(np.isfinite(d['tau'][test]),d['tau'][test]*factor,default)
                    x=d['x'][test].copy(); cc=[i for i,n in enumerate(names) if n.endswith('_seconds')]
                    x[:,cc]=np.log1p(np.expm1(x[:,cc])*factor[:,None]/(tau[:,None] if kind=='relative' else 1))
                    with torch.no_grad(): h=torch.sigmoid(model(torch.tensor((x-mean)/std,dtype=torch.float32,device=args.device))).cpu().numpy()
                    forecasts[scen].append(h)
            for scen,factor in scenarios.items():
                tau=np.where(np.isfinite(d['tau'][test]),d['tau'][test]*factor,default); scale=tau if kind=='relative' else np.ones(len(test))
                h=np.mean(forecasts[scen],axis=0); met,pred,con=evaluate(h,edges,scale,d,test,factor,base)
                pr,pd=pairs(d,test,d['duration'][test]*factor,d['event'][test].astype(bool),pred); met['ranking']=pr
                for label,mask in [('history',np.isfinite(d['tau'][test])),('fallback',~np.isfinite(d['tau'][test]))]:
                    met[label]={'n':int(mask.sum()),'ibs':float(con[mask].mean()) if mask.any() else None}
                result['models'][kind]['scenarios'][scen]=met; contribs[kind,scen]=con; pairdata[kind,scen]=pd
                np.savez_compressed(args.out/f'{fraction}_{kind}_{scen}_predictions.npz',hazards=h,median_seconds=pred,ibs_contribution=con)
        result['comparisons']={}
        for scen,factor in scenarios.items():
            diff=contribs['relative',scen]-contribs['absolute',scen]
            sums=np.bincount(group,weights=diff,minlength=len(sessions)); counts=np.bincount(group,minlength=len(sessions))
            bs=(boots@sums)/(boots@counts)
            a,b,sc=pairdata['relative',scen]; delta=sc-pairdata['absolute',scen][2]
            pb=[]
            for bt in boots:
                w=bt[group[a]]*bt[group[b]]
                if w.sum(): pb.append(float(w@delta/w.sum()))
            tau=np.where(np.isfinite(d['tau'][test]),d['tau'][test]*factor,default)
            naive,_=pairs(d,test,d['duration'][test]*factor,d['event'][test].astype(bool),tau)
            result['comparisons'][scen]={'ibs_delta_relative_minus_absolute':float(diff.mean()),'ibs_delta_ci95':np.quantile(bs,[.025,.975]).tolist(),
                 'ranking_delta_ci95':np.quantile(pb,[.025,.975]).tolist() if pb else [],'tau_only_ranking':naive}
        results[str(fraction)]=result
        (args.out/'results.json').write_text(json.dumps(results,indent=2))
    print('DONE',flush=True)

if __name__=='__main__': main()
