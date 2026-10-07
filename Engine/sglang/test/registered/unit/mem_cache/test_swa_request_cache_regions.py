from array import array
from types import SimpleNamespace

import torch
import pytest

from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import (
    DecLockRefParams,
    EvictResult,
    EvictParams,
    InsertParams,
    MatchPrefixParams,
)
from sglang.srt.mem_cache import common as mem_cache_common
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.common import region_allocation_token_counts
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.request_region_ghost import RequestRegionGhostIndex
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


def make_cache(
    full_size: int = 10,
    swa_size: int = 6,
    *,
    region_policy: str = "fixed",
    request_agent_cache_ratio: float = 0.5,
    window_requests: int = 64,
    alpha: float = 0.2,
    feedback_mode: str = "eviction_share",
    max_ratio_step: float = 0.05,
    pressure_hysteresis: float = 0.0,
    cooldown_evicted_tokens: int = 0,
    lazy_reclassify: bool = False,
    elastic_reclaim_order: str = "request_first",
    elastic_activity_window: int = 0,
    borrowed_segment_tokens: int = 0,
) -> SWARadixCache:
    return SWARadixCache(
        CacheInitParams(
            disable=False,
            req_to_token_pool=None,
            token_to_kv_pool_allocator=FakeSWAAllocator(full_size, swa_size),
            page_size=1,
            sliding_window_size=4,
            eviction_policy="lru",
            enable_request_cache_regions=True,
            request_agent_cache_ratio=request_agent_cache_ratio,
            request_cache_region_policy=region_policy,
            request_cache_ratio_window_requests=window_requests,
            request_cache_ratio_alpha=alpha,
            request_cache_ratio_feedback_mode=feedback_mode,
            request_cache_ratio_max_step=max_ratio_step,
            request_cache_ratio_pressure_hysteresis=pressure_hysteresis,
            request_cache_ratio_cooldown_evicted_tokens=cooldown_evicted_tokens,
            request_cache_borrow_lazy_reclassify=lazy_reclassify,
            request_cache_elastic_reclaim_order=elastic_reclaim_order,
            request_cache_elastic_activity_window=elastic_activity_window,
            request_cache_borrowed_segment_tokens=borrowed_segment_tokens,
            request_cache_agent_min_ratio=0.2,
            request_cache_agent_max_ratio=0.8,
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


def test_swa_elastic_hit_only_activity_ignores_cold_request_and_refreshes_on_hit():
    cache = make_cache(
        full_size=32,
        swa_size=16,
        region_policy="elastic",
        elastic_activity_window=4,
    )
    cache.request_cache_elastic_activity_requires_hit = True
    req = SimpleNamespace(cache_region="request")

    cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [21, 22]), ("region", "request")),
            req=req,
        )
    )
    assert cache.region_quota_stats()["elastic_region_last_access"]["request"] == -1

    insert(cache, [21, 22], "request")
    cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [21, 22]), ("region", "request")),
            req=req,
        )
    )
    assert cache.region_quota_stats()["elastic_region_last_access"]["request"] >= 0


def test_swa_elastic_ghost_uses_same_region_feedback_as_full():
    cache = make_cache(
        full_size=4,
        swa_size=4,
        region_policy="elastic",
    )
    cache.request_cache_elastic_ghost_capacity_tokens = 16
    cache.request_region_ghost = __import__(
        "sglang.srt.mem_cache.request_region_ghost",
        fromlist=["RequestRegionGhostIndex"],
    ).RequestRegionGhostIndex(page_size=1, capacity_tokens=16, pressure_decay=1.0)
    insert(cache, [1, 2, 3, 4], "agent")
    cache.ensure_region_capacity("request", 4)
    req = SimpleNamespace(cache_region="agent")
    result = cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")),
            req=req,
        )
    )
    assert len(result.device_indices) == 0
    ghost = cache.region_quota_stats()["elastic_ghost"]
    assert ghost["revisit_tokens"]["agent"] == 4


