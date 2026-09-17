"""Session-only logical-prefix candidate screening; no serving state inputs."""
import argparse, collections, hashlib, json, math, time
from datetime import datetime
from pathlib import Path
import numpy as np
import torch
from torch import nn

# description, group, transform; relative times use -1 as missing after log1p.
FEATURES = {
 'prefix_fraction':('目标逻辑 prefix 的内容长度 / 当前 context 内容长度','position','identity'),
 'segment_fraction':('prefix 最后一个 message 的内容长度 / 当前 context 内容长度','position','identity'),
 'creation_turn_fraction':('prefix 首次出现的 turn index / 当前 turn index（从1计）','position','identity'),
 'endpoint_is_tool':('prefix 最后一个 message 是否为 tool','position','identity'),
 'endpoint_is_assistant':('prefix 最后一个 message 是否为 assistant','position','identity'),
 'context_chars':('当前 message context 的规范化字符长度，独立于 serving tokenizer','context','log1p'),
 'tool_schema_fraction':('tool schema 字符长度 / (schema + message context 字符长度)','context','identity'),
 'tool_schema_count':('当前请求声明的可用 tool 数量；0同时表示无tool','context','log1p'),
 'tool_content_fraction':('当前 context 中 tool message 内容长度比例','context','identity'),
 'assistant_content_fraction':('当前 context 中 assistant message 内容长度比例','context','identity'),
 'tool_call_density':('当前 context 中 tool call 数 / assistant message 数','context','log1p'),
 'last_message_is_tool':('当前已知 context 最后一个 message 是否为 tool','context','identity'),
 'last_message_is_user':('当前已知 context 最后一个 message 是否为 user','context','identity'),
 'last_assistant_call_count':('当前 context 最近一个 assistant message 中 tool call 数','context','log1p'),
 'context_growth_fraction':('当前与上一请求 context 长度之差 / 上一 context 长度，可负','evolution','signed_log1p'),
 'rewritten_fraction':('上一请求 context 中未保留为当前公共前缀的内容比例','evolution','identity'),
 'new_tool_messages':('当前相对上一请求新增/改写后缀中的 tool message 数','evolution','log1p'),
 'new_user_messages':('当前相对上一请求新增/改写后缀中的 user message 数','evolution','log1p'),
 'tool_schema_changed':('当前与上一请求的工具声明是否不同','evolution','identity'),
 'session_turn':('session 已观测请求数，按时间去重；非全局事件数','session','log1p'),
 'session_gap_last_rel':('session 最近请求间隔 / 当前 session τ','session','relative'),
 'session_gap_lag2_rel':('session 倒数第二个请求间隔 / 当前 session τ','session','relative'),
 'session_gap_ewma_rel':('session 最近最多8个 gap 的 EWMA / τ，alpha=.6','session','relative'),
 'session_gap_std_rel':('session 最近最多8个 gap 的标准差 / τ','session','relative'),
 'prefix_gap_last_rel':('本session对目标prefix最近需求间隔 / τ','prefix_history','relative'),
 'prefix_gap_lag2_rel':('本session对目标prefix倒数第二个需求间隔 / τ','prefix_history','relative'),
 'prefix_gap_ewma_rel':('本session对prefix最近最多8个 gap 的 EWMA / τ','prefix_history','relative'),
 'prefix_gap_std_rel':('本session对prefix最近最多8个 gap 的标准差 / τ','prefix_history','relative'),
 'prefix_reuse_rate8':('prefix存在期间最近最多8个session请求中包含该prefix的比例','prefix_history','identity'),
 'prefix_turn_gap_last':('最近两次包含该prefix的session请求相隔的turn数','prefix_history','log1p'),
 'prefix_age_rel':('该逻辑prefix首次在session出现至今的时间 / τ','prefix_history','relative'),
 'prefix_reuse_count':('本session对该prefix已经完成的再次需求次数，独立于缓存hit','prefix_history','log1p'),
}
NAMES=list(FEATURES)
REL=[i for i,n in enumerate(NAMES) if FEATURES[n][2]=='relative']
EDGES=np.array([.125,.25,.5,1,2,4,8,16,64],dtype=np.float64)
GRID=np.unique(np.r_[np.linspace(0,8,65),.25,.5,1,2,4])

def digest(o):
 return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def number(s): return int(hashlib.sha256(str(s).encode()).hexdigest()[:12],16)
def size(m):
 # Ignore transient call ids for LENGTH only; prefix identity still exact message.
 return max(1,len(json.dumps({k:v for k,v in m.items() if k in ('content','reasoning_content','tool_calls')},sort_keys=True,ensure_ascii=False,separators=(',',':'))))
