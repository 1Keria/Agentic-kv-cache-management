from array import array
from types import SimpleNamespace

import torch

from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import (
    DecLockRefParams,
    EvictParams,
    InsertParams,
    MatchPrefixParams,
)
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.common import region_allocation_token_counts
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.swa_radix_cache import SWARadixCache
from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=2, suite="base-a-test-cpu")


class FakeSWAAllocator(SWATokenToKVPoolAllocator):
    def __init__(self, full_size: int, swa_size: int):
        self._size_full = full_size
        self._size_swa = swa_size
        self.device = torch.device("cpu")
        self.page_size = 1
        self.dtype = torch.int64
        self.need_sort = False
        self.free_pages = None
        self.release_pages = None
        self.is_not_in_free_group = True
        self.free_group = []
        self._kvcache = None

    def free(self, indices):
        return None

    def free_swa(self, indices):
        return None


def make_cache(full_size: int = 10, swa_size: int = 6) -> SWARadixCache:
    return SWARadixCache(
        CacheInitParams(
            disable=False,
            req_to_token_pool=None,
            token_to_kv_pool_allocator=FakeSWAAllocator(full_size, swa_size),
            page_size=1,
            sliding_window_size=4,
            eviction_policy="lru",
            enable_request_cache_regions=True,
            request_agent_cache_ratio=0.5,
        )
    )


def insert(cache: SWARadixCache, token_ids: list[int], region: str) -> None:
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", token_ids), ("region", region)),
            value=torch.arange(len(token_ids)),
            req=SimpleNamespace(cache_region=region),
        )
    )


def test_swa_region_quota_evicts_only_over_capacity_region():
    cache = make_cache()
    insert(cache, [1, 2, 3, 4, 5, 6], "agent")
    insert(cache, [11, 12], "request")

    cache.ensure_region_capacity("agent", 0)
    stats = cache.region_stats()

    assert stats["agent"]["full_capacity_tokens"] == 5
    assert stats["agent"]["swa_capacity_tokens"] == 3
    assert stats["agent"]["full_used_tokens"] == 0
    assert stats["agent"]["swa_used_tokens"] == 0
    assert stats["agent"]["eviction_count"] == 1
    assert stats["agent"]["full_evicted_tokens"] == 6
    assert stats["agent"]["swa_evicted_tokens"] == 6
    assert stats["request"]["full_used_tokens"] == 2
    assert stats["request"]["swa_used_tokens"] == 2

    agent_match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2]), ("region", "agent")))
    )
    request_match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [11, 12]), ("region", "request")))
    )
    assert len(agent_match.device_indices) == 0
    assert len(request_match.device_indices) == 2


def test_swa_region_count_drops_when_locked_leaf_becomes_tombstone():
    cache = make_cache(full_size=16, swa_size=16)
    insert(cache, [1, 2, 3, 4], "agent")
    match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")))
    )
    leaf = match.last_device_node
    lock = cache.inc_lock_ref(leaf)

    cache.dec_swa_lock_only(leaf, lock.swa_uuid_for_lock)
    stats = cache.region_stats()["agent"]
    assert stats["full_used_tokens"] == 4
    assert stats["swa_used_tokens"] == 0
    assert leaf.swa_tombstone

    cache.dec_lock_ref(
        leaf,
        DecLockRefParams(swa_uuid_for_lock=lock.swa_uuid_for_lock),
        skip_swa=True,
    )
    cache.sanity_check()


def test_paged_region_capacity_counts_only_new_pages():
    prefix_lens = torch.tensor([5, 7, 8], dtype=torch.int64)
    seq_lens = torch.tensor([6, 10, 9], dtype=torch.int64)
    assert region_allocation_token_counts(prefix_lens, seq_lens, 8) == [0, 8, 8]

    decode_before = torch.tensor([5, 8, 15, 16], dtype=torch.int64)
    decode_after = decode_before + 1
    assert region_allocation_token_counts(
        decode_before,
        decode_after,
        8,
        decode=True,
    ) == [0, 8, 0, 8]


def test_swa_region_count_drops_when_full_locked_leaf_is_evicted_from_swa():
    cache = make_cache(full_size=16, swa_size=16)
    insert(cache, [1, 2, 3, 4], "agent")
    match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")))
    )
    leaf = match.last_device_node
    lock = cache.inc_lock_ref(leaf)

    cache.swa_protected_size_ -= len(leaf.value)
    cache.swa_evictable_size_ += len(leaf.value)
    leaf.swa_lock_ref -= 1
    result = cache.evict(EvictParams(swa_num_tokens=1, region="agent"))

    assert result.num_tokens_evicted == 0
    assert result.swa_num_tokens_evicted == 4
    assert cache.region_stats()["agent"]["swa_used_tokens"] == 0
    assert leaf.swa_tombstone

    cache.dec_lock_ref(
        leaf,
        DecLockRefParams(swa_uuid_for_lock=lock.swa_uuid_for_lock),
        skip_swa=True,
    )
    cache.sanity_check()
