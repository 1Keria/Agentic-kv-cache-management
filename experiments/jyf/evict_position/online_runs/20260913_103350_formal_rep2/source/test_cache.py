"""Real installed cache: >16 candidates, forced non-LRU, split and parents."""
from concurrent.futures import Future
import threading
from types import SimpleNamespace
import numpy as np
import torch
from sglang.srt.mem_cache import swa_radix_cache as s
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.base_prefix_cache import InsertParams, MatchPrefixParams, EvictParams, DecLockRefParams
import serving_patch as p

class Allocator(s.SWATokenToKVPoolAllocator):
    def __init__(self):
        self.device=torch.device('cpu')
        self.freed=[]
    def free(self,x): self.freed.extend(x.tolist())
    def free_swa(self,x): pass

def main():
    c=s.SWARadixCache(CacheInitParams(False,None,Allocator(),1,sliding_window_size=4))
    c.update_eviction_metrics=lambda *a:None
    def add(tokens): c.insert(InsertParams(key=s.RadixKey(tokens),value=torch.tensor(tokens)))
    add([1,2,3,4,5,6])
    add([1,2,3,4,7,8])
    for i in range(25): add([100+i*4+j for j in range(4)])
    c.sanity_check()
    r=c.match_prefix(MatchPrefixParams(key=s.RadixKey([1,2,3,4,5,6]),req=SimpleNamespace()))
    lock=c.inc_lock_ref(r.last_device_node)
    c.dec_lock_ref(r.last_device_node,DecLockRefParams(swa_uuid_for_lock=lock.swa_uuid_for_lock))
    ns=p.frontier(c,'full')
    assert len(ns)>16
    if p.MODE=='precompute':
        for n in ns:
            f,i,t=n._ep_tickets['full']
            f.result()
            forced=Future()
            forced.set_result((np.full((1,9),.001 if n is ns[-1] else .8),0))
            n._ep_tickets['full']=(forced,0,t)
        target=ns[-1]
        # Pending work must be awaited; eviction cannot call the model itself.
        f,i,t=target._ep_tickets['full']
        pending=Future()
        target._ep_tickets['full']=(pending,0,t)
        threading.Timer(.05,lambda:pending.set_result(f.result())).start()
    elif p.MODE=='on_demand':
        predict=c._ep_model.predict
        def forced(rows):
            h=np.full((len(rows),9),.8)
            h[-1]=.001
            return h
        c._ep_model.predict=forced
        target=ns[-1]
    c.evict(EvictParams(num_tokens=1,swa_num_tokens=0))
    if p.MODE!='lru':
        assert not c.full_lru_list.in_list(target),'failed to select outside oldest 16'
    if p.MODE=='precompute':
        assert c._ep_fresh==0
        assert c._ep_waited>0
    elif p.MODE=='on_demand': c._ep_model.predict=predict
    c.sanity_check()
    c.evict(EvictParams(num_tokens=0,swa_num_tokens=2))
    c.sanity_check()
    c.evict(EvictParams(num_tokens=10000,swa_num_tokens=10000))
    c.sanity_check()
    assert c.full_evictable_size()==0
    if c._ep_worker:c._ep_worker.close()
    print('PASS',p.MODE,'full frontier >16, split, locks, new parents, native freeing')

if __name__=='__main__':main()
