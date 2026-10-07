from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import torch
import pytest

from sglang.srt.mem_cache.base_prefix_cache import (
    EvictParams,
    InsertParams,
    MatchPrefixParams,
)
from sglang.srt.managers.io_struct import GenerateReqInput
from sglang.srt.mem_cache.radix_cache import RadixCache, RadixKey
from sglang.srt.mem_cache.request_region import (
    RequestRegionClassifier,
    extract_features,
)
from sglang.srt.mem_cache.request_region_ghost import RequestRegionGhostIndex
from sglang.srt.mem_cache.request_region_quota import RequestRegionQuotaController


def test_request_region_features_are_structure_only():
    values = extract_features(
        {
            "messages": [
                {"role": "assistant", "content": "ignored vocabulary", "tool_calls": [{"id": "1"}]}
            ],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
        },
        128,
    )
    assert values["has_tools"] == 1.0
    assert values["has_tool_calls"] == 1.0
    assert values["log_tool_count"] > 0
    assert values["log_content_chars"] > 0


def test_batch_classifier_bodies_are_kept_per_request():
    request = GenerateReqInput(
        text=["ordinary", "agent"],
        sampling_params=[{}, {}],
        cache_classifier_body=[
            {"messages": [{"role": "user", "content": "ordinary"}]},
            {
                "messages": [{"role": "user", "content": "agent"}],
                "tools": [{"type": "function"}],
            },
        ],
    )
    request.normalize_batch_and_arguments()

    assert request[0].cache_classifier_body["messages"][0]["content"] == "ordinary"
    assert request[1].cache_classifier_body["tools"] == [{"type": "function"}]


def test_request_region_checkpoint_loads():
    checkpoint = (
        Path(__file__).resolve().parents[6]
        / "models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt"
    )
    if not checkpoint.exists():
        pytest.skip("trained request classifier artifact is not present in this checkout")
    classifier = RequestRegionClassifier.load(
        checkpoint
    )
    assert classifier.feature_names == (
        "has_tools",
        "log_tool_count",
        "has_tool_calls",
        "log_content_chars",
    )
    probability = classifier.predict_proba({"messages": [{"role": "user", "content": "hello"}]}, 64)
    assert 0.0 <= probability <= 1.0


def test_region_quota_evicts_only_the_requested_region():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
    )

    agent_req = SimpleNamespace(cache_region="agent")
    request_req = SimpleNamespace(cache_region="request")
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [1, 2, 3, 4, 5, 6]), ("region", "agent")),
            value=torch.arange(6),
            req=agent_req,
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [1, 2]), ("region", "request")),
            value=torch.arange(2),
            req=request_req,
        )
    )

    cache.ensure_region_capacity("agent", 0)
    assert cache.region_stats()["agent"]["used_tokens"] == 0
    assert cache.region_stats()["agent"]["eviction_count"] == 1
    assert cache.region_stats()["agent"]["evicted_tokens"] == 6
    assert cache.region_stats()["request"]["used_tokens"] == 2
    assert allocator.free.called

    agent_match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2]), ("region", "agent")))
    )
    request_match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", [1, 2]), ("region", "request")))
    )
    assert len(agent_match.device_indices) == 0
    assert len(request_match.device_indices) == 2


def test_elastic_hit_only_activity_ignores_cold_request_and_refreshes_on_hit():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 32
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="elastic",
        request_cache_elastic_activity_window=4,
        request_cache_elastic_activity_requires_hit=True,
    )
    req = SimpleNamespace(cache_region="request")

    cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [7, 8]), ("region", "request")),
            req=req,
        )
    )
    assert cache.region_quota_stats()["elastic_region_last_access"]["request"] == -1

    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [7, 8]), ("region", "request")),
            value=torch.arange(2),
            req=req,
        )
    )
    cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [7, 8]), ("region", "request")),
            req=req,
        )
    )
    assert cache.region_quota_stats()["elastic_region_last_access"]["request"] >= 0


def test_elastic_ghost_counts_only_eviction_then_revisit_loss():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 4
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="elastic",
        request_cache_elastic_ghost_capacity_tokens=16,
        request_cache_elastic_ghost_pressure_decay=1.0,
    )
    req = SimpleNamespace(cache_region="agent")
    key = RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent"))
    cache.insert(InsertParams(key=key, value=torch.arange(4), req=req))
    cache.ensure_region_capacity("request", 4)
    before = cache.region_quota_stats()["elastic_ghost"]
    assert before["eviction_events"] == 1
    assert before["revisit_tokens"]["agent"] == 0

    result = cache.match_prefix(MatchPrefixParams(key=key, req=req))
    assert len(result.device_indices) == 0
    after = cache.region_quota_stats()["elastic_ghost"]
    assert after["revisit_events"]["agent"] == 1
    assert after["revisit_tokens"]["agent"] == 4
    assert after["pressure_tokens"]["agent"] == pytest.approx(4.0)


