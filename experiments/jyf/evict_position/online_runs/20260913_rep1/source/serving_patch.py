"""Full legal-frontier eviction: fresh on-demand vs precompute-and-wait.

Only rank zero reads wall clock or runs the model. Native allocation and forced
tombstone cleanup are preserved. Missing precomputed tickets are fatal, never LRU.
"""
import bisect
import hashlib
import inspect
import json
import os
from pathlib import Path
import textwrap
import time
import numpy as np
import torch
from sglang.srt.mem_cache import swa_radix_cache as swa
from training_base import make_features
from predictor import Model, Worker, values

MODE = os.environ['EP_MODE']
assert MODE in ('lru','on_demand','precompute')
OUT = Path(os.environ['EP_OUT'])
CHECKPOINT = os.environ['EP_CHECKPOINT']

def emit(c, row):
    row['wall_s'] = time.time()
    c._ep_log.write(json.dumps(row,separators=(',',':'))+'\n')

def path_nodes(c,n):
    out=[]
    while n is not None and n is not c.root_node:
        out.append(n)
        n=n.parent
    return out

def frontier(c,k):
    ls=c.full_lru_list if k=='full' else c.swa_lru_list
    get=ls.get_leaf_lru_no_lock if k=='full' else ls.get_lru_no_lock
    prev=ls.get_prev_leaf_no_lock if k=='full' else ls.get_prev_no_lock
    out=[]
    n=get()
    while ls.in_list(n):
        out.append(n)
        n=prev(n)
    return out

def touch(c,n):
    if not getattr(c,'_ep_leader',False) or MODE=='lru' or c._ep_in_evict:
        return
    for x in path_nodes(c,n):
        c._ep_dirty[x.id]=x

def raw(c,n,k,frac,now):
    chain=path_nodes(c,n)
    created=getattr(n,'_ep_created',(c._ep_seq,now))
    points=getattr(n,'_ep_points',[])
    gap=points[-1][0]-points[-2][0] if len(points)>1 else -1
    r=dict(node_tokens=len(n.key),path_tokens=sum(len(x.key) for x in chain),
           age_requests=max(0,c._ep_seq-created[0]),age_s=max(0,now-created[1]),
           hits=getattr(n,'_ep_hits',0),cold=int(not getattr(n,'_ep_hits',0)),
           recent_gap_req=gap,lru_frac=frac,owner_traffic=getattr(n,'_ep_traffic',''),
           frontier=k)
    f,known=make_features(r,c._ep_seq,now,points)
    assert known, 'warm node without demand history'
    return f

def snapshots(c,nodes,k,now):
    ns=frontier(c,k)
    ranks={n.id:i/max(1,len(ns)-1) for i,n in enumerate(ns)}
    # Internal Full nodes cannot have a frontier rank yet. Use their virtual
    # insertion rank among the current frontier, without truncating candidates.
    times=sorted(float(n.last_access_time) for n in ns)
    return [raw(c,n,k,ranks.get(n.id,min(1.,bisect.bisect_left(times,float(n.last_access_time))/max(1,len(ns)))),now) for n in nodes]

def flush(c,source='manual'):
    if MODE!='precompute' or not c._ep_leader or c._ep_in_evict:
        return
    start=time.perf_counter()
    dirty,c._ep_dirty=c._ep_dirty,{}
    nodes=[n for n in dirty.values() if c.full_lru_list.in_list(n)]
    if not nodes: return
    now=time.monotonic()
    rows=[]
    slots=[]
    for k in ('full','swa'):
        rows.extend(snapshots(c,nodes,k,now))
        slots.extend((n,k) for n in nodes)
    # Tickets contain immutable input snapshots and one shared future. New
    # tickets replace references, so old completions cannot overwrite state.
    for start_i in range(0,len(rows),256):
        f=c._ep_worker.submit(rows[start_i:start_i+256])
        for i,(n,k) in enumerate(slots[start_i:start_i+256]):
            if not hasattr(n,'_ep_tickets'): n._ep_tickets={}
            n._ep_tickets[k]=(f,i,now)
    emit(c,dict(kind='submit',source=source,nodes=len(nodes),predictions=len(rows),
                snapshot_submit_us=(time.perf_counter()-start)*1e6))