def stats(gs):
 if not gs: return -1.,-1.,-1.,-1.
 a=np.asarray(gs[-8:]); ew=a[0]
 for v in a[1:]: ew=.6*v+.4*ew
 return a[-1],a[-2] if len(a)>1 else -1.,float(ew),float(a.std())

def build(path,out):
 sessions=collections.defaultdict(list); audit=collections.Counter(); earliest=float('inf'); latest=0
 for line in open(path,encoding='utf-8'):
  try:
   r=json.loads(line); q=json.loads(r['prompt_body']); ms=q['messages']; u=next(i for i,m in enumerate(ms) if m.get('role')=='user')
   t=datetime.fromisoformat(r['start_time'].replace('Z','+00:00')).timestamp()
   sid=digest([r.get('tenant_id',''),ms[u]])
   mh=[digest(m) for m in ms]; lengths=[size(m) for m in ms]; schema=q.get('tools') or []
   chain=digest({'tools':schema,'system_before_user':ms[:u]}); prefixes=[]
   for i in range(u,len(ms)):
    chain=digest([chain,mh[i]]);prefixes.append((i,chain))
   roles=[m.get('role','') for m in ms]; calls=[len(m.get('tool_calls') or []) for m in ms]
   sessions[sid].append(dict(t=t,mh=mh,lengths=lengths,prefixes=prefixes,roles=roles,calls=calls,schema=digest(schema),schema_len=len(json.dumps(schema,ensure_ascii=False)) if schema else 0,tool_count=len(schema)))
   earliest=min(earliest,t);latest=max(latest,t);audit['requests_parsed']+=1
  except Exception:audit['malformed']+=1
 keys=sorted(sessions,key=number); ns=len(keys); train_s=set(keys[:int(.7*ns)]);val_s=set(keys[int(.7*ns):int(.85*ns)])
 rows=[]; durations=[]; events=[]; sidrows=[]; pgrows=[]; taus=[]; splits=[]; obs=[]; ticks=[]
 for si,sid in enumerate(keys):
  reqs=sorted(sessions[sid],key=lambda r:r['t']); ps={}; sg=[]; prev=None; seen_req=set()
  sp=0 if sid in train_s else 1 if sid in val_s else 2; turn=0
  for r in reqs:
   signature=(r['t'],tuple(r['mh']))
   if signature in seen_req:audit['duplicate_request']+=1;continue
   seen_req.add(signature)
   if prev and r['t']<=prev['t']:audit['equal_timestamp_dropped']+=1;continue
   turn+=1
   if prev:sg.append(r['t']-prev['t'])
   tau=float(np.median(sg[-8:])) if sg else np.nan
   total=sum(r['lengths']); common=0
   if prev:
    for a,b in zip(prev['mh'],r['mh']):
     if a!=b:break
     common+=1
   suffix=r['roles'][common:] if prev else []
   sstats=stats(sg); ass=[i for i,x in enumerate(r['roles']) if x=='assistant']
   context=dict(context_chars=total,tool_schema_fraction=r['schema_len']/(total+r['schema_len']),tool_schema_count=r['tool_count'],
    tool_content_fraction=sum(v for v,role in zip(r['lengths'],r['roles']) if role=='tool')/total,
    assistant_content_fraction=sum(v for v,role in zip(r['lengths'],r['roles']) if role=='assistant')/total,
    tool_call_density=sum(r['calls'])/max(len(ass),1),last_message_is_tool=float(r['roles'][-1]=='tool'),last_message_is_user=float(r['roles'][-1]=='user'),
    last_assistant_call_count=r['calls'][ass[-1]] if ass else 0,
    context_growth_fraction=(total-sum(prev['lengths']))/max(sum(prev['lengths']),1) if prev else 0,
    rewritten_fraction=1-sum(prev['lengths'][:common])/sum(prev['lengths']) if prev else 0,
    new_tool_messages=suffix.count('tool'),new_user_messages=suffix.count('user'),tool_schema_changed=float(prev is not None and prev['schema']!=r['schema']),
    session_turn=turn,session_gap_last_rel=sstats[0],session_gap_lag2_rel=sstats[1],session_gap_ewma_rel=sstats[2],session_gap_std_rel=sstats[3],session_gap_count=len(sg))
   cumulative=np.cumsum(r['lengths'])
   for end,pref in r['prefixes']:
    if pref not in ps: ps[pref]=dict(created=turn,created_t=r['t'],turns=[],times=[],gaps=[],pending=None)
    st=ps[pref]
    if st['times']:
     gap=r['t']-st['times'][-1];durations[st['pending']]=gap;events[st['pending']]=1;st['gaps'].append(gap)
    turngap=turn-st['turns'][-1] if st['turns'] else 0
    st['turns'].append(turn);st['times'].append(r['t']); gst=stats(st['gaps'])
    vals=dict(context,prefix_fraction=cumulative[end]/total,segment_fraction=r['lengths'][end]/total,creation_turn_fraction=st['created']/turn,
     endpoint_is_tool=float(r['roles'][end]=='tool'),endpoint_is_assistant=float(r['roles'][end]=='assistant'),
     prefix_gap_last_rel=gst[0],prefix_gap_lag2_rel=gst[1],prefix_gap_ewma_rel=gst[2],prefix_gap_std_rel=gst[3],
     prefix_reuse_rate8=sum(v>turn-8 for v in st['turns'])/min(8,turn-st['created']+1),prefix_turn_gap_last=turngap,
     prefix_age_rel=r['t']-st['created_t'],prefix_reuse_count=len(st['turns'])-1)
    st['pending']=len(rows);rows.append([vals[n] for n in NAMES]);durations.append(max(latest-r['t'],1e-5));events.append(0)
    sidrows.append(si);pgrows.append(pref);taus.append(tau);splits.append(sp);obs.append(r['t']);ticks.append(turn)
   prev=r
 raw=np.array(rows,np.float64);split=np.array(splits);tau=np.array(taus)
 # Training-only fallback. Test timestamps and test future gaps never enter it.
 # Placeholder used only to materialize arrays; unknown-tau samples are excluded below.
 tau_known=np.isfinite(tau);fallback=None;tau=np.where(tau_known,tau,1.)
 for j,n in enumerate(NAMES):
  kind=FEATURES[n][2]
  if kind=='relative':raw[:,j]=np.where(raw[:,j]>=0,np.log1p(np.maximum(raw[:,j],0)/tau),-1.)
  elif kind=='log1p':raw[:,j]=np.log1p(np.maximum(raw[:,j],0))
  elif kind=='signed_log1p':raw[:,j]=np.sign(raw[:,j])*np.log1p(np.abs(raw[:,j]))
 data=dict(x=raw.astype('float32'),duration=(np.array(durations)/tau).astype('float32'),duration_seconds=np.array(durations),event=np.array(events,'float32'),
   sid=np.array(sidrows),prefix=np.array(pgrows),split=split,tau=tau,observed_at=np.array(obs),turn=np.array(ticks))
 audit['excluded_unknown_session_tau']=int((~tau_known).sum())
 data={k:v[tau_known] for k,v in data.items()}
 # Same inferred session remains in one split; identical first-user anchors across tenants excluded from crossing via identity? audit only.
 audit.update(raw_samples=len(rows),samples=len(data['sid']),inferred_sessions=ns,
  sessions=len(np.unique(data['sid'])),train_sessions=len(np.unique(data['sid'][data['split']==0])),
  val_sessions=len(np.unique(data['sid'][data['split']==1])),test_sessions=len(np.unique(data['sid'][data['split']==2])))
 meta=dict(audit=audit,fallback_tau=fallback,clock_start=earliest,clock_end=latest,features=FEATURES,
   limitations=['Session inferred as tenant + first user message; not authoritative session ID.', 'Request-start gaps include historical service latency; no completion timestamps.',
    'Logical message-boundary prefixes use exact message and tools hashes; no physical KV/tokenization state.'])
 np.savez_compressed(out/'samples.npz',**data);(out/'dataset_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
 return data,meta

class Net(nn.Module):
 def __init__(self):
  super().__init__();self.net=nn.Sequential(nn.Linear(len(NAMES),64),nn.ReLU(),nn.Linear(64,64),nn.ReLU(),nn.Linear(64,9))
 def forward(self,x):return self.net(x)

def loss(logits,d,e,edges,w=None):
 ls=torch.nn.functional.logsigmoid(-logits);lh=torch.nn.functional.logsigmoid(logits);idx=torch.bucketize(d,edges,right=True)
 ll=(ls*(torch.arange(9,device=d.device)[None,:]<idx[:,None])).sum(1)
 hit=(e>.5)&(idx<9);rs=torch.where(hit)[0];ll[rs]+=lh[rs,idx[rs]]
 cens=(e<.5)&(idx<9);rs=torch.where(cens)[0];j=idx[rs];left=torch.where(j==0,0,edges[(j-1).clamp_min(0)])
 ll[rs]+=((d[rs]-left)/(edges[j]-left)).clamp(0,1)*ls[rs,j]
 return (-ll if w is None else -ll*w).mean()

def surv(h,t):
 ans=np.zeros(len(h));left=0
 for j,right in enumerate(EDGES):ans+=np.clip((t-left)/(right-left),0,1)*np.log(np.clip(1-h[:,j],1e-8,1));left=right
 return np.exp(ans)

def rank(a):
 order=np.argsort(a,kind='stable');v=a[order];out=np.empty(len(a));ends=np.r_[0,np.where(v[1:]!=v[:-1])[0]+1,len(v)]
 for l,r in zip(ends[:-1],ends[1:]):out[order[l:r]]=(l+r-1)/2
 return out

def correlation(d,out):
 tr=np.where(d['split']==0)[0];rng=np.random.default_rng(37)
 if len(tr)>60000:tr=rng.choice(tr,60000,replace=False)
 x=d['x'][tr];active=[i for i in range(len(NAMES)) if np.std(x[:,i])>1e-7]
 dropped={NAMES[i]:'constant on training' for i in range(len(NAMES)) if i not in active}
 for i in list(active):
  for j in active:
   if j>=i:break
   if np.array_equal(x[:,i],x[:,j]):dropped[NAMES[i]]='identical to '+NAMES[j];active.remove(i);break
 ranked=np.array([rank(x[:,j]) for j in active]).T;corr=np.corrcoef(ranked,rowvar=False)
 matrix={'names':[NAMES[j] for j in active],'spearman':corr.tolist(),'dropped':dropped}
 # Censor-aware threshold point-biserial association; not raw-duration correlation over positives only.
 scores=[]
 for j in active:
  cells={}
  for h in (1,2,4):
   y=(d['event'][tr]>.5)&(d['duration'][tr]<=h);known=y|(d['duration'][tr]>h)
   if known.sum()>2 and y[known].std()>0 and x[known,j].std()>0:cells[str(h)]=float(np.corrcoef(rank(x[known,j]),y[known])[0,1])
  scores.append({'feature':NAMES[j],'threshold_rank_correlation':cells})
 matrix['target_associations']=scores;(out/'correlations.json').write_text(json.dumps(matrix,indent=2))
 return active

def evaluation(h,d,ix):
 h=h[ix]
 dur=d['duration'][ix];ev=d['event'][ix]>.5
 # IPCW censoring KM, ensemble metrics over exactly the same cohort.
 order=np.argsort(dur);u,first,count=np.unique(dur[order],return_index=True,return_counts=True);g=1.;be=[];af=[]
 for t,a,c in zip(u,first,count):be.append(g);g*=1-(~ev[order[a:a+c]]).sum()/(len(dur)-a);af.append(g)
 be=np.array(be);af=np.array(af);ge=np.maximum(be[np.searchsorted(u,dur)],1e-4);curves=[];cells={}
 for t in GRID:
  p=1-surv(h,t);yes=ev&(dur<=t);alive=dur>t;j=np.searchsorted(u,t,side='right')-1;gt=1 if j<0 else af[j]
  b=yes*(1-p)**2/ge+alive*p*p/max(gt,1e-4);curves.append(b)
  if t in (1,2,4):
   known=yes|alive;y=yes[known].astype(float);pp=np.clip(p[known],1e-6,1-1e-6)
   ranks=rank(pp)+1;np_=y.sum();nn_=len(y)-np_;auc=float((ranks[y>0].sum()-np_*(np_+1)/2)/(np_*nn_)) if np_*nn_ else None
   cells[str(int(t))]={'brier':float(b.mean()),'nll_known':float(np.mean(-y*np.log(pp)-(1-y)*np.log(1-pp))),'auc':auc,'n':len(y),'positive_rate':float(y.mean())}
 ib=np.trapezoid(curves,GRID,axis=0)/8
 return {'ibs_0_8_relative':float(ib.mean()),'thresholds':cells},ib

def fit(d,cols,seed,args,save=None):
 torch.manual_seed(seed);rng=np.random.default_rng(seed);tr=np.where(d['split']==0)[0];va=np.where(d['split']==1)[0]
 mean=d['x'][tr].mean(0);std=np.maximum(d['x'][tr].std(0),1e-5);x=(d['x']-mean)/std;exclude=np.ones(len(NAMES),bool);exclude[cols]=False;x[:,exclude]=0
 xx=torch.tensor(x,device=args.device);dd=torch.tensor(d['duration'],device=args.device);ee=torch.tensor(d['event'],device=args.device);edges=torch.tensor(EDGES,dtype=torch.float32,device=args.device)
 model=Net().to(args.device);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001)
 # Equal total weight per training session prevents long prefixes/trajectories dominating training.
 _,inv,ct=np.unique(d['sid'][tr],return_inverse=True,return_counts=True);ww=len(tr)/len(ct)/ct[inv];ww=torch.tensor(ww,dtype=torch.float32,device=args.device)
 best=float('inf');state=None;stale=0
 for epoch in range(args.epochs):
  model.train()
  for pos in np.array_split(rng.permutation(len(tr)),max(1,int(np.ceil(len(tr)/8192)))):
   ix=tr[pos];l=loss(model(xx[ix]),dd[ix],ee[ix],edges,ww[pos]);opt.zero_grad();l.backward();opt.step()
  model.eval()
  with torch.no_grad():v=loss(model(xx[va]),dd[va],ee[va],edges).item()
  if v<best-1e-5:best=v;state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};stale=0
  else:stale+=1
  if stale>=6:break
 model.load_state_dict(state);model.eval()
 with torch.no_grad():h=torch.sigmoid(model(xx)).cpu().numpy()
 if save:torch.save({'state_dict':state,'mean':mean,'std':std,'columns':cols,'features':NAMES,'edges':EDGES.tolist()},save)
 return h,{'seed':seed,'epochs':epoch+1,'validation_loss':best}