def test_elastic_ghost_event_clock_advances_once_per_request():
    ghost = RequestRegionGhostIndex(
        page_size=1, capacity_tokens=16, pressure_decay=1.0
    )
    pages = ((1,), (2,))
    for _ in range(3):
        ghost.observe_match(
            pages,
            extra_key="region",
            actual_tokens=0,
            request_region="agent",
            request_event_key="request-0",
        )
    assert ghost.stats()["event_step"] == 1
    ghost.observe_match(
        pages,
        extra_key="region",
        actual_tokens=0,
        request_region="agent",
        request_event_key="request-1",
    )
    assert ghost.stats()["event_step"] == 2


def test_elastic_ghost_is_bounded_by_metadata_capacity():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 16
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="elastic",
        request_cache_elastic_ghost_capacity_tokens=4,
    )
    req = SimpleNamespace(cache_region="agent")
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(8)), ("region", "agent")),
            value=torch.arange(8),
            req=req,
        )
    )
    cache.ensure_region_capacity("request", 16)
    ghost = cache.region_quota_stats()["elastic_ghost"]
    assert ghost["resident_metadata_tokens"] <= 4
    assert ghost["entry_count"] <= 4


def test_elastic_ghost_protects_a_revisited_borrowed_prefix():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 8
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        page_size=1,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="elastic",
        request_cache_elastic_ghost_capacity_tokens=32,
        request_cache_elastic_ghost_pressure_decay=1.0,
        request_cache_elastic_ghost_bias=0.0,
        request_cache_elastic_ghost_reclaim=False,
        request_cache_elastic_ghost_protect=True,
        request_cache_borrowed_segment_tokens=1,
    )
    req = SimpleNamespace(cache_region="agent")

    def insert(ids):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", "agent")),
                value=torch.arange(len(ids)),
                req=req,
            )
        )

    insert([1, 2, 3, 4])
    # Leave the oldest page resident while recording the other three pages in
    # the bounded ghost, then observe that their loss caused recomputation.
    assert cache.evict(
        EvictParams(num_tokens=4, region="agent", borrowed_only=True)
    ).num_tokens_evicted == 3
    result = cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")),
            req=req,
        )
    )
    assert len(result.device_indices) == 1
    assert cache.region_quota_stats()["elastic_ghost"]["revisit_tokens"]["agent"] == 3

    insert([1, 2, 3, 4])
    insert([10, 11, 12, 13])
    candidates = list(cache.evictable_leaves)
    assert any(cache._elastic_ghost_revisit_score(node) > 0 for node in candidates)
    assert cache.evict(
        EvictParams(num_tokens=1, region="agent", borrowed_only=True)
    ).num_tokens_evicted == 1
    # The unvisited competing prefix is reclaimed first; all four pages of
    # the revisited prefix remain available.
    result = cache.match_prefix(
        MatchPrefixParams(
            key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")),
            req=req,
        )
    )
    assert len(result.device_indices) == 4


def test_borrowed_suffix_granularity_limits_radix_reclaim_overshoot():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 32
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="elastic",
        request_cache_borrowed_segment_tokens=1,
    )
    req = SimpleNamespace(cache_region="agent")
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(20)), ("region", "agent")),
            value=torch.arange(20),
            req=req,
        )
    )

    nodes = []
    stack = [cache.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children.values())
        if node is not cache.root_node:
            nodes.append(node)
    assert all(len(node.key) == 1 for node in nodes[1:])
    result = cache.evict(
        EvictParams(num_tokens=4, region="agent", borrowed_only=True)
    )
    assert result.num_tokens_evicted == 4


def test_dynamic_region_quota_controller_uses_eviction_feedback():
    controller = RequestRegionQuotaController(
        initial_ratio=0.5,
        alpha=0.5,
        min_ratio=0.2,
        max_ratio=0.8,
        feedback_mode="eviction_share",
    )
    controller.observe_insert("agent", 9)
    controller.observe_eviction("agent", 9)
    controller.observe_eviction("request", 1)

    update = controller.observe_request_finished("agent")

    assert update is not None
    assert update.agent_eviction_share == pytest.approx(0.9)
    assert update.new_ratio == pytest.approx(0.7)
    stats = controller.stats()
    assert stats["feedback_agent_evicted_tokens"] == 0
    assert stats["last_feedback_agent_evicted_tokens"] == 9
    assert stats["feedback_update_count"] == 1


def test_dynamic_region_quota_keeps_ratio_without_eviction_feedback():
    controller = RequestRegionQuotaController(
        initial_ratio=0.61,
        alpha=1.0,
        min_ratio=0.2,
        max_ratio=0.8,
    )

    assert controller.observe_request_finished("agent") is None
    assert controller.current_ratio == pytest.approx(0.61)
    assert controller.stats()["last_feedback_agent_eviction_share"] is None