old_init=swa.SWARadixCache.__init__
def init(c,*a,**kw):
    old_init(c,*a,**kw)
    if os.environ.get('EP_TEST'):
        c._ep_group=None
        c._ep_rank=0
    else:
        from sglang.srt.distributed.parallel_state import get_tp_group
        c._ep_group=get_tp_group()
        c._ep_rank=c._ep_group.rank_in_group
    c._ep_leader=c._ep_rank==0
    c._ep_seq=0
    c._ep_depth=0
    c._ep_dirty={}
    c._ep_in_evict=False
    c._ep_meta={}
    c._ep_evict=0
    c._ep_model=None
    c._ep_worker=None
    OUT.mkdir(parents=True,exist_ok=True)
    c._ep_log=(OUT/f'rank{c._ep_rank}_pid{os.getpid()}.jsonl').open('a',buffering=1)
    if c._ep_leader and MODE!='lru':
        c._ep_model=Model(CHECKPOINT)
        c._ep_model.predict([[0.]*24])
        if MODE=='precompute': c._ep_worker=Worker(c._ep_model)
    emit(c,dict(kind='init',mode=MODE,rank=c._ep_rank,checkpoint=CHECKPOINT,
                candidate_limit=None))
swa.SWARadixCache.__init__=init

old_add=swa.SWARadixCache._add_new_node
def add(c,*a,**kw):
    n=old_add(c,*a,**kw)
    n._ep_created=(c._ep_seq,time.monotonic())
    n._ep_traffic=str(c._ep_meta.get('traffic_class',''))
    n._ep_hits=0
    n._ep_points=[]
    touch(c,n)
    return n
swa.SWARadixCache._add_new_node=add

old_split=swa.SWARadixCache._split_node
def split(c,key,child,split_len):
    n=old_split(c,key,child,split_len)
    for name in ('_ep_created','_ep_traffic','_ep_hits'):
        if hasattr(child,name): setattr(n,name,getattr(child,name))
    n._ep_points=list(getattr(child,'_ep_points',[]))
    touch(c,child)
    touch(c,n)
    return n
swa.SWARadixCache._split_node=split

old_match=swa.SWARadixCache.match_prefix
def match(c,params):
    req=getattr(params,'req',None)
    if req is not None: c._ep_seq+=1
    r=old_match(c,params)
    if req is not None and c._ep_leader and MODE!='lru':
        now=time.monotonic()
        for n in path_nodes(c,r.last_device_node):
            n._ep_hits=getattr(n,'_ep_hits',0)+1
            points=list(getattr(n,'_ep_points',[]))
            points.append((c._ep_seq,now))
            n._ep_points=points[-9:]
            touch(c,n)
    return r
swa.SWARadixCache.match_prefix=match

def wrap_boundary(name):
    original=getattr(swa.SWARadixCache,name)
    def method(c,*a,**kw):
        start=time.perf_counter()
        c._ep_depth+=1
        previous=c._ep_meta
        if name in ('cache_finished_req','cache_unfinished_req'):
            custom=getattr(getattr(a[0],'sampling_params',None),'custom_params',None)
            c._ep_meta=custom if isinstance(custom,dict) else {}
        try:
            r=original(c,*a,**kw)
        finally:
            c._ep_depth-=1
            c._ep_meta=previous
        original_end=time.perf_counter()
        if c._ep_depth==0:
            flush(c,name)
        if name=='cache_finished_req' and c._ep_leader:
            emit(c,dict(kind='finish',original_us=(original_end-start)*1e6,
                        total_us=(time.perf_counter()-start)*1e6))
        return r
    setattr(swa.SWARadixCache,name,method)
# Standalone matching/splitting and early SWA release can precede request-end.
# Submit at mutation boundaries, never at eviction. Request-end remains the
# normal insertion/unlock batching boundary; extra boundary counts are reported.
for name in ('cache_finished_req','cache_unfinished_req','match_prefix','insert',
             'inc_lock_ref','dec_lock_ref','dec_swa_lock_only'):
    wrap_boundary(name)