def test_swa_elastic_ghost_protects_revisited_borrowed_prefix():
    cache = make_cache(
        full_size=8,
        swa_size=8,
        region_policy="elastic",
        borrowed_segment_tokens=1,
    )
    cache.request_cache_elastic_ghost_capacity_tokens = 32
    cache.request_cache_elastic_ghost_pressure_decay = 1.0
    cache.request_cache_elastic_ghost_bias = 0.0
    cache.request_cache_elastic_ghost_reclaim = False
    cache.request_cache_elastic_ghost_protect = True
    cache.request_region_ghost = RequestRegionGhostIndex(
        page_size=1, capacity_tokens=32, pressure_decay=1.0
    )
    insert(cache, [1, 2, 3, 4], "agent")

    evicted = cache.evict(
        EvictParams(
            num_tokens=4,
            swa_num_tokens=4,
            region="agent",
            borrowed_only=True,
        )
    )
    assert evicted.num_tokens_evicted > 0
    req = SimpleNamespace(cache_region="agent")
    result = cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")),
            req=req,
        )
    )
    assert len(result.device_indices) < 4
    assert cache.region_quota_stats()["elastic_ghost"]["revisit_tokens"]["agent"] > 0

    insert(cache, [1, 2, 3, 4], "agent")
    insert(cache, [10, 11, 12, 13], "agent")
    victim = cache._select_full_leaf_victim("agent", borrowed_only=True)
    assert victim is not None
    assert cache._elastic_ghost_revisit_score(victim) == 0.0


def test_borrowed_suffix_granularity_limits_swa_reclaim_overshoot():
    cache = make_cache(
        full_size=32,
        swa_size=32,
        region_policy="elastic",
        borrowed_segment_tokens=1,
    )
    insert(cache, list(range(20)), "agent")
    result = cache.evict(
        EvictParams(
            num_tokens=4,
            swa_num_tokens=4,
            region="agent",
            borrowed_only=True,
        )
    )
    assert result.num_tokens_evicted == 4
    assert result.swa_num_tokens_evicted == 4


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


def test_paged_allocator_eviction_uses_actual_new_pages(monkeypatch):
    class FakeAllocator:
        page_size = 8

        def alloc_extend(self, *args, **kwargs):
            return torch.empty(3, dtype=torch.int64)

        def alloc_decode(self, seq_lens, *args, **kwargs):
            return torch.empty(len(seq_lens), dtype=torch.int64)

    allocator = FakeAllocator()
    tree_cache = type("TreeCache", (), {"token_to_kv_pool_allocator": allocator})()
    evictions = []
    monkeypatch.setattr(
        mem_cache_common,
        "evict_from_tree_cache",
        lambda _tree_cache, num_tokens: evictions.append(num_tokens),
    )

    prefix_lens_cpu = torch.tensor([5, 7, 8], dtype=torch.int64)
    seq_lens_cpu = torch.tensor([6, 10, 9], dtype=torch.int64)
    mem_cache_common.alloc_paged_token_slots_extend(
        tree_cache,
        prefix_lens_cpu,
        prefix_lens_cpu,
        seq_lens_cpu,
        seq_lens_cpu,
        torch.empty(3, dtype=torch.int64),
        extend_num_tokens=3,
    )

    decode_seq_lens_cpu = torch.tensor([6, 9, 16, 17], dtype=torch.int64)
    mem_cache_common.alloc_paged_token_slots_decode(
        tree_cache,
        decode_seq_lens_cpu,
        decode_seq_lens_cpu,
        torch.empty(4, dtype=torch.int64),
    )

    assert evictions == [16, 16]


