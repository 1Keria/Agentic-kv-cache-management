"""Exercise the patched, installed SWARadixCache with CPU index tensors."""
import os
from pathlib import Path
from types import SimpleNamespace

import torch
from sglang.srt.mem_cache import swa_radix_cache as s
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.base_prefix_cache import InsertParams, MatchPrefixParams, EvictParams, DecLockRefParams
from predictor import Result
import serving_patch as patch


class Allocator(s.SWATokenToKVPoolAllocator):
    def __init__(self):
        self.device = torch.device("cpu")
        self.freed = []

    def free(self, x):
        self.freed.extend(x.tolist())

    def free_swa(self, x):
        pass


def main():
    cache = s.SWARadixCache(CacheInitParams(False, None, Allocator(), 1, sliding_window_size=4))
    cache.update_eviction_metrics = lambda *args: None
    def insert(tokens):
        return cache.insert(InsertParams(key=s.RadixKey(tokens), value=torch.tensor(tokens)))
    insert([1, 2, 3, 4, 5, 6])
    insert([1, 2, 3, 4, 7, 8])  # split common prefix
    insert([10, 11, 12, 13])
    cache.sanity_check()
    hit = cache.match_prefix(MatchPrefixParams(key=s.RadixKey([1, 2, 3, 4, 5, 6]), req=SimpleNamespace()))
    lock = cache.inc_lock_ref(hit.last_device_node)
    assert hit.last_device_node.full_lock_ref > 0
    cache.dec_lock_ref(hit.last_device_node, DecLockRefParams(swa_uuid_for_lock=lock.swa_uuid_for_lock))
    patch.flush(cache)
    cache.sanity_check()
    ns = patch.frontier(cache, "full")
    if patch.MODE != "lru":
        if cache._ap_worker:
            cache._ap_worker.close()
        # Known scores force an actual out-of-LRU victim, testing allocator logic.
        for i, node in enumerate(ns):
            st = node._ap_states["full"]
            t = st.prediction_state
            assert t is not None
            t.result = Result(0, (), tuple([.8 if i == 0 else .01] * 9))
    target = ns[1] if patch.MODE != "lru" else ns[0]
    cache.evict(EvictParams(num_tokens=1, swa_num_tokens=0))
    assert not cache.full_lru_list.in_list(target), "policy failed to change actual victim"
    cache.sanity_check()
    cache.evict(EvictParams(num_tokens=0, swa_num_tokens=1))
    cache.sanity_check()
    cache.evict(EvictParams(num_tokens=1000, swa_num_tokens=1000))
    cache.sanity_check()
    assert cache.full_evictable_size() == 0
    print("PASS", patch.MODE, "split, match, locks, forced victim, full+swa free, sanity")


if __name__ == "__main__":
    main()