def test_dynamic_region_quota_can_aggregate_small_eviction_events():
    controller = RequestRegionQuotaController(
        initial_ratio=0.5,
        alpha=1.0,
        min_ratio=0.2,
        max_ratio=0.8,
        feedback_mode="eviction_share",
        feedback_min_evicted_tokens=10,
    )
    controller.observe_eviction("agent", 4)
    assert controller.consume_feedback() is None
    assert controller.stats()["feedback_agent_evicted_tokens"] == 4

    controller.observe_eviction("request", 6)
    update = controller.consume_feedback()
    assert update is not None
    assert update.agent_eviction_share == pytest.approx(0.4)
    assert update.new_ratio == pytest.approx(0.4)


def test_normalized_pressure_moves_by_pressure_gap_instead_of_raw_share():
    controller = RequestRegionQuotaController(
        initial_ratio=0.61,
        alpha=0.2,
        min_ratio=0.4,
        max_ratio=0.7,
        feedback_mode="normalized_pressure",
        max_ratio_step=0.05,
    )
    controller.observe_eviction("agent", 20)
    controller.observe_eviction("request", 10)

    update = controller.consume_feedback(
        agent_capacity_tokens=100,
        request_capacity_tokens=100,
    )

    assert update is not None
    assert update.agent_eviction_share == pytest.approx(2 / 3)
    assert update.agent_pressure == pytest.approx(0.2)
    assert update.request_pressure == pytest.approx(0.1)
    assert update.pressure_gap == pytest.approx(0.1)
    assert update.applied_step == pytest.approx(0.02)
    assert update.new_ratio == pytest.approx(0.63)


def test_normalized_pressure_respects_hysteresis_and_token_cooldown():
    controller = RequestRegionQuotaController(
        initial_ratio=0.61,
        alpha=0.5,
        min_ratio=0.4,
        max_ratio=0.7,
        feedback_mode="normalized_pressure",
        max_ratio_step=0.03,
        pressure_hysteresis=0.05,
        cooldown_evicted_tokens=8,
    )
    controller.observe_eviction("agent", 6)
    update = controller.consume_feedback(
        agent_capacity_tokens=100,
        request_capacity_tokens=100,
    )
    assert update is not None
    assert update.applied_step == pytest.approx(0.03)

    controller.observe_eviction("agent", 4)
    assert (
        controller.consume_feedback(
            agent_capacity_tokens=100,
            request_capacity_tokens=100,
        )
        is None
    )
    assert controller.stats()["cooldown_evicted_tokens_remaining"] == 8

    controller.observe_eviction("agent", 4)
    update = controller.consume_feedback(
        agent_capacity_tokens=100,
        request_capacity_tokens=100,
    )
    assert update is not None
    assert update.applied_step == pytest.approx(0.03)


def test_normalized_pressure_accumulates_feedback_inside_hysteresis():
    controller = RequestRegionQuotaController(
        initial_ratio=0.61,
        alpha=0.2,
        min_ratio=0.4,
        max_ratio=0.7,
        feedback_mode="normalized_pressure",
        pressure_hysteresis=0.02,
    )

    controller.observe_eviction("request", 1)
    assert (
        controller.consume_feedback(
            agent_capacity_tokens=100,
            request_capacity_tokens=100,
        )
        is None
    )
    # The first small event is below hysteresis but must remain pending.
    assert controller.stats()["feedback_request_evicted_tokens"] == 1

    controller.observe_eviction("request", 2)
    update = controller.consume_feedback(
        agent_capacity_tokens=100,
        request_capacity_tokens=100,
    )
    assert update is not None
    assert update.request_evicted_tokens == 3
    assert update.new_ratio == pytest.approx(0.604)
    assert controller.stats()["feedback_request_evicted_tokens"] == 0


def test_normalized_pressure_drops_feedback_pushing_past_ratio_bound():
    controller = RequestRegionQuotaController(
        initial_ratio=0.7,
        alpha=0.2,
        min_ratio=0.4,
        max_ratio=0.7,
        feedback_mode="normalized_pressure",
    )

    controller.observe_eviction("agent", 100)
    assert (
        controller.consume_feedback(
            agent_capacity_tokens=100,
            request_capacity_tokens=100,
        )
        is None
    )
    assert controller.stats()["feedback_agent_evicted_tokens"] == 0

    controller.observe_eviction("request", 10)
    update = controller.consume_feedback(
        agent_capacity_tokens=100,
        request_capacity_tokens=100,
    )
    assert update is not None
    assert update.new_ratio < 0.7