def test_borrow_policy_uses_borrowed_pages_before_global_fallback():
    class FallbackAllocator(SWATokenToKVPoolAllocator):
        def __init__(self):
            self.full_available = 0
            self.swa_available = 0

        def full_available_size(self):
            return self.full_available

        def swa_available_size(self):
            return self.swa_available

    allocator = FallbackAllocator()
    calls = []

    def evict(params):
        calls.append(params)
        if params.borrowed_only:
            allocator.full_available = 8
            allocator.swa_available = 8
            return EvictResult(
                num_tokens_evicted=8,
                swa_num_tokens_evicted=8,
            )
        return EvictResult()

    tree_cache = SimpleNamespace(
        token_to_kv_pool_allocator=allocator,
        request_cache_region_policy="borrow",
        is_chunk_cache=lambda: False,
        evict=evict,
    )

    mem_cache_common.evict_from_tree_cache(tree_cache, 8, region="request")

    assert len(calls) == 2
    assert calls[0].region == "request"
    assert not calls[0].borrowed_only
    assert calls[1].borrowed_only
    assert calls[1].region is None
    assert calls[1].borrow_reclaim_reason == "allocator_fallback"



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


def test_swa_cache_uses_one_dynamic_ratio_for_full_and_swa():
    cache = make_cache(region_policy="dynamic", alpha=1.0)
    insert(cache, [1, 2, 3, 4], "agent")

    cache.ensure_region_capacity("agent", 0)
    cache._on_request_region_finished("agent")

    stats = cache.region_stats()
    assert cache.request_agent_cache_ratio == 0.8
    assert stats["agent"]["full_capacity_tokens"] == 8
    assert stats["agent"]["swa_capacity_tokens"] == 4
    assert stats["request"]["full_capacity_tokens"] == 2
    assert stats["request"]["swa_capacity_tokens"] == 2
    assert cache.region_quota_stats()["request_min_ratio"] == pytest.approx(0.2)
    assert cache.region_quota_stats()["last_feedback_agent_evicted_tokens"] == 4

    insert(cache, [11, 12, 13, 14], "request")
    cache.ensure_region_capacity("request", 0)
    cache._on_request_region_finished("request")

    stats = cache.region_stats()
    assert cache.request_agent_cache_ratio == 0.2
    assert stats["agent"]["full_used_tokens"] == 0
    assert stats["agent"]["swa_used_tokens"] == 0
    assert stats["request"]["full_capacity_tokens"] == 8
    assert stats["request"]["swa_capacity_tokens"] == 5


def test_swa_borrow_dynamic_combines_feedback_with_idle_capacity_borrowing():
    cache = make_cache(
        full_size=10,
        swa_size=6,
        region_policy="borrow_dynamic",
        alpha=1.0,
        feedback_mode="eviction_share",
        cooldown_evicted_tokens=0,
    )
    insert(cache, [1, 2, 3, 4, 5, 6], "agent")
    stats = cache.region_stats()
    assert stats["agent"]["full_capacity_tokens"] == 10
    assert stats["agent"]["swa_capacity_tokens"] == 6
    assert cache.region_quota_stats()["policy"] == "borrow_dynamic"

    cache.evict(
        EvictParams(
            num_tokens=6,
            swa_num_tokens=6,
            borrowed_only=True,
            borrow_reclaim_reason="global_overage",
        )
    )
    cache._on_request_region_finished("agent")

    assert cache.request_agent_cache_ratio == pytest.approx(0.8)
    assert cache.region_quota_stats()["policy"] == "borrow_dynamic"


def test_swa_normalized_pressure_uses_shared_bounded_ratio():
    cache = make_cache(
        region_policy="dynamic",
        alpha=1.0,
        feedback_mode="normalized_pressure",
        max_ratio_step=0.03,
    )
    insert(cache, list(range(1, 9)), "agent")

    cache.ensure_region_capacity("agent", 0)
    cache._on_request_region_finished("agent")

    assert cache.request_agent_cache_ratio == pytest.approx(0.53)
    stats = cache.region_quota_stats()
    assert stats["feedback_mode"] == "normalized_pressure"
    assert stats["last_feedback_applied_step"] == pytest.approx(0.03)
    assert cache.region_stats()["agent"]["full_capacity_tokens"] == 5
    assert cache.region_stats()["agent"]["swa_capacity_tokens"] == 3