def choose(c,k,original):
    nodes=frontier(c,k)
    assert nodes
    signature=[(n.id,len(n.key)) for n in nodes]
    payload=None
    if c._ep_leader:
        start=time.perf_counter()
        fresh=waited=0
        wait_s=infer_s=0.
        if MODE=='on_demand':
            missing=[n for n in nodes if (n.id,k) not in c._ep_current]
            if missing:
                now=time.monotonic()
                rows=snapshots(c,missing,k,now)
                t=time.perf_counter()
                h=c._ep_model.predict(rows)
                infer_s=time.perf_counter()-t
                for n,hh in zip(missing,h): c._ep_current[n.id,k]=(hh,now)
                fresh=len(missing)
            hs,origins=zip(*(c._ep_current[n.id,k] for n in nodes))
        else:
            hs=[]
            origins=[]
            for n in nodes:
                ticket=getattr(n,'_ep_tickets',{}).get(k)
                assert ticket is not None, f'precompute coverage violation node={n.id} kind={k}'
                f,i,origin=ticket
                pending=not f.done()
                t=time.perf_counter()
                result,_=f.result(timeout=120)
                wait_s+=time.perf_counter()-t
                waited+=int(pending)
                hs.append(result[i])
                origins.append(origin)
        now=time.monotonic()
        age=now-np.asarray(origins)
        scores=values(np.asarray(hs),age,
                      [sum(len(x.key) for x in path_nodes(c,n)) for n in nodes],
                      [len(n.value) for n in nodes])
        assert len(scores)==len(nodes) and np.isfinite(scores).all()
        selected=int(np.argmin(scores))
        payload=(signature,selected,fresh,waited,wait_s,infer_s,float(age.max()))
        c._ep_selection_s+=time.perf_counter()-start
    if c._ep_group is not None and c._ep_group.world_size>1:
        box=[payload]
        torch.distributed.broadcast_object_list(box,src=c._ep_group.ranks[0],group=c._ep_group.cpu_group)
        payload=box[0]
    sig,selected,fresh,waited,wait_s,infer_s,max_age=payload
    assert sig==signature,'TP frontier mismatch'
    n=nodes[selected]
    c._ep_decisions.append((k,n.id,len(n.key),len(nodes),selected))
    c._ep_fresh+=fresh
    c._ep_waited+=waited
    c._ep_wait_s+=wait_s
    c._ep_infer_s+=infer_s
    c._ep_max_age=max(c._ep_max_age,max_age)
    return n

original_evict=swa.SWARadixCache.evict
source=textwrap.dedent(inspect.getsource(original_evict))
source=source.replace('def evict(', 'def predicted_evict(',1)
for k,loop in [('full','while full_num_evicted < full_num_tokens and self.full_lru_list.in_list(x):'),
               ('swa','while swa_num_evicted < swa_num_tokens and (self.swa_lru_list.in_list(x)):')]:
    assert source.count(loop)==1
    source=source.replace(loop,loop+f'\n            x = _ep_choose(self, "{k}", x)')
assert source.count('            x = x_next')==2
source=source.replace('            x = x_next','            x = self.full_lru_list.get_leaf_lru_no_lock()',1)
source=source.replace('            x = x_next','            x = self.swa_lru_list.get_lru_no_lock()',1)
namespace=dict(vars(swa),_ep_choose=choose)
exec(compile(source,'<evict-position-native-free>','exec'),namespace)
predicted_evict=namespace['predicted_evict']

def evict(c,params):
    start=time.perf_counter()
    c._ep_evict+=1
    c._ep_current={}
    c._ep_decisions=[]
    c._ep_fresh=c._ep_waited=0
    c._ep_wait_s=c._ep_infer_s=c._ep_selection_s=c._ep_max_age=0.
    c._ep_in_evict=True
    try:
        r=original_evict(c,params) if MODE=='lru' else predicted_evict(c,params)
    finally:
        c._ep_in_evict=False
    ds=c._ep_decisions
    emit(c,dict(kind='evict',index=c._ep_evict,seq=c._ep_seq,
                freed_full=r.num_tokens_evicted,freed_swa=r.swa_num_tokens_evicted,
                digest=hashlib.sha256(repr(ds).encode()).hexdigest(),
                choices=len(ds),changed_choices=sum(d[4]!=0 for d in ds),
                candidate_exposures=sum(d[3] for d in ds),max_frontier=max([d[3] for d in ds],default=0),
                fresh_predictions=c._ep_fresh,pending_waits=c._ep_waited,
                wait_us=c._ep_wait_s*1e6,inference_us=c._ep_infer_s*1e6,
                selection_us=c._ep_selection_s*1e6,max_prediction_age_s=c._ep_max_age,
                total_us=(time.perf_counter()-start)*1e6))
    c._ep_current={}
    return r
swa.SWARadixCache.evict=evict