def test_dynamic_ratio_preserves_the_ordinary_request_minimum():
    controller = RequestRegionQuotaController(
        initial_ratio=0.5,
        alpha=1.0,
        min_ratio=0.2,
        max_ratio=0.8,
        feedback_mode="normalized_pressure",
        max_ratio_step=1.0,
    )

    # Agent pressure can repeatedly push toward the upper bound, but the
    # ordinary region must retain the complementary minimum fraction.
    for _ in range(4):
        controller.observe_eviction("agent", 100)
        controller.consume_feedback(
            agent_capacity_tokens=100,
            request_capacity_tokens=100,
        )

    assert controller.current_ratio == pytest.approx(0.8)
    assert controller.current_ratio <= 1.0 - controller.request_min_ratio
    assert controller.stats()["request_min_ratio"] == pytest.approx(0.2)

    # The lower bound is symmetric: ordinary pressure cannot remove the
    # Agent minimum either.
    for _ in range(4):
        controller.observe_eviction("request", 100)
        controller.consume_feedback(
            agent_capacity_tokens=100,
            request_capacity_tokens=100,
        )
    assert controller.current_ratio == pytest.approx(0.2)
    assert controller.current_ratio >= controller.min_ratio


def test_dynamic_region_quota_discards_rebalance_feedback():
    controller = RequestRegionQuotaController(
        initial_ratio=0.5,
        alpha=0.5,
        min_ratio=0.2,
        max_ratio=0.8,
    )
    controller.observe_eviction("agent", 8)
    controller.discard_pending_feedback()
    assert controller.consume_feedback() is None


def test_classic_cache_updates_dynamic_ratio_and_reclaims_shrunk_region():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="dynamic",
        request_cache_ratio_alpha=1.0,
        request_cache_ratio_feedback_mode="eviction_share",
        request_cache_ratio_cooldown_evicted_tokens=0,
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )

    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 9)), ("region", "agent")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.ensure_region_capacity("agent", 0)
    cache._on_request_region_finished("agent")

    assert cache.request_agent_cache_ratio == pytest.approx(0.8)
    assert cache.region_stats()["agent"]["capacity_tokens"] == 8
    assert cache.region_stats()["request"]["capacity_tokens"] == 2
    assert cache.region_quota_stats()["request_min_ratio"] == pytest.approx(0.2)
    assert cache.region_quota_stats()["last_feedback_agent_evicted_tokens"] == 8

    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 19)), ("region", "request")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="request"),
        )
    )
    cache.ensure_region_capacity("request", 0)
    cache._on_request_region_finished("request")

    stats = cache.region_stats()
    assert cache.request_agent_cache_ratio == pytest.approx(0.2)
    assert stats["agent"]["used_tokens"] == 0
    assert stats["agent"]["evicted_tokens"] == 8
    assert stats["request"]["used_tokens"] == 0


def test_classic_borrow_dynamic_combines_feedback_with_idle_capacity_borrowing():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow_dynamic",
        request_cache_ratio_alpha=1.0,
        request_cache_ratio_feedback_mode="eviction_share",
        request_cache_ratio_cooldown_evicted_tokens=0,
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )

    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 9)), ("region", "agent")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    assert cache.region_stats()["agent"]["capacity_tokens"] == 10
    assert cache.region_quota_stats()["policy"] == "borrow_dynamic"

    cache.evict(
        EvictParams(
            num_tokens=8,
            borrowed_only=True,
            borrow_reclaim_reason="global_overage",
        )
    )
    cache._on_request_region_finished("agent")

    assert cache.request_agent_cache_ratio == pytest.approx(0.8)
    assert cache.region_quota_stats()["policy"] == "borrow_dynamic"


def test_allocator_region_eviction_falls_back_for_locked_shortage():
    """A locked active batch may require a global fallback to make progress."""
    class FakeAllocator:
        def __init__(self):
            self.available = 0

        def available_size(self):
            return self.available

    class FakeCache:
        def __init__(self):
            self.token_to_kv_pool_allocator = FakeAllocator()
            self.calls = []

        def is_chunk_cache(self):
            return False

        def evict(self, params):
            self.calls.append(params)
            if params.region is None:
                self.token_to_kv_pool_allocator.available = 8

    cache = FakeCache()
    from sglang.srt.mem_cache.common import evict_from_tree_cache

    evict_from_tree_cache(cache, 8, region="agent")

    assert [call.region for call in cache.calls] == ["agent", None]
    assert cache.calls[0].num_tokens == 8
    assert cache.calls[1].num_tokens == 8


def test_classic_borrow_policy_uses_idle_region_capacity_without_changing_ratio():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 9)), ("region", "agent")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    stats = cache.region_stats()
    assert stats["agent"]["base_capacity_tokens"] == 5
    assert stats["agent"]["borrowed_tokens"] == 5
    assert stats["agent"]["effective_capacity_tokens"] == 10
    assert stats["agent"]["used_tokens"] == 8
    assert cache.request_agent_cache_ratio == pytest.approx(0.5)


def test_classic_borrow_policy_reclaims_borrowed_pages_for_owner():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )
    for token in range(1, 9):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", [token]), ("region", "agent")),
                value=torch.tensor([token]),
                req=SimpleNamespace(cache_region="agent"),
            )
        )
    cache.ensure_region_capacity("request", 3)
    stats = cache.region_stats()
    assert stats["agent"]["used_tokens"] == 7
    assert stats["request"]["used_tokens"] == 0
    assert stats["agent"]["evicted_tokens"] == 1
    assert stats["request"]["capacity_tokens"] == 5