def test_swa_borrow_policy_reports_idle_capacity():
    cache = make_cache(region_policy="borrow")
    insert(cache, [1, 2, 3, 4, 5, 6], "agent")
    stats = cache.region_stats()
    assert stats["agent"]["base_full_capacity_tokens"] == 5
    assert stats["agent"]["full_borrowed_tokens"] == 5
    assert stats["agent"]["full_capacity_tokens"] == 10
    assert stats["agent"]["swa_borrowed_tokens"] == 3
    assert stats["agent"]["swa_capacity_tokens"] == 6
    assert cache.request_agent_cache_ratio == 0.5


def test_swa_borrow_reclaims_borrowed_node_without_touching_protected_node():
    cache = make_cache(full_size=10, swa_size=6, region_policy="borrow")
    insert(cache, [1, 2, 3], "agent")
    insert(cache, [11, 12], "agent")

    nodes = [node for node in cache._collect_all_nodes() if node.cache_region == "agent"]
    assert sorted(
        (len(node.key), node.full_borrowed, node.swa_borrowed) for node in nodes
    ) == [(2, False, True), (3, False, False)]

    cache.ensure_region_capacity("request", 2)
    stats = cache.region_stats()
    assert stats["agent"]["full_used_tokens"] == 3
    assert stats["agent"]["swa_used_tokens"] == 3
    assert stats["agent"]["full_cached_borrowed_tokens"] == 0
    assert stats["agent"]["swa_cached_borrowed_tokens"] == 0
    assert stats["agent"]["full_evicted_tokens"] == 2
    assert stats["agent"]["swa_evicted_tokens"] == 2
    assert stats["agent"]["borrowed_eviction_count"] == 1
    assert stats["agent"]["borrowed_full_evicted_tokens"] == 2
    assert stats["agent"]["borrowed_swa_evicted_tokens"] == 2
    assert stats["agent"]["borrow_reclaim_reasons"] == {"global_overage": 1}
    match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2, 3]), ("region", "agent")))
    )
    assert len(match.device_indices) == 3


def test_swa_borrow_marks_only_actual_idle_capacity_as_borrowed():
    cache = make_cache(full_size=10, swa_size=6, region_policy="borrow")
    insert(cache, list(range(1, 9)), "agent")
    insert(cache, list(range(11, 16)), "request")
    insert(cache, list(range(11, 19)), "request")

    request_nodes = [
        node
        for node in cache._collect_all_nodes()
        if node.cache_region == "request"
    ]
    assert request_nodes
    assert all(not node.full_borrowed for node in request_nodes)
    assert all(not node.swa_borrowed for node in request_nodes)
    stats = cache.region_stats()["request"]
    assert stats["full_cached_borrowed_tokens"] == 0
    assert stats["swa_cached_borrowed_tokens"] == 0


def test_swa_borrow_marks_page_that_crosses_guarantee_boundary():
    cache = make_cache(full_size=10, swa_size=6, region_policy="borrow")
    insert(cache, [1, 2, 3, 4], "agent")
    insert(cache, [11, 12], "agent")

    nodes = [node for node in cache._collect_all_nodes() if node.cache_region == "agent"]
    assert sorted(
        (len(node.key), node.full_borrowed, node.swa_borrowed) for node in nodes
    ) == [(2, True, True), (4, False, True)]
    stats = cache.region_stats()["agent"]
    assert stats["full_cached_borrowed_tokens"] == 2
    assert stats["swa_cached_borrowed_tokens"] == 6


