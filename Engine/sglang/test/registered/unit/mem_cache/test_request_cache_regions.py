from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import torch
import pytest

from sglang.srt.mem_cache.base_prefix_cache import InsertParams, MatchPrefixParams
from sglang.srt.managers.io_struct import GenerateReqInput
from sglang.srt.mem_cache.radix_cache import RadixCache, RadixKey
from sglang.srt.mem_cache.request_region import RequestRegionClassifier, extract_features


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