def test_classic_borrow_reclaims_borrowed_nodes_before_protected_nodes():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
        request_cache_borrow_high_watermark_tokens=2,
        request_cache_borrow_low_watermark_tokens=1,
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 6)), ("region", "agent")),
            value=torch.arange(5),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 14)), ("region", "agent")),
            value=torch.arange(3),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    nodes = []
    stack = [cache.root_node]
    while stack:
        node = stack.pop()
        if node.cache_region == "agent":
            nodes.append(node)
        stack.extend(node.children.values())
    assert sorted((len(node.key), node.region_borrowed) for node in nodes) == [
        (3, True),
        (5, False),
    ]

    cache.ensure_region_capacity("request", 3)
    stats = cache.region_stats()
    assert stats["agent"]["used_tokens"] == 5
    assert stats["agent"]["cached_borrowed_tokens"] == 0
    assert stats["agent"]["evicted_tokens"] == 3
    assert stats["agent"]["borrowed_eviction_count"] == 1
    assert stats["agent"]["borrowed_evicted_tokens"] == 3
    assert stats["agent"]["borrow_reclaim_reasons"] == {"global_overage": 1}
    match = cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", range(1, 6)), ("region", "agent")))
    )
    assert len(match.device_indices) == 5


def test_classic_borrow_reclaim_never_promotes_a_protected_parent():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )
    region_req = SimpleNamespace(cache_region="agent")

    # The first node fills the Agent guarantee. The one-token child is
    # borrowed, while its five-token parent remains protected.
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 6)), ("region", "agent")),
            value=torch.arange(5),
            req=region_req,
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 7)), ("region", "agent")),
            value=torch.arange(6),
            req=region_req,
        )
    )

    # A six-token request creates two tokens of global overage. Only one
    # borrowed token exists, so reclaim must stop there rather than promoting
    # the protected parent into the same eviction heap.
    cache.ensure_region_capacity("request", 6)
    stats = cache.region_stats()
    assert stats["agent"]["used_tokens"] == 5
    assert stats["agent"]["evicted_tokens"] == 1
    assert stats["agent"]["borrowed_evicted_tokens"] == 1
    assert stats["agent"]["borrow_reclaim_reasons"] == {"global_overage": 1}


def test_classic_borrow_marks_only_actual_idle_capacity_as_borrowed():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )

    # Both regions are already beyond their guarantees when the request
    # suffix is inserted, so that suffix is over-quota rather than borrowed.
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 9)), ("region", "agent")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 16)), ("region", "request")),
            value=torch.arange(5),
            req=SimpleNamespace(cache_region="request"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 19)), ("region", "request")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="request"),
        )
    )

    request_nodes = []
    stack = [cache.root_node]
    while stack:
        node = stack.pop()
        if node.cache_region == "request":
            request_nodes.append(node)
        stack.extend(node.children.values())
    assert request_nodes
    assert all(not node.region_borrowed for node in request_nodes)
    assert cache.region_stats()["request"]["cached_borrowed_tokens"] == 0


def test_classic_borrow_marks_page_that_crosses_guarantee_boundary():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )

    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [1, 2, 3, 4]), ("region", "agent")),
            value=torch.arange(4),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [11, 12]), ("region", "agent")),
            value=torch.arange(2),
            req=SimpleNamespace(cache_region="agent"),
        )
    )

    nodes = []
    stack = [cache.root_node]
    while stack:
        node = stack.pop()
        if node.cache_region == "agent":
            nodes.append(node)
        stack.extend(node.children.values())
    assert sorted((len(node.key), node.region_borrowed) for node in nodes) == [
        (2, True),
        (4, False),
    ]
    assert cache.region_stats()["agent"]["cached_borrowed_tokens"] == 2


def test_classic_lazy_borrow_reclassifies_only_at_fallback_boundary():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
        request_cache_borrow_lazy_reclassify=True,
    )
    # Fill both guarantees first.  The Agent surplus is therefore protected
    # at insertion time even though the request side later becomes idle.
    for token in range(1, 6):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", [100 + token]), ("region", "request")),
                value=torch.tensor([token]),
                req=SimpleNamespace(cache_region="request"),
            )
        )
    for token in range(1, 9):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", [token]), ("region", "agent")),
                value=torch.tensor([token]),
                req=SimpleNamespace(cache_region="agent"),
            )
        )
    assert cache.region_stats()["agent"]["cached_borrowed_tokens"] == 0

    cache.evict(EvictParams(num_tokens=5, region="request"))
    # The ordinary quota is now idle, but the lazy mode does not scan the tree
    # during a normal quota check.
    cache.ensure_region_capacity("agent", 0)
    assert cache.region_stats()["agent"]["cached_borrowed_tokens"] == 0

    cache._reclassify_borrowed_for_fallback()
    assert cache.region_stats()["agent"]["cached_borrowed_tokens"] == 3