def test_swa_lazy_borrow_reclassifies_stale_surplus_at_fallback_boundary():
    cache = make_cache(region_policy="borrow", lazy_reclassify=True)
    for token in range(1, 6):
        insert(cache, [100 + token], "request")
    for token in range(1, 9):
        insert(cache, [token], "agent")

    assert cache.region_stats()["agent"]["full_cached_borrowed_tokens"] == 0
    cache.evict(EvictParams(num_tokens=5, swa_num_tokens=5, region="request"))
    cache.ensure_region_capacity("agent", 0)
    assert cache.region_stats()["agent"]["full_cached_borrowed_tokens"] == 0

    cache._reclassify_borrowed_for_fallback()
    stats = cache.region_stats()["agent"]
    # The smaller SWA pool first evicts two Agent leaves during the normal
    # quota check; the fallback promotion therefore sees one remaining Full
    # surplus token and three remaining SWA surplus tokens.
    assert stats["full_cached_borrowed_tokens"] == 1
    assert stats["swa_cached_borrowed_tokens"] == 3


def test_swa_borrow_batch_reservation_accounts_for_both_regions():
    cache = make_cache(full_size=10, swa_size=6, region_policy="borrow")
    insert(cache, list(range(1, 5)), "agent")
    insert(cache, [101], "request")

    # Each individual reservation fits the current SWA pool, but together they
    # cross it. The existing borrowed Agent SWA page is the legal victim.
    cache.ensure_region_capacities({"agent": 1, "request": 1})
    stats = cache.region_stats()
    # SWA eviction is node-granular, so the four-token leaf is removed.
    assert stats["agent"]["swa_evicted_tokens"] == 4
    assert stats["agent"]["borrowed_swa_evicted_tokens"] == 4
    assert stats["request"]["swa_evicted_tokens"] == 0


def test_swa_borrow_reclaims_current_region_before_other_region():
    cache = make_cache(full_size=10, swa_size=6, region_policy="borrow")
    insert(cache, [1, 2, 3, 4], "agent")
    insert(cache, [5, 6], "agent")
    cache.evict(EvictParams(num_tokens=4, swa_num_tokens=4, region="agent"))

    # Both regions now contain borrowed leaves. The request reservation must
    # reclaim its own borrowed leaf before touching the Agent history.
    insert(cache, [11, 12, 13, 14, 15, 16], "request")
    cache.ensure_region_capacity("request", 3)

    stats = cache.region_stats()
    assert stats["request"]["borrowed_full_evicted_tokens"] == 6
    assert stats["request"]["borrowed_swa_evicted_tokens"] == 6
    assert stats["agent"]["borrowed_full_evicted_tokens"] == 0
    assert stats["agent"]["borrowed_swa_evicted_tokens"] == 0
    assert stats["agent"]["full_cached_borrowed_tokens"] == 2


def test_swa_borrow_reclass_promotes_full_and_swa_tail_pages():
    cache = make_cache(full_size=20, swa_size=20, region_policy="borrow_reclass")
    insert(cache, list(range(1, 11)), "agent")
    insert(cache, list(range(11, 21)), "request")
    insert(cache, [21, 22, 23], "agent")

    # The Agent tail was inserted while the request side was full. After the
    # request page is released, both physical pools should expose that tail as
    # borrowed capacity under the reclassification variant.
    cache.evict(EvictParams(num_tokens=10, swa_num_tokens=10, region="request"))
    cache.ensure_region_capacity("agent", 0)
    stats = cache.region_stats()["agent"]
    assert stats["full_cached_borrowed_tokens"] >= 3
    assert stats["swa_cached_borrowed_tokens"] >= 3