def main():
 pa=argparse.ArgumentParser();pa.add_argument('--data',type=Path,required=True);pa.add_argument('--out',type=Path,required=True);pa.add_argument('--device',default='cuda:0');pa.add_argument('--epochs',type=int,default=60);args=pa.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
 if (out/'samples.npz').exists():z=np.load(out/'samples.npz');d={k:z[k] for k in z.files};meta=json.loads((out/'dataset_meta.json').read_text())
 else:d,meta=build(args.data,out)
 print('DATA',meta['audit'],flush=True);active=correlation(d,out);val=np.where(d['split']==1)[0];test=np.where(d['split']==2)[0]
 groups=sorted(set(v[1] for v in FEATURES.values()));sets={'full':active}
 for g in groups:sets['without_group_'+g]=[i for i in active if FEATURES[NAMES[i]][1]!=g]
 for i in active:sets['without_'+NAMES[i]]=[j for j in active if j!=i]
 results={};cache={}
 for name,cols in sets.items():
  hh=[];runs=[]
  for seed in (41,42,43):
   h,run=fit(d,cols,seed,args);hh.append(h);runs.append(run)
  h=np.mean(hh,axis=0);met,con=evaluation(h,d,val);results[name]={'features':[NAMES[i] for i in cols],'validation':met,'runs':runs};cache[name]=(h,con)
  print(name,met['ibs_0_8_relative'],flush=True);(out/'screening.json').write_text(json.dumps(results,indent=2))
 # Predeclared reduction: remove features whose single omission changes val IBS by <=1%.
 base=results['full']['validation']['ibs_0_8_relative'];selected=[i for i in active if results['without_'+NAMES[i]]['validation']['ibs_0_8_relative']>base*1.01]
 if not selected:selected=active
 selected_sets={'full':active,'selected':selected}
 for g in groups:selected_sets['only_group_'+g]=[i for i in active if FEATURES[NAMES[i]][1]==g]
 final={}
 for name,cols in selected_sets.items():
  hs=[];runs=[]
  for seed in (41,42,43):
   h,run=fit(d,cols,seed,args,out/f'{name}_{seed}.pt');hs.append(h);runs.append(run)
  h=np.mean(hs,axis=0);vm,vc=evaluation(h,d,val);tm,tc=evaluation(h,d,test)
  np.savez_compressed(out/f'{name}_predictions.npz',val_h=h[val],test_h=h[test],val_ibs=vc,test_ibs=tc)
  final[name]={'features':[NAMES[i] for i in cols],'validation':vm,'test':tm,'runs':runs};print('FINAL',name,vm['ibs_0_8_relative'],tm['ibs_0_8_relative'],flush=True)
 # Choice is frozen using validation only; test is descriptive.
 chosen=min(('full','selected'),key=lambda n:final[n]['validation']['ibs_0_8_relative'])
 (out/'results.json').write_text(json.dumps({'selected_by_validation':chosen,'models':final,'selection_rule':'single-drop val IBS degradation >1%; joint set must beat full on validation','edges_relative':EDGES.tolist()},indent=2))
 print('DONE selected_by_validation',chosen,flush=True)

if __name__=='__main__':main()