def test_borrow_batch_reservation_accounts_for_both_regions_before_allocating():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )
    for region, offset, count in (("agent", 0, 8), ("request", 100, 1)):
        for token in range(offset + 1, offset + count + 1):
            cache.insert(
                InsertParams(
                    key=RadixKey(array("q", [token]), ("region", region)),
                    value=torch.tensor([token]),
                    req=SimpleNamespace(cache_region=region),
                )
            )

    # Each individual reservation fits the current global pool, but their
    # combined reservation crosses it. The batch path must reclaim one already
    # borrowed Agent token before the allocator's generic fallback.
    cache.ensure_region_capacities({"agent": 1, "request": 1})
    stats = cache.region_stats()
    assert stats["agent"]["evicted_tokens"] == 1
    assert stats["agent"]["borrowed_evicted_tokens"] == 1
    assert stats["request"]["evicted_tokens"] == 0


def test_borrow_reclaims_current_region_before_other_region():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow",
    )

    # Leave a stale, but still reclaimable, Agent borrowed leaf behind.
    for ids in ([1, 2, 3, 4], [5, 6]):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", "agent")),
                value=torch.tensor(ids),
                req=SimpleNamespace(cache_region="agent"),
            )
        )
    cache.evict(EvictParams(num_tokens=4, region="agent"))

    # Direct insertion mirrors a mixed scheduler batch and leaves borrowed
    # leaves in both regions before the next reservation is checked.
    cache.insert(
        InsertParams(
            key=RadixKey(
                array("q", [11, 12, 13, 14, 15, 16]),
                ("region", "request"),
            ),
            value=torch.arange(6),
            req=SimpleNamespace(cache_region="request"),
        )
    )
    cache.ensure_region_capacity("request", 3)

    stats = cache.region_stats()
    assert stats["request"]["borrowed_evicted_tokens"] == 6
    assert stats["agent"]["borrowed_evicted_tokens"] == 0
    assert stats["agent"]["cached_borrowed_tokens"] == 2


def test_borrow_global_reclaims_oldest_borrowed_region():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow_global",
    )

    # Leave an older Agent borrowed leaf behind while the Agent owner falls
    # below its guarantee. The later Request insertion then creates a second
    # borrowed leaf, so a global reclaim should choose the older Agent page.
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [1, 2, 3, 4, 5]), ("region", "agent")),
            value=torch.arange(5),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [6, 7, 8]), ("region", "agent")),
            value=torch.arange(3),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.evict(EvictParams(num_tokens=5, region="agent"))
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 19)), ("region", "request")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="request"),
        )
    )

    cache.ensure_region_capacity("request", 0)
    stats = cache.region_stats()
    assert stats["agent"]["borrowed_evicted_tokens"] == 3
    assert stats["request"]["borrowed_evicted_tokens"] == 0
    assert stats["agent"]["borrow_reclaim_reasons"] == {"global_overage": 1}


def test_borrow_reclass_promotes_pages_after_other_region_frees_space():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow_reclass",
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 6)), ("region", "agent")),
            value=torch.arange(5),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(11, 16)), ("region", "request")),
            value=torch.arange(5),
            req=SimpleNamespace(cache_region="request"),
        )
    )
    # The Agent suffix is inserted while the request guarantee is full, so it
    # is initially protected. Once the request side releases its page, the
    # reclass variant can expose the old Agent surplus as a reclaimable loan.
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(21, 24)), ("region", "agent")),
            value=torch.arange(3),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.evict(EvictParams(num_tokens=5, region="request"))
    cache.ensure_region_capacity("agent", 0)
    assert cache.region_stats()["agent"]["cached_borrowed_tokens"] >= 3


def test_borrow_request_reclass_only_promotes_request_surplus():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.5,
        request_cache_region_policy="borrow_request_reclass",
    )
    for ids, region in (
        (range(1, 6), "request"),
        (range(11, 16), "agent"),
        (range(21, 24), "request"),
    ):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", region)),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region=region),
            )
        )
    cache.evict(EvictParams(num_tokens=5, region="agent"))
    cache.ensure_region_capacity("request", 0)
    stats = cache.region_stats()
    assert stats["agent"]["cached_borrowed_tokens"] == 0
    assert stats["request"]["cached_borrowed_tokens"] >= 3