def test_swa_elastic_uses_minimums_for_full_and_swa_pools():
    cache = make_cache(region_policy="elastic")
    insert(cache, [1], "agent")
    insert(cache, [2, 3, 4], "agent")

    stats = cache.region_stats()
    quota_stats = cache.region_quota_stats()
    assert quota_stats["agent_min_ratio"] == pytest.approx(0.2)
    assert quota_stats["request_min_ratio"] == pytest.approx(0.2)
    assert quota_stats["elastic_pool_ratio"] == pytest.approx(0.6)
    assert stats["agent"]["base_full_capacity_tokens"] == 2
    assert stats["agent"]["base_swa_capacity_tokens"] == 1
    assert stats["agent"]["full_cached_borrowed_tokens"] == 3
    assert stats["agent"]["swa_cached_borrowed_tokens"] == 3
    nodes = [node for node in cache._collect_all_nodes() if node.cache_region == "agent"]
    assert sorted((len(node.key), node.full_borrowed, node.swa_borrowed) for node in nodes) == [
        (1, False, False),
        (3, True, True),
    ]


def test_swa_elastic_empty_soft_split_uses_safety_band_midpoint():
    cache = make_cache(
        full_size=10,
        swa_size=6,
        region_policy="elastic",
        request_agent_cache_ratio=0.61,
    )

    assert cache._elastic_preferred_agent_ratio() == pytest.approx(0.5)
    assert cache.region_quota_stats()["elastic_observed_agent_ratio"] == pytest.approx(0.5)
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.5)


def test_swa_elastic_activity_window_keeps_stale_region_minimum_reserve():
    cache = make_cache(
        full_size=10,
        swa_size=6,
        region_policy="elastic",
        request_agent_cache_ratio=0.61,
        elastic_activity_window=2,
    )

    assert cache._elastic_activity_floor_ratio() == pytest.approx(0.61)
    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 0, "request": 9}
    full_quotas, swa_quotas = cache._region_base_quotas(10, 6)
    assert full_quotas == {"agent": 6, "request": 4}
    assert swa_quotas == {"agent": 3, "request": 3}

    cache._elastic_region_last_access = {"agent": 9, "request": 10}
    assert cache._elastic_activity_floor_ratio() is None
    full_quotas, swa_quotas = cache._region_base_quotas(10, 6)
    assert full_quotas == {"agent": 2, "request": 1}
    assert swa_quotas == {"agent": 1, "request": 1}

    cache._elastic_region_last_access = {"agent": 9, "request": 0}
    assert cache._elastic_activity_floor_ratio() == pytest.approx(0.61)
    full_quotas, swa_quotas = cache._region_base_quotas(10, 6)
    assert full_quotas == {"agent": 6, "request": 4}
    assert swa_quotas == {"agent": 3, "request": 3}


def test_swa_elastic_preferred_reclaim_requires_history_for_stale_region():
    cache = make_cache(
        full_size=10,
        swa_size=6,
        region_policy="elastic",
        request_agent_cache_ratio=0.61,
        elastic_activity_window=4,
    )
    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 10, "request": 1}
    cache._elastic_last_access_region = "agent"
    cache._elastic_region_run_length = {"agent": 5, "request": 1}
    cache._elastic_region_access_count = {"agent": 5, "request": 1}
    assert cache._elastic_preferred_reclaim_active() is False

    cache._elastic_region_access_count["request"] = 4
    assert cache._elastic_preferred_reclaim_active() is True


def test_swa_elastic_pressure_marks_active_region_tail_first_when_request_is_idle():
    cache = make_cache(full_size=10, swa_size=10, region_policy="elastic")
    insert(cache, list(range(1, 15)), "agent")
    insert(cache, [21], "request")

    # Full and SWA share one ratio.  With both pools under pressure, the
    # request side's unused minimum makes the Agent suffix the first victim.
    assert cache._elastic_target_agent_ratio() == pytest.approx(0.8)
    cache._refresh_elastic_preferred_borrowed(full_pending=1, swa_pending=1)
    assert cache._elastic_tail_first_regions == {"agent"}