def test_elastic_policy_exposes_shared_pool_without_changing_configured_ratio():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 7)), ("region", "agent")),
            value=torch.arange(6),
            req=SimpleNamespace(cache_region="agent"),
        )
    )

    stats = cache.region_stats()
    quota_stats = cache.region_quota_stats()
    assert cache.request_agent_cache_ratio == pytest.approx(0.61)
    assert quota_stats["agent_min_ratio"] == pytest.approx(0.2)
    assert quota_stats["request_min_ratio"] == pytest.approx(0.2)
    assert quota_stats["elastic_pool_ratio"] == pytest.approx(0.6)
    assert stats["agent"]["base_capacity_tokens"] == 2
    assert stats["request"]["base_capacity_tokens"] == 1
    assert stats["agent"]["cached_borrowed_tokens"] == 6
    assert stats["agent"]["capacity_tokens"] == 10


def test_elastic_empty_soft_split_uses_safety_band_midpoint():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )

    # Elastic mode has no resident-mix evidence at startup.  Its soft tier
    # must therefore be independent of the fixed-partition ratio.
    assert cache._elastic_preferred_agent_ratio() == pytest.approx(0.5)
    assert cache.region_quota_stats()["elastic_observed_agent_ratio"] == pytest.approx(0.5)
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.5)


def test_elastic_activity_window_keeps_stale_region_minimum_reserve():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_elastic_activity_window=2,
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )

    # A cold cache, or a one-sided burst, keeps the configured return reserve.
    assert cache._elastic_activity_floor_ratio() == pytest.approx(0.61)
    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 0, "request": 9}
    assert cache._elastic_activity_floor_ratio() == pytest.approx(0.61)
    assert cache._region_base_quotas(10) == {"agent": 6, "request": 4}

    cache._elastic_region_last_access = {"agent": 9, "request": 10}
    assert cache._elastic_activity_floor_ratio() is None
    assert cache._region_base_quotas(10) == {"agent": 2, "request": 1}

    # The same configured reserve is retained for the symmetric case.
    cache._elastic_region_last_access = {"agent": 9, "request": 0}
    assert cache._elastic_activity_floor_ratio() == pytest.approx(0.61)
    assert cache._region_base_quotas(10) == {"agent": 6, "request": 4}


def test_elastic_preferred_reclaim_requires_history_for_stale_region():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_elastic_activity_window=4,
    )
    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 10, "request": 1}
    cache._elastic_last_access_region = "agent"
    cache._elastic_region_run_length = {"agent": 5, "request": 1}
    cache._elastic_region_access_count = {"agent": 5, "request": 1}
    assert cache._elastic_preferred_reclaim_active() is False

    cache._elastic_region_access_count["request"] = 4
    assert cache._elastic_preferred_reclaim_active() is True


def test_elastic_soft_step_limits_phase_change_per_pressure_boundary():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_cache_region_policy="elastic",
        request_cache_elastic_soft_step=0.1,
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for region, ids in (
        ("request", [1, 2, 3]),
        ("agent", [11, 12, 13, 14, 15, 16]),
    ):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", region)),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region=region),
            )
        )

    target = cache._elastic_target_agent_ratio()
    cache._refresh_elastic_preferred_borrowed()
    assert target > 0.5
    assert cache._elastic_preferred_agent_ratio() == pytest.approx(0.6)
    assert cache._elastic_preferred_agent_ratio() < target


def test_elastic_pressure_marks_active_region_tail_first_when_request_is_idle():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 10)), ("region", "agent")),
            value=torch.arange(9),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [11]), ("region", "request")),
            value=torch.arange(1),
            req=SimpleNamespace(cache_region="request"),
        )
    )

    # The request side is below its 20% minimum.  Keep the configured soft
    # split, but choose the newest Agent suffix as the preferred victim when
    # the pending allocation reaches physical pressure.
    assert cache._elastic_target_agent_ratio() == pytest.approx(0.8)
    cache._refresh_elastic_preferred_borrowed(pending_tokens=1)
    assert cache._elastic_tail_first_regions == {"agent"}


def test_elastic_activity_window_suppresses_stale_opposite_region_tail_first():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
        request_cache_elastic_activity_window=2,
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 10)), ("region", "agent")),
            value=torch.arange(9),
            req=SimpleNamespace(cache_region="agent"),
        )
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [11]), ("region", "request")),
            value=torch.arange(1),
            req=SimpleNamespace(cache_region="request"),
        )
    )

    # The request side is below its minimum, but its last access is stale.
    cache._elastic_region_access_epoch = 10
    cache._elastic_region_last_access = {"agent": 0, "request": 1}
    cache._refresh_elastic_preferred_borrowed(pending_tokens=1)
    assert cache._elastic_tail_first_regions == set()
    assert cache._elastic_tail_first_activity_suppressed == 1

    # A recent request access re-enables the same reclaim tier.
    cache._elastic_region_last_access["request"] = 9
    cache._refresh_elastic_preferred_borrowed(pending_tokens=1)
    assert cache._elastic_tail_first_regions == {"agent"}


def test_elastic_soft_line_accounts_for_pending_pressure():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", range(1, 9)), ("region", "agent")),
            value=torch.arange(8),
            req=SimpleNamespace(cache_region="agent"),
        )
    )

    assert cache._elastic_target_agent_ratio() == pytest.approx(0.8)
    assert cache._elastic_target_agent_ratio(pending_tokens=2) == pytest.approx(0.8)