def test_swa_elastic_activity_window_suppresses_stale_opposite_region_tail_first():
    cache = make_cache(full_size=10, swa_size=10, region_policy="elastic")
    cache.request_cache_elastic_activity_window = 2
    insert(cache, list(range(1, 10)), "agent")
    insert(cache, [21], "request")

    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 0, "request": 1}
    cache._refresh_elastic_preferred_borrowed(full_pending=1, swa_pending=1)
    assert cache._elastic_tail_first_regions == set()
    assert cache._elastic_tail_first_activity_suppressed == 1

    cache._elastic_region_last_access["request"] = 9
    cache._refresh_elastic_preferred_borrowed(full_pending=1, swa_pending=1)
    assert cache._elastic_tail_first_regions == {"agent"}


def test_swa_elastic_preferred_tier_uses_one_current_mix_for_both_pools():
    cache = make_cache(full_size=10, swa_size=6, region_policy="elastic")
    for key in ([1, 2, 3], [4, 5, 6], [7, 8, 9]):
        insert(cache, list(key), "request")
    insert(cache, [11, 12, 13], "agent")

    assert cache.region_full_preferred_borrowed_tokens["agent"] > 0
    assert cache.region_swa_preferred_borrowed_tokens["agent"] > 0
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.25)

    cache.evict(EvictParams(num_tokens=9, swa_num_tokens=9, region="request"))
    cache._refresh_elastic_preferred_borrowed()
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.8)
    assert cache.region_full_preferred_borrowed_tokens["agent"] == 0
    assert cache.region_swa_preferred_borrowed_tokens["agent"] == 0


def test_swa_elastic_reclaims_borrowed_pages_before_protected_pages():
    cache = make_cache(region_policy="elastic")
    insert(cache, [1], "agent")
    insert(cache, [2, 3, 4], "agent")

    # The reservation exceeds both physical pools. The three-token borrowed
    # Agent page is reclaimable, while the one-token minimum remains.
    cache.ensure_region_capacity("request", 7)
    stats = cache.region_stats()
    assert stats["agent"]["full_used_tokens"] == 1
    assert stats["agent"]["swa_used_tokens"] == 1
    assert stats["agent"]["full_cached_borrowed_tokens"] == 0
    assert stats["agent"]["swa_cached_borrowed_tokens"] == 0
    assert stats["agent"]["borrowed_full_evicted_tokens"] == 3
    assert stats["agent"]["borrowed_swa_evicted_tokens"] == 3


def test_swa_elastic_reclaims_the_larger_pool_surplus_first():
    cache = make_cache(full_size=20, swa_size=20, region_policy="elastic")
    insert(cache, [1, 2, 3, 4], "agent")
    insert(cache, [11, 12, 13, 14, 15, 16, 17, 18], "request")

    # Request owns the larger Full/SWA elastic surplus. Agent pressure should
    # release that request surplus before discarding Agent history.
    cache.ensure_region_capacity("agent", 9)
    stats = cache.region_stats()
    assert stats["request"]["borrowed_full_evicted_tokens"] > 0
    assert stats["request"]["borrowed_swa_evicted_tokens"] > 0
    assert stats["agent"]["full_used_tokens"] == 4
    assert stats["agent"]["swa_used_tokens"] == 4


def test_swa_elastic_pressure_first_reclaims_requesting_region_surplus():
    cache = make_cache(
        full_size=20,
        swa_size=20,
        region_policy="elastic",
        elastic_reclaim_order="pressure_first",
    )
    insert(cache, [1, 2, 3, 4, 5, 6, 7, 8], "agent")
    insert(cache, [11, 12, 13, 14, 15, 16, 17, 18], "request")

    cache.ensure_region_capacity("agent", 8)
    stats = cache.region_stats()
    assert stats["agent"]["borrowed_full_evicted_tokens"] > 0
    assert stats["agent"]["borrowed_swa_evicted_tokens"] > 0
    assert stats["request"]["borrowed_full_evicted_tokens"] == 0
    assert stats["request"]["borrowed_swa_evicted_tokens"] == 0
    assert stats["request"]["full_used_tokens"] == 8
    assert stats["request"]["swa_used_tokens"] == 8