def test_elastic_marks_tokens_above_each_minimum_as_borrowed():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for ids in ([1, 2], [3, 4, 5]):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", "agent")),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region="agent"),
            )
        )

    nodes = []
    stack = [cache.root_node]
    while stack:
        node = stack.pop()
        if node.cache_region == "agent":
            nodes.append(node)
        stack.extend(node.children.values())
    assert sorted((len(node.key), node.region_borrowed) for node in nodes) == [
        (2, False),
        (3, True),
    ]


def test_elastic_preferred_tier_follows_current_resident_mix():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )

    for key in ([1, 2, 3], [4, 5, 6], [7, 8, 9]):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", key), ("request", key[0])),
                value=torch.arange(3),
                req=SimpleNamespace(cache_region="request"),
            )
        )
    cache.insert(
        InsertParams(
            key=RadixKey(array("q", [11, 12, 13]), ("agent", 11)),
            value=torch.arange(3),
            req=SimpleNamespace(cache_region="agent"),
        )
    )

    # The Agent burst starts while the request side still occupies most of
    # the resident set, so its page is initially in the preferred tier.
    assert cache.region_preferred_borrowed_tokens["agent"] > 0
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.25)

    # Once the request side releases its pages, the observed mix moves to the
    # Agent upper bound. The old insertion-time label must be removed before
    # the next shared-pool reclaim.
    cache.evict(EvictParams(num_tokens=9, region="request"))
    cache._refresh_elastic_preferred_borrowed()
    assert cache.region_quota_stats()["elastic_soft_agent_ratio"] == pytest.approx(0.8)
    assert cache.region_preferred_borrowed_tokens["agent"] == 0


def test_elastic_reclaims_agent_shared_pages_before_protected_pages():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for ids in ([1, 2], [3, 4, 5, 6]):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", "agent")),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region="agent"),
            )
        )

    # A request reservation creates one token of global pressure. The
    # borrowed four-token Agent leaf is legal to reclaim; its protected
    # two-token leaf must remain.
    cache.ensure_region_capacity("request", 5)
    stats = cache.region_stats()
    assert stats["agent"]["used_tokens"] == 2
    assert stats["agent"]["borrowed_evicted_tokens"] == 4
    assert stats["agent"]["cached_borrowed_tokens"] == 0


def test_elastic_keeps_both_minimums_when_the_shared_pool_has_room():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for region, ids in (
        ("agent", [1, 2, 3, 4, 5, 6]),
        ("request", [11, 12]),
    ):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", region)),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region=region),
            )
        )

    cache.ensure_region_capacity("request", 1)
    stats = cache.region_stats()
    assert stats["agent"]["evicted_tokens"] == 0
    assert stats["request"]["evicted_tokens"] == 0
    assert stats["agent"]["used_tokens"] == 6
    assert stats["request"]["used_tokens"] == 2


def test_elastic_reclaims_the_larger_region_surplus_first():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for region, ids in (
        ("agent", [1, 2, 3, 4]),
        ("request", [11, 12, 13, 14, 15, 16, 17]),
    ):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", region)),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region=region),
            )
        )

    # Request owns the larger elastic surplus. Agent pressure should release
    # that request surplus before discarding Agent history.
    cache.ensure_region_capacity("agent", 3)
    stats = cache.region_stats()
    assert stats["request"]["borrowed_evicted_tokens"] > 0
    assert stats["agent"]["used_tokens"] == 4


def test_elastic_pressure_first_reclaims_requesting_region_surplus():
    allocator = Mock()
    allocator.device = torch.device("cpu")
    allocator.size = 10
    allocator.free = Mock()
    cache = RadixCache.create_simulated(
        mock_allocator=allocator,
        enable_request_cache_regions=True,
        request_agent_cache_ratio=0.61,
        request_cache_region_policy="elastic",
        request_cache_elastic_reclaim_order="pressure_first",
        request_cache_agent_min_ratio=0.2,
        request_cache_agent_max_ratio=0.8,
    )
    for region, ids in (
        ("agent", [1, 2, 3, 4]),
        ("request", [11, 12, 13, 14, 15, 16, 17]),
    ):
        cache.insert(
            InsertParams(
                key=RadixKey(array("q", ids), ("region", region)),
                value=torch.arange(len(ids)),
                req=SimpleNamespace(cache_region=region),
            )
        )

    # Agent pressure now gives the requesting region's borrowed tail first
    # chance, leaving the ordinary return reserve intact.
    cache.ensure_region_capacity("agent", 3)
    stats = cache.region_stats()
    assert stats["agent"]["borrowed_evicted_tokens"] > 0
    assert stats["request"]["borrowed_evicted_tokens"] == 0
    assert stats["request"]["used_tokens"] == 7
