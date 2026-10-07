from __future__ import annotations

from sglang.srt.mem_cache.cache_init_params import CacheInitParams

"""
Copyright 2023-2024 SGLang Team
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
The radix tree data structure for managing the KV cache.
"""

import hashlib
import heapq
import logging
import math
import sys
import time
from array import array
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterator, List, Optional, Tuple, Union

import torch

logger = logging.getLogger(__name__)

from sglang.srt.mem_cache.base_prefix_cache import (
    BasePrefixCache,
    DecLockRefParams,
    DecLockRefResult,
    EvictParams,
    EvictResult,
    IncLockRefResult,
    InsertParams,
    InsertResult,
    MatchPrefixParams,
    MatchResult,
)
from sglang.srt.mem_cache.events import KVCacheEventMixin
from sglang.srt.mem_cache.mlp_reuse import (
    MlpReuseMixin,
    copy_mlp_on_split,
    init_mlp_fields,
)
from sglang.srt.mem_cache.request_region_quota import RequestRegionQuotaController
from sglang.srt.mem_cache.request_region_ghost import (
    RequestRegionGhostIndex,
    logical_pages,
    prefix_pages_for_node,
    rolling_prefix_keys,
)
from sglang.srt.mem_cache.utils import get_eviction_strategy, split_node_hash_value

if TYPE_CHECKING:
    from sglang.srt.managers.schedule_batch import Req


class RadixKey:
    """is_bigram=True: token_ids holds raw tokens (N+1 for N bigrams); slices share one boundary token."""

    __slots__ = ("token_ids", "extra_key", "is_bigram")

    def __init__(
        self,
        token_ids: array[int],
        extra_key: Optional[str] = None,
        is_bigram: bool = False,
    ):
        # token ids sequence (raw ints in both modes)
        self.token_ids = token_ids
        # extra key (e.g. lora_id, cache_salt)
        self.extra_key = extra_key
        # bigram view over token_ids: length = max(0, len(token_ids) - 1)
        self.is_bigram = is_bigram

    def __len__(self) -> int:
        if self.is_bigram:
            n = len(self.token_ids)
            return n - 1 if n > 0 else 0
        return len(self.token_ids)

    # TODO(Jialin): vectorize with numpy without PyLong boxing
    def __iter__(self) -> Iterator:
        if self.is_bigram:
            t = self.token_ids
            for i in range(len(t) - 1):
                yield (t[i], t[i + 1])
        else:
            yield from self.token_ids

    def __getitem__(self, idx: Union[int, slice]) -> "RadixKey":
        # Normalize int -> 1-element slice so the rest handles one shape.
        if isinstance(idx, int):
            if idx < 0:
                idx += len(self)
            if idx < 0 or idx >= len(self):
                raise IndexError(f"RadixKey index out of range: {idx}")
            idx = slice(idx, idx + 1)
        start, stop, step = idx.indices(len(self))
        if step != 1:
            raise ValueError("RadixKey slice step must be 1")

        if self.is_bigram:
            # bigrams [start, stop) span raw tokens [start, stop + 1);
            # empty slice -> empty raw tokens (not a dangling boundary token).
            raw = self.token_ids[start : stop + 1] if stop > start else array("q")
            return RadixKey(raw, self.extra_key, is_bigram=True)
        return RadixKey(self.token_ids[start:stop], self.extra_key)

    def __repr__(self) -> str:
        preview = self.token_ids[:10]
        return f"RadixKey(extra_key={self.extra_key!r}, token_ids={preview}{'...' if len(self.token_ids) > 10 else ''}, is_bigram={self.is_bigram})"

    def page_aligned(self, page_size: int) -> "RadixKey":
        if page_size == 1:
            return self
        aligned_len = len(self) // page_size * page_size
        return self[:aligned_len]

    def maybe_to_bigram_view(
        self,
        is_eagle: bool,
        value: Optional[torch.Tensor] = None,
    ) -> Tuple["RadixKey", Optional[torch.Tensor]]:
        # O(1): flip the bigram flag instead of materializing a tuple list.
        # value is paired with raw tokens and gets truncated to the bigram count.
        if is_eagle and not self.is_bigram:
            self.is_bigram = True
            if value is not None:
                value = value[: len(self)]
        return self, value

    def _check_compatible(self, other: "RadixKey") -> None:
        if self.extra_key != other.extra_key:
            raise ValueError(
                f"RadixKey operations require matching extra_key, but got "
                f"{self.extra_key=} != {other.extra_key=}"
            )

    def match(self, other: "RadixKey", page_size: int = 1) -> int:
        """Logical-unit prefix length shared with ``other``. Result is rounded down to ``page_size``."""
        self._check_compatible(other)
        t0, t1 = self.token_ids, other.token_ids
        assert type(t0) is type(t1), (type(t0), type(t1))
        n = min(len(t0), len(t1))

        # Exponential search for the first diverging token: gallop in doubling
        # windows (one C-level slice compare each), then binary-search the window
        # holding the divergence -- no per-token Python loop on long shared prefixes.
        matched_tokens = n
        lo = 0
        step = 1
        while lo < n:
            hi = lo + step if lo + step < n else n
            if t0[lo:hi] != t1[lo:hi]:
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if t0[lo:mid] == t1[lo:mid]:
                        lo = mid
                    else:
                        hi = mid
                matched_tokens = lo
                break
            lo = hi
            step *= 2

        if self.is_bigram:
            matched = max(0, min(matched_tokens - 1, len(self), len(other)))
            return (matched // page_size) * page_size if page_size > 1 else matched

        if page_size == 1:
            return matched_tokens
        return (matched_tokens // page_size) * page_size

    def child_key(self, page_size: int = 1):
        """Hashable dict-key for the first ``page_size`` logical units, namespaced by ``extra_key``."""
        t = self.token_ids
        if self.is_bigram:
            if page_size == 1:
                plain = (t[0], t[1])
            else:
                plain = tuple((t[j], t[j + 1]) for j in range(page_size))
        else:
            plain = t[0] if page_size == 1 else tuple(t[:page_size])
        return plain if self.extra_key is None else (self.extra_key, plain)

    def hash_page(self, start: int, end: int, prior_hash: Optional[str] = None) -> str:
        """SHA256 for logical units [start, end); bigram mode feeds overlapping (t_i, t_{i+1}) byte pairs."""
        hasher = hashlib.sha256()
        if prior_hash:
            hasher.update(bytes.fromhex(prior_hash))
        t = self.token_ids
        if self.is_bigram:
            for j in range(start, end):
                hasher.update(t[j].to_bytes(4, byteorder="little", signed=False))
                hasher.update(t[j + 1].to_bytes(4, byteorder="little", signed=False))
        else:
            for j in range(start, end):
                hasher.update(t[j].to_bytes(4, byteorder="little", signed=False))
        return hasher.hexdigest()


class TreeNode:
    counter = 0

    def __init__(self, id: Optional[int] = None, priority: int = 0):
        self.children = defaultdict(TreeNode)
        self.parent: TreeNode = None
        self.key: RadixKey = None
        self.value: Optional[torch.Tensor] = None
        self.lock_ref = 0
        self.last_access_time = time.monotonic()
        self.creation_time = time.monotonic()

        self.hit_count = 0
        # Online, label-free reuse-value metadata. These fields are inert for
        # eviction policies other than ``reuse_value``.
        self.reuse_strength = 0.0
        self.last_turnover = 0.0
        self.reuse_count = 0
        self.terminal_count = 0
        self.prefix_depth = 0
        self.reuse_value_density = 0.0
        init_mlp_fields(self)
        # indicating the node is locked to protect from eviction
        # incremented when the node is referenced by a storage operation
        self.host_ref_counter = 0
        # store the host indices of KV cache
        self.host_value: Optional[torch.Tensor] = None
        self.write_through_pending_id: Optional[int] = None
        # store hash values of each pages
        self.hash_value: Optional[List[str]] = None
        # priority for priority-aware eviction
        self.priority = priority
        self.cache_region: Optional[str] = None
        # Request-region borrow metadata. A borrowed node is outside its
        # region's fixed base quota and may be reclaimed for the owner region.
        self.region_borrowed = False
        self.region_preferred_borrowed = False

        self.id = TreeNode.counter if id is None else id
        TreeNode.counter += 1

    @property
    def evicted(self):
        return self.value is None

    @property
    def backuped(self):
        return self.host_value is not None

    def protect_host(self):
        """Protect the host value from eviction."""
        self.host_ref_counter += 1

    def release_host(self):
        """Release the host value, allowing it to be evicted."""
        if self.host_ref_counter > 0:
            self.host_ref_counter -= 1
        else:
            raise RuntimeError("Host reference counter is already zero.")

    def get_last_hash_value(self) -> Optional[str]:
        """Returns the hash value of the last page in this node."""
        if self.hash_value is None or len(self.hash_value) == 0:
            return None
        return self.hash_value[-1]

    def get_prefix_hash_values(self, node: TreeNode) -> List[str]:
        if node is None or node.hash_value is None:
            return []

        return node.get_prefix_hash_values(node.parent) + node.hash_value

    def __lt__(self, other: "TreeNode"):
        return self.last_access_time < other.last_access_time


class RadixCache(MlpReuseMixin, KVCacheEventMixin, BasePrefixCache):
    def __init__(self, params: CacheInitParams):
        self.disable = params.disable
        self.req_to_token_pool = params.req_to_token_pool
        self.token_to_kv_pool_allocator = params.token_to_kv_pool_allocator
        self.page_size = params.page_size
        self.enable_kv_cache_events = params.enable_kv_cache_events
        self.is_eagle = params.is_eagle
        self.disable_finished_insert = params.disable_finished_insert
        self.request_regions_enabled = params.enable_request_cache_regions
        self.request_agent_cache_ratio = float(params.request_agent_cache_ratio)
        if (
            self.request_regions_enabled
            and not 0.0 < self.request_agent_cache_ratio < 1.0
        ):
            raise ValueError("request_agent_cache_ratio must be between 0 and 1")
        self.request_cache_region_policy = params.request_cache_region_policy
        if self.request_cache_region_policy not in (
            "fixed",
            "dynamic",
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            raise ValueError(
                "request_cache_region_policy must be 'fixed', 'dynamic', 'borrow', 'borrow_dynamic', 'borrow_global', 'borrow_reclass', 'borrow_request_reclass', or 'elastic'"
            )
        self.request_cache_agent_min_ratio = float(
            getattr(params, "request_cache_agent_min_ratio", 0.2)
        )
        self.request_cache_agent_max_ratio = float(
            getattr(params, "request_cache_agent_max_ratio", 0.8)
        )
        self.request_cache_elastic_reclaim_order = str(
            getattr(params, "request_cache_elastic_reclaim_order", "request_first")
        )
        self.request_cache_elastic_preferred_reclaim = bool(
            getattr(params, "request_cache_elastic_preferred_reclaim", True)
        )
        if self.request_cache_elastic_reclaim_order not in (
            "request_first",
            "pressure_first",
        ):
            raise ValueError(
                "request_cache_elastic_reclaim_order must be 'request_first' or 'pressure_first'"
            )
        self.request_cache_elastic_soft_step = float(
            getattr(params, "request_cache_elastic_soft_step", 1.0)
        )
        if not 0.0 < self.request_cache_elastic_soft_step <= 1.0:
            raise ValueError("request_cache_elastic_soft_step must be in (0, 1]")
        self.request_cache_elastic_activity_window = int(
            getattr(params, "request_cache_elastic_activity_window", 0)
        )
        if self.request_cache_elastic_activity_window < 0:
            raise ValueError(
                "request_cache_elastic_activity_window must be non-negative"
            )
        self.request_cache_elastic_activity_requires_hit = bool(
            getattr(params, "request_cache_elastic_activity_requires_hit", False)
        )
        self.request_cache_elastic_ghost_capacity_tokens = int(
            getattr(params, "request_cache_elastic_ghost_capacity_tokens", 0)
        )
        self.request_cache_elastic_ghost_pressure_decay = float(
            getattr(params, "request_cache_elastic_ghost_pressure_decay", 0.95)
        )
        self.request_cache_elastic_ghost_bias = float(
            getattr(params, "request_cache_elastic_ghost_bias", 0.5)
        )
        self.request_cache_elastic_ghost_reclaim = bool(
            getattr(params, "request_cache_elastic_ghost_reclaim", True)
        )
        self.request_cache_elastic_ghost_protect = bool(
            getattr(params, "request_cache_elastic_ghost_protect", False)
        )
        self.request_cache_elastic_ghost_protect_min_tokens = int(
            getattr(params, "request_cache_elastic_ghost_protect_min_tokens", 0)
        )
        if self.request_cache_elastic_ghost_protect_min_tokens < 0:
            raise ValueError(
                "request_cache_elastic_ghost_protect_min_tokens must be non-negative"
            )
        self.request_cache_elastic_feedback = bool(
            getattr(params, "request_cache_elastic_feedback", False)
        )
        if self.request_cache_elastic_ghost_capacity_tokens < 0:
            raise ValueError(
                "request_cache_elastic_ghost_capacity_tokens must be non-negative"
            )
        if not 0.0 < self.request_cache_elastic_ghost_pressure_decay <= 1.0:
            raise ValueError(
                "request_cache_elastic_ghost_pressure_decay must be in (0, 1]"
            )
        if self.request_cache_elastic_ghost_bias < 0.0:
            raise ValueError("request_cache_elastic_ghost_bias must be non-negative")
        if self.request_cache_region_policy == "elastic" and not (
            0.0
            < self.request_cache_agent_min_ratio
            < self.request_cache_agent_max_ratio
            < 1.0
            and self.request_cache_agent_min_ratio
            + (1.0 - self.request_cache_agent_max_ratio)
            < 1.0
        ):
            raise ValueError(
                "elastic request cache minimum guarantees must leave a positive shared pool"
            )
        self.request_region_quota_controller = None
        self.request_region_ghost = None
        if (
            self.request_regions_enabled
            and self.request_cache_region_policy == "elastic"
            and self.request_cache_elastic_ghost_capacity_tokens > 0
        ):
            self.request_region_ghost = RequestRegionGhostIndex(
                page_size=self.page_size,
                capacity_tokens=self.request_cache_elastic_ghost_capacity_tokens,
                pressure_decay=self.request_cache_elastic_ghost_pressure_decay,
            )
        if (
            self.request_regions_enabled
            and (
                self.request_cache_region_policy in ("dynamic", "borrow_dynamic")
                or (
                    self.request_cache_region_policy == "elastic"
                    and self.request_cache_elastic_feedback
                )
            )
        ):
            self.request_region_quota_controller = RequestRegionQuotaController(
                initial_ratio=self.request_agent_cache_ratio,
                alpha=params.request_cache_ratio_alpha,
                feedback_mode=params.request_cache_ratio_feedback_mode,
                min_ratio=params.request_cache_agent_min_ratio,
                max_ratio=params.request_cache_agent_max_ratio,
                feedback_min_evicted_tokens=params.request_cache_feedback_min_evicted_tokens,
                max_ratio_step=params.request_cache_ratio_max_step,
                pressure_hysteresis=params.request_cache_ratio_pressure_hysteresis,
                cooldown_evicted_tokens=params.request_cache_ratio_cooldown_evicted_tokens,
                policy_name=self.request_cache_region_policy,
            )
        self.eviction_policy = params.eviction_policy.lower()
        self.reuse_value_shadow_only = params.reuse_value_shadow_only
        self.reuse_value_turnover_kappa = float(params.reuse_value_turnover_kappa)
        self.reuse_value_base_cold_strength = float(
            params.reuse_value_base_cold_strength
        )
        if self.reuse_value_turnover_kappa <= 0:
            raise ValueError("reuse_value_turnover_kappa must be greater than zero")
        if self.reuse_value_base_cold_strength < 0:
            raise ValueError(
                "reuse_value_base_cold_strength must be greater than or equal to zero"
            )

        self.kv_event_queue = []
        self._init_kv_diagnostics()

        if params.enable_metrics:
            self.init_metrics_collector()

        if self.token_to_kv_pool_allocator:
            dev = self.token_to_kv_pool_allocator.device
            if isinstance(dev, (str, torch.device)):
                self.device = torch.device(dev)
            else:
                self.device = torch.device("cpu")
        else:
            self.device = torch.device("cpu")

        self.eviction_strategy = get_eviction_strategy(self.eviction_policy)
        active_reuse_value = bool(
            getattr(self.eviction_strategy, "uses_reuse_value", False)
        )
        if self.reuse_value_shadow_only and self.eviction_policy != "lru":
            raise ValueError("reuse_value_shadow_only requires eviction_policy='lru'")
        self.reuse_value_enabled = (
            active_reuse_value
            or params.enable_reuse_value_estimator
            or self.reuse_value_shadow_only
        )
        self.init_mlp_from_params(
            params,
            self.eviction_policy,
            bool(getattr(self.eviction_strategy, "uses_mlp", False)),
        )

        self.evictable_leaves = set()
        self.region_used_tokens: dict[str, int] = {"agent": 0, "request": 0}
        self.region_eviction_count: dict[str, int] = {"agent": 0, "request": 0}
        self.region_evicted_tokens: dict[str, int] = {"agent": 0, "request": 0}
        self.region_borrowed_tokens: dict[str, int] = {"agent": 0, "request": 0}
        self.region_preferred_borrowed_tokens: dict[str, int] = {
            "agent": 0,
            "request": 0,
        }
        self.region_borrowed_eviction_count: dict[str, int] = {
            "agent": 0,
            "request": 0,
        }
        self.region_borrowed_evicted_tokens: dict[str, int] = {
            "agent": 0,
            "request": 0,
        }
        self.region_borrow_reclaim_reason_count: dict[str, dict[str, int]] = {
            "agent": {},
            "request": {},
        }
        self.request_cache_borrow_high_watermark_tokens = int(
            getattr(params, "request_cache_borrow_high_watermark_tokens", 0)
        )
        self.request_cache_borrow_low_watermark_tokens = int(
            getattr(params, "request_cache_borrow_low_watermark_tokens", 0)
        )
        self.request_cache_borrow_lazy_reclassify = bool(
            getattr(params, "request_cache_borrow_lazy_reclassify", False)
        )
        self.request_cache_borrowed_segment_tokens = int(
            getattr(params, "request_cache_borrowed_segment_tokens", 0)
        )
        if self.request_cache_borrowed_segment_tokens < 0:
            raise ValueError(
                "request_cache_borrowed_segment_tokens must be non-negative"
            )
        if (
            self.request_cache_borrow_low_watermark_tokens < 0
            or self.request_cache_borrow_high_watermark_tokens
            < self.request_cache_borrow_low_watermark_tokens
        ):
            raise ValueError(
                "borrow watermarks must satisfy 0 <= low <= high"
            )
        self.reset()

    @classmethod
    def create_simulated(
        self,
        disable: bool = False,
        mock_allocator: Optional[Any] = None,
        page_size: int = 1,
        enable_kv_cache_events: bool = False,
        eviction_policy: str = "lru",
        enable_reuse_value_estimator: bool = False,
        reuse_value_shadow_only: bool = False,
        reuse_value_turnover_kappa: float = 1.0,
        reuse_value_base_cold_strength: float = 1.0,
        enable_request_cache_regions: bool = False,
        request_agent_cache_ratio: float = 0.5,
        request_cache_region_policy: str = "fixed",
        request_cache_ratio_window_requests: int = 0,
        request_cache_ratio_alpha: float = 0.2,
        request_cache_ratio_feedback_mode: str = "normalized_pressure",
        request_cache_ratio_max_step: float = 0.05,
        request_cache_ratio_pressure_hysteresis: float = 0.02,
        request_cache_ratio_cooldown_evicted_tokens: int = 4096,
        request_cache_agent_min_ratio: float = 0.2,
        request_cache_agent_max_ratio: float = 0.8,
        request_cache_elastic_reclaim_order: str = "request_first",
        request_cache_elastic_soft_step: float = 1.0,
        request_cache_elastic_activity_window: int = 0,
        request_cache_elastic_activity_requires_hit: bool = False,
        request_cache_elastic_ghost_capacity_tokens: int = 0,
        request_cache_elastic_ghost_pressure_decay: float = 0.95,
        request_cache_elastic_ghost_bias: float = 0.5,
        request_cache_elastic_ghost_reclaim: bool = True,
        request_cache_elastic_ghost_protect: bool = False,
        request_cache_elastic_ghost_protect_min_tokens: int = 0,
        request_cache_elastic_feedback: bool = False,
        request_cache_feedback_min_evicted_tokens: int = 0,
        request_cache_borrow_high_watermark_tokens: int = 0,
        request_cache_borrow_low_watermark_tokens: int = 0,
        request_cache_borrow_lazy_reclassify: bool = False,
        request_cache_borrowed_segment_tokens: int = 0,
    ) -> RadixCache:
        """Init a radix cache without memory pools for simulation purpose."""
        params = CacheInitParams(
            disable=disable,
            req_to_token_pool=None,
            token_to_kv_pool_allocator=mock_allocator,
            page_size=page_size,
            enable_kv_cache_events=enable_kv_cache_events,
            eviction_policy=eviction_policy,
            enable_reuse_value_estimator=enable_reuse_value_estimator,
            reuse_value_shadow_only=reuse_value_shadow_only,
            reuse_value_turnover_kappa=reuse_value_turnover_kappa,
            reuse_value_base_cold_strength=reuse_value_base_cold_strength,
            enable_request_cache_regions=enable_request_cache_regions,
            request_agent_cache_ratio=request_agent_cache_ratio,
            request_cache_region_policy=request_cache_region_policy,
            request_cache_ratio_window_requests=request_cache_ratio_window_requests,
            request_cache_ratio_alpha=request_cache_ratio_alpha,
            request_cache_ratio_feedback_mode=request_cache_ratio_feedback_mode,
            request_cache_ratio_max_step=request_cache_ratio_max_step,
            request_cache_ratio_pressure_hysteresis=request_cache_ratio_pressure_hysteresis,
            request_cache_ratio_cooldown_evicted_tokens=request_cache_ratio_cooldown_evicted_tokens,
            request_cache_agent_min_ratio=request_cache_agent_min_ratio,
            request_cache_agent_max_ratio=request_cache_agent_max_ratio,
            request_cache_elastic_reclaim_order=request_cache_elastic_reclaim_order,
            request_cache_elastic_soft_step=request_cache_elastic_soft_step,
            request_cache_elastic_activity_window=request_cache_elastic_activity_window,
            request_cache_elastic_activity_requires_hit=request_cache_elastic_activity_requires_hit,
            request_cache_elastic_ghost_capacity_tokens=request_cache_elastic_ghost_capacity_tokens,
            request_cache_elastic_ghost_pressure_decay=request_cache_elastic_ghost_pressure_decay,
            request_cache_elastic_ghost_bias=request_cache_elastic_ghost_bias,
            request_cache_elastic_ghost_reclaim=request_cache_elastic_ghost_reclaim,
            request_cache_elastic_ghost_protect=request_cache_elastic_ghost_protect,
            request_cache_elastic_ghost_protect_min_tokens=request_cache_elastic_ghost_protect_min_tokens,
            request_cache_elastic_feedback=request_cache_elastic_feedback,
            request_cache_feedback_min_evicted_tokens=request_cache_feedback_min_evicted_tokens,
            request_cache_borrow_high_watermark_tokens=request_cache_borrow_high_watermark_tokens,
            request_cache_borrow_low_watermark_tokens=request_cache_borrow_low_watermark_tokens,
            request_cache_borrow_lazy_reclassify=request_cache_borrow_lazy_reclassify,
            request_cache_borrowed_segment_tokens=request_cache_borrowed_segment_tokens,
        )
        return RadixCache(params)

    ##### Public API #####

    def reset(self):
        # Initialize root with minimum priority so any real priority overrides it
        self.root_node = TreeNode(priority=-sys.maxsize)
        self.root_node.key = RadixKey(token_ids=array("q"), extra_key=None)
        self.root_node.value = []
        self.root_node.host_value = []
        self.root_node.lock_ref = 1
        self.root_node.hash_value = []
        self.root_node.prefix_depth = 0
        self.reuse_value_inserted_tokens_total = 0
        allocator_size = getattr(self.token_to_kv_pool_allocator, "size", 1)
        if not isinstance(allocator_size, (int, float)):
            allocator_size = 1
        self.reuse_value_cache_capacity_tokens = max(1, int(allocator_size))
        self.evictable_size_ = 0
        self.protected_size_ = 0
        self.evictable_leaves.clear()
        self.region_used_tokens = {"agent": 0, "request": 0}
        self.region_eviction_count = {"agent": 0, "request": 0}
        self.region_evicted_tokens = {"agent": 0, "request": 0}
        self.region_borrowed_tokens = {"agent": 0, "request": 0}
        self.region_preferred_borrowed_tokens = {"agent": 0, "request": 0}
        self.region_borrowed_eviction_count = {"agent": 0, "request": 0}
        self.region_borrowed_evicted_tokens = {"agent": 0, "request": 0}
        self.region_borrow_reclaim_reason_count = {"agent": {}, "request": {}}
        self._elastic_last_reclassified_ratio: Optional[float] = None
        self._elastic_soft_agent_ratio_state: Optional[float] = None
        self._elastic_tail_first_regions: set[str] = set()
        self._elastic_tail_first_pressure_events = 0
        self._elastic_tail_first_activations = {"agent": 0, "request": 0}
        self._elastic_tail_first_reclaim_calls = 0
        self._elastic_tail_first_evicted_tokens = {"agent": 0, "request": 0}
        self._elastic_region_access_epoch = 0
        self._elastic_region_last_access = {"agent": -1, "request": -1}
        self._elastic_region_access_count = {"agent": 0, "request": 0}
        self._elastic_region_run_length = {"agent": 0, "request": 0}
        self._elastic_last_access_region: Optional[str] = None
        self._elastic_tail_first_activity_suppressed = 0
        # Elastic feedback is a cold-start correction, not a continuously
        # chasing controller. Once one side has gone stale, allow one update
        # from the first borrowed-eviction burst and hold the line until both
        # classes become recent again.
        self._elastic_feedback_phase_active = False
        self._elastic_feedback_phase_updated = False
        self._elastic_feedback_phase_region: Optional[str] = None
        if self.request_region_ghost is not None:
            self.request_region_ghost.reset()
        if self.request_region_quota_controller is not None:
            self.request_region_quota_controller.reset()
            self.request_agent_cache_ratio = (
                self.request_region_quota_controller.current_ratio
            )
        if getattr(self, "mlp_sessions", None) is not None:
            self.mlp_sessions.clear()
        self._empty_match_result = MatchResult(
            device_indices=torch.empty(
                (0,),
                dtype=torch.int64,
                device=self.device,
            ),
            last_device_node=self.root_node,
            last_host_node=self.root_node,
            best_match_node=self.root_node,
        )
        self._record_all_cleared_event()

    @property
    def reuse_value_global_turnover(self) -> float:
        return (
            self.reuse_value_inserted_tokens_total
            / self.reuse_value_cache_capacity_tokens
        )

    def _materialize_reuse_strength(self, node: TreeNode) -> float:
        """Apply cache-turnover aging to one node only when it is needed."""
        current_turnover = self.reuse_value_global_turnover
        delta = max(0.0, current_turnover - node.last_turnover)
        if delta and not math.isinf(self.reuse_value_turnover_kappa):
            node.reuse_strength *= math.exp(-delta / self.reuse_value_turnover_kappa)
        node.last_turnover = current_turnover
        return node.reuse_strength

    def _record_reuse(self, node: TreeNode):
        if not self.reuse_value_enabled:
            return
        self._materialize_reuse_strength(node)
        node.reuse_strength += 1.0
        node.reuse_count += 1

    def _initialize_reuse_value_node(self, node: TreeNode, parent: TreeNode):
        """Initialize a newly inserted KV node without using traffic labels."""
        parent_strength = self._materialize_reuse_strength(parent)
        if parent is not self.root_node and parent.terminal_count > 0:
            node.reuse_strength = parent_strength
        else:
            node.reuse_strength = self.reuse_value_base_cold_strength
        node.prefix_depth = parent.prefix_depth + len(node.key)

    def _record_reuse_value_insert(self, num_tokens: int):
        if self.reuse_value_enabled and num_tokens > 0:
            self.reuse_value_inserted_tokens_total += num_tokens

    def _refresh_reuse_value_density(self, node: TreeNode):
        if not self.reuse_value_enabled:
            return
        kv_size = len(node.value)
        if kv_size <= 0:
            raise RuntimeError(
                f"reuse_value eviction candidate has no KV: node_id={node.id}"
            )
        effective_strength = self._materialize_reuse_strength(node)
        # Token proxy: the marginal recompute cost is this radix segment's
        # logical token count. KV size uses the physical indices actually freed.
        recompute_tokens = len(node.key)
        node.reuse_value_density = effective_strength * recompute_tokens / kv_size

    def _get_eviction_priority(self, node: TreeNode):
        self._refresh_reuse_value_density(node)
        return self.eviction_strategy.get_priority(node)

    def _elastic_ghost_revisit_score(self, node: TreeNode) -> float:
        """Return observed recomputation pressure for one radix node."""

        if (
            not getattr(self, "request_cache_elastic_ghost_protect", False)
            or self.request_region_ghost is None
            or not self.request_region_ghost.enabled
            or node.cache_region not in self.region_used_tokens
        ):
            return 0.0
        extra_key = getattr(node.key, "extra_key", None)
        marker = getattr(node, "_elastic_ghost_extra_key", object())
        keys = getattr(node, "_elastic_ghost_prefix_keys", None)
        if keys is None or marker != extra_key:
            pages = prefix_pages_for_node(node, self.page_size)
            if not pages:
                return 0.0
            keys = rolling_prefix_keys(pages, extra_key)
            node._elastic_ghost_prefix_keys = keys
            node._elastic_ghost_extra_key = extra_key
            node._elastic_ghost_score_step = -1
        if not keys:
            return 0.0
        score_step = getattr(node, "_elastic_ghost_score_step", -1)
        if score_step == self.request_region_ghost.event_step:
            return float(getattr(node, "_elastic_ghost_score", 0.0))
        score = self.request_region_ghost.revisit_score_for_keys(
            keys,
            region=node.cache_region,
            max_age_steps=(
                self.request_cache_elastic_activity_window
                if self.request_cache_elastic_activity_window > 0
                else None
            ),
        )
        node._elastic_ghost_score_step = self.request_region_ghost.event_step
        node._elastic_ghost_score = score
        return score

    def _elastic_ghost_protect_threshold(self) -> int:
        configured = int(
            getattr(self, "request_cache_elastic_ghost_protect_min_tokens", 0)
        )
        return max(configured, self.page_size)

    def _elastic_ghost_protection_active(self, params: EvictParams) -> bool:
        """Use node-level ghost protection only on borrowed reclaim paths."""

        return bool(
            getattr(self, "request_cache_elastic_ghost_protect", False)
            and self.request_cache_region_policy == "elastic"
            and self.request_region_ghost is not None
            and self.request_region_ghost.enabled
            and (params.borrowed_only or params.preferred_borrowed_only)
        )

    def _log_reuse_value_shadow(self, leaves: list[TreeNode]):
        if not self.reuse_value_shadow_only or not leaves:
            return
        for node in leaves:
            self._refresh_reuse_value_density(node)

        lru_victim = min(leaves, key=lambda node: node.last_access_time)
        value_victim = min(
            leaves,
            key=lambda node: (node.reuse_value_density, node.last_access_time),
        )
        logger.info(
            "KV_VALUE_SHADOW turnover=%.6f candidates=%d "
            "lru_victim=%d lru_victim_value=%.6f "
            "reuse_value_victim=%d reuse_value=%.6f agree=%s",
            self.reuse_value_global_turnover,
            len(leaves),
            lru_victim.id,
            lru_victim.reuse_value_density,
            value_victim.id,
            value_victim.reuse_value_density,
            lru_victim is value_victim,
        )
        if logger.isEnabledFor(logging.DEBUG):
            for node in leaves:
                logger.debug(
                    "KV_VALUE_CANDIDATE node=%d prefix_depth=%d kv_size=%d "
                    "reuse_count=%d terminal_count=%d "
                    "effective_reuse_strength=%.6f recompute_tokens=%d "
                    "value_density=%.6f last_access_time=%.6f",
                    node.id,
                    node.prefix_depth,
                    len(node.value),
                    node.reuse_count,
                    node.terminal_count,
                    node.reuse_strength,
                    len(node.key),
                    node.reuse_value_density,
                    node.last_access_time,
                )

    def match_prefix(self, params: MatchPrefixParams) -> MatchResult:
        """Find the longest cached prefix of ``key`` in the radix tree.

        The logical namespace for prefix matching is determined by both the
        token id sequence and the optional ``extra_key`` carried by ``RadixKey``.
        Entries that share identical leading token ids but have *different*
        ``extra_key`` values are intentionally kept disjoint and never share
        prefix nodes. This is useful to:

        * Isolate KV cache lines for different LoRA / adapter IDs.
        * Separate requests that intentionally should not share state (e.g.,
          different sampling salt, cache version, or retrieval augmentation
          context) by supplying a distinct ``extra_key``.

        Args:
            params (MatchPrefixParams): Parameters containing the lookup key
                with a list of token ids and an optional ``extra_key`` namespace tag.
                If ``page_size > 1`` the length is internally truncated to a multiple
                of ``page_size`` before matching. Passing an empty key returns an
                empty result with the root as the last node.

        Returns:
            MatchResult: ``device_indices`` is a 1-D ``torch.int64`` tensor of
            the concatenated KV cache indices corresponding to the longest
            cached prefix (may be length 0).
            ``last_device_node`` and ``last_host_node`` (currently the same) are the tree node objects
            representing the terminal node of the matched prefix. This method
            may mutate internal structure by splitting an existing node if the
            match ends inside a stored segment.

        Internal updates:
            * Refreshes access metadata (timestamps) used by the
                configured eviction strategy.
            * If the lookup ends inside a stored segment the node is split once
                to expose a precise boundary; this structural refinement improves
                subsequent match efficiency and does not duplicate data.
        """
        key = params.key
        key, _ = key.maybe_to_bigram_view(self.is_eagle)

        if self.disable or len(key) == 0:
            return self._empty_match_result

        region = getattr(params.req, "cache_region", None)
        elastic_activity_region = (
            self.request_cache_region_policy == "elastic"
            and region in self._elastic_region_last_access
        )
        if elastic_activity_region:
            self._elastic_region_access_epoch += 1
            self._elastic_region_access_count[region] += 1
            if region == self._elastic_last_access_region:
                self._elastic_region_run_length[region] += 1
            else:
                self._elastic_region_run_length[region] = 1
                self._elastic_last_access_region = region

        key = key.page_aligned(self.page_size)

        if len(key) == 0:
            return self._empty_match_result

        value, last_node = self._match_prefix_helper(
            self.root_node, key, params.update_reuse_strength
        )
        if value:
            value = torch.cat(value)
        else:
            value = self._empty_match_result.device_indices
        result = MatchResult(
            device_indices=value,
            last_device_node=last_node,
            last_host_node=last_node,
            best_match_node=last_node,
        )
        if elastic_activity_region and (
            not self.request_cache_elastic_activity_requires_hit or len(value) > 0
        ):
            self._elastic_region_last_access[region] = self._elastic_region_access_epoch
        if self.request_region_ghost is not None and region in (
            "agent",
            "request",
        ):
            request_event_key = getattr(params.req, "rid", None)
            if request_event_key is None and params.req is not None:
                request_event_key = id(params.req)
            if request_event_key is not None:
                self.request_region_ghost.observe_match(
                    logical_pages(key, self.page_size),
                    extra_key=key.extra_key,
                    actual_tokens=len(value),
                    request_region=region,
                    request_event_key=request_event_key,
                )
        self._mlp_note_match(params.req, last_node)
        return result

    def insert(self, params: InsertParams) -> InsertResult:
        if self.disable:
            return InsertResult(prefix_len=0)

        key = params.key
        value = params.value
        priority = params.priority
        chunked = params.chunked
        is_terminal = params.is_terminal
        region = getattr(params.req, "cache_region", None)

        key, value = key.maybe_to_bigram_view(self.is_eagle, value)
        key = key.page_aligned(self.page_size)
        if value is not None:
            value = value[: len(key)]
        else:
            # Debug/test fallback: use token ids themselves as values.
            value = torch.tensor(key.token_ids[: len(key)], dtype=torch.int64)

        self._mlp_begin_insert(params.req)
        try:
            prefix_len = self._insert_helper(
                self.root_node, key, value, priority, chunked, is_terminal, region
            )
        finally:
            self._mlp_end_insert()
        return InsertResult(prefix_len=prefix_len)

    def cache_finished_req(self, req: Req, is_insert: bool = True):
        """Cache request when it finishes."""
        # In deterministic mode, disable finished request insertion to radix cache
        if self.disable_finished_insert:
            is_insert = False

        kv_committed_len = req.pop_committed_kv_cache()
        if self.disable:
            kv_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, :kv_committed_len
            ]
            self.token_to_kv_pool_allocator.free(kv_indices)
            return

        token_ids = (req.origin_input_ids + req.output_ids)[:kv_committed_len]
        kv_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, : len(token_ids)
        ]

        radix_key = RadixKey(
            token_ids, req.extra_key, is_bigram=self.is_eagle
        ).page_aligned(self.page_size)
        key_len = len(radix_key)
        values = kv_indices[:key_len].to(dtype=torch.int64, copy=True)

        # Radix Cache takes one ref in memory pool
        if is_insert:
            priority = getattr(req, "priority", 0) or 0
            result = self.insert(
                InsertParams(
                    key=radix_key,
                    value=values,
                    priority=priority,
                    is_terminal=True,
                    req=req,
                )
            )
            # Free the duplicates that were already in the tree
            self.token_to_kv_pool_allocator.free(
                kv_indices[req.cache_protected_len : result.prefix_len]
            )
        else:
            self.token_to_kv_pool_allocator.free(
                kv_indices[req.cache_protected_len : key_len]
            )
        self._mlp_note_finished(req)

        # free the unaligned tail
        self.token_to_kv_pool_allocator.free(kv_indices[key_len:])

        # Remove req slot release the cache lock
        if req.last_node is not None:
            self.dec_lock_ref(req.last_node)

        if self.request_regions_enabled:
            self._on_request_region_finished(getattr(req, "cache_region", None))

    def cache_unfinished_req(self, req: Req, chunked=False):
        """Cache request when it is unfinished."""
        if self.disable:
            return

        token_ids = req.get_fill_ids()
        kv_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, : len(token_ids)
        ]

        radix_key = RadixKey(
            token_ids, req.extra_key, is_bigram=self.is_eagle
        ).page_aligned(self.page_size)
        values = kv_indices[: len(radix_key)].to(dtype=torch.int64, copy=True)

        # Radix Cache takes one ref in memory pool
        result = self.insert(
            InsertParams(
                key=radix_key,
                value=values,
                chunked=chunked,
                priority=getattr(req, "priority", 0) or 0,
                req=req,
            )
        )
        new_prefix_len = result.prefix_len

        self.token_to_kv_pool_allocator.free(
            kv_indices[req.cache_protected_len : new_prefix_len]
        )

        # The prefix indices could be updated, reuse it
        match_result = self.match_prefix(
            MatchPrefixParams(key=radix_key, update_reuse_strength=False)
        )
        new_indices, new_last_node = (
            match_result.device_indices,
            match_result.last_device_node,
        )
        assert len(new_indices) == len(
            radix_key
        ), f"{len(new_indices)=}, {len(radix_key)=}"

        self.req_to_token_pool.write(
            (req.req_pool_idx, slice(req.cache_protected_len, len(new_indices))),
            new_indices[req.cache_protected_len :],
        )

        # The cache_protected_len is not always equal to len(req.prefix_indices)
        # since for page_size > 1, the partial part is added to req.prefix_indices, but that part of kv indices is not added to the tree.
        # It should be freed in the next cache_unfinished_req and final cache_finished_req to avoid memory leak.
        # So we introduce this `cache_protected_len` field to make sure the partial part can be freed correctly.
        req.cache_protected_len = len(new_indices)

        self.dec_lock_ref(req.last_node)
        self.inc_lock_ref(new_last_node)

        # `req.prefix_indices` will be used in `PrefillAdder::add_chunked_req` later
        # - page_size != 1: there is a partial page at the end, keep the full kv_indices
        # - eagle case: bigram keys will only cache len - 1 kv indices
        if len(new_indices) < len(kv_indices):
            req.prefix_indices = torch.cat(
                [new_indices, kv_indices[len(new_indices) :]]
            )
        else:
            req.prefix_indices = new_indices

        req.last_node = new_last_node

    def pretty_print(self):
        self._print_helper(self.root_node, 0)
        print(f"#tokens: {self.total_size()}")

    def total_size(self):
        return self._total_size_helper()

    def evict(self, params: EvictParams) -> EvictResult:
        if self.disable:
            return EvictResult()

        start_time = time.perf_counter()
        self._mlp_on_evict_start()
        num_tokens = params.num_tokens
        self._record_evict_start_diagnostic(num_tokens)
        leaves = list(self.evictable_leaves)
        if params.region is not None:
            leaves = [leaf for leaf in leaves if leaf.cache_region == params.region]
        if params.borrowed_only:
            leaves = [leaf for leaf in leaves if leaf.region_borrowed]
        if params.preferred_borrowed_only:
            leaves = [leaf for leaf in leaves if leaf.region_preferred_borrowed]
        self._log_reuse_value_shadow(leaves)
        if getattr(self, "mlp_enabled", False) and leaves:
            self._mlp_net_values(leaves)
        protect_ghost = self._elastic_ghost_protection_active(params)
        eviction_heap = [
            (
            1
            if protect_ghost
            and self._elastic_ghost_revisit_score(node)
            >= self._elastic_ghost_protect_threshold()
            else 0,
                self._get_eviction_priority(node),
                node,
            )
            for node in leaves
        ]
        heapq.heapify(eviction_heap)

        num_evicted = 0
        evicted_by_region: dict[str, int] = defaultdict(int)
        while num_evicted < num_tokens and len(eviction_heap):
            _ghost_rank, _priority, x = heapq.heappop(eviction_heap)

            self.token_to_kv_pool_allocator.free(x.value)
            num_evicted += len(x.value)
            if x.cache_region in self.region_evicted_tokens:
                evicted_by_region[x.cache_region] += len(x.value)
            self._record_elastic_ghost_eviction(x)
            self._delete_leaf(x)

            if (
                len(x.parent.children) == 0
                and x.parent.lock_ref == 0
                and (not params.borrowed_only or x.parent.region_borrowed)
                and (
                    not params.preferred_borrowed_only
                    or x.parent.region_preferred_borrowed
                )
            ):
                if getattr(self, "mlp_enabled", False) and not getattr(
                    self, "mlp_shadow_only", False
                ):
                    self._mlp_net_values([x.parent])
                parent_ghost_rank = (
                    1
                    if protect_ghost
                    and self._elastic_ghost_revisit_score(x.parent)
                    >= self._elastic_ghost_protect_threshold()
                    else 0
                )
                new_priority = self._get_eviction_priority(x.parent)
                heapq.heappush(
                    eviction_heap, (parent_ghost_rank, new_priority, x.parent)
                )

            self._record_remove_event(x)

        for region, region_tokens in evicted_by_region.items():
            self.region_eviction_count[region] += 1
            self.region_evicted_tokens[region] += region_tokens
            if params.borrowed_only:
                self.region_borrowed_eviction_count[region] += 1
                self.region_borrowed_evicted_tokens[region] += region_tokens
                reason = params.borrow_reclaim_reason or "unspecified"
                reasons = self.region_borrow_reclaim_reason_count[region]
                reasons[reason] = reasons.get(reason, 0) + 1
            # The hybrid controller only reacts to a loan being reclaimed.
            # Ordinary region-local LRU evictions measure working-set churn,
            # not evidence that the protected split should move.
            if self.request_region_quota_controller is not None and (
                self.request_cache_region_policy not in ("borrow_dynamic", "elastic")
                or params.borrowed_only
            ):
                self.request_region_quota_controller.observe_eviction(
                    region, region_tokens
                )

        self.update_eviction_metrics(num_evicted, start_time)
        self._mlp_on_evict_end(time.perf_counter() - start_time, full=num_evicted)
        self._record_evict_end_diagnostic(num_evicted)
        return EvictResult(num_tokens_evicted=num_evicted)

    def _reclaim_borrowed_tokens(
        self,
        region: str,
        other: str,
        target: int,
        reason: str,
    ) -> int:
        """Reclaim borrowed pages with Agent history given priority.

        Request pressure releases request-owned borrowed pages first. Agent
        pressure releases request-owned borrowed pages first as well, so an
        Agent continuation does not discard its own temporary history while
        ordinary cache is still reclaimable.
        """
        remaining = max(int(target), 0)
        reclaimed = 0
        if (
            self.request_cache_region_policy == "borrow_global"
            and reason == "global_overage"
        ):
            # The hard quotas still protect both regions.  Once the shared
            # pool is full, however, every borrowed page is an equivalent
            # reclaim candidate; selecting the oldest one globally avoids a
            # fixed request-first order that can evict a newer page while an
            # older borrowed page from the other region remains resident.
            result = self.evict(
                EvictParams(
                    num_tokens=remaining,
                    borrowed_only=True,
                    borrow_reclaim_reason=reason,
                )
            )
            return int(result.num_tokens_evicted)
        if self.request_cache_region_policy == "elastic":
            # Keep two tiers in the shared pool. Pages above the configured
            # soft split are reclaimed first; pages between the soft split
            # and the hard minimum are a lower-priority reserve. The default
            # request-first order preserves long Agent continuations. The
            # pressure-first variant keeps the opposite region's borrowed
            # pages as a return reserve during a burst.
            if self.request_cache_elastic_reclaim_order == "pressure_first":
                reclaim_order = (
                    (region, True),
                    (region, False),
                    (other, True),
                    (other, False),
                )
            else:
                reclaim_order = (
                    ("request", True),
                    ("request", False),
                    ("agent", True),
                    ("agent", False),
                )
            ghost = self.request_region_ghost
            if (
                ghost is not None
                and ghost.enabled
                and self.request_cache_elastic_ghost_reclaim
            ):
                agent_pressure = ghost.pressure["agent"]
                request_pressure = ghost.pressure["request"]
                # If the requesting region has recently paid more observed
                # recomputation, keep its pages and reclaim the opposite
                # region's borrowed tier first.  A 5% deadband prevents a
                # single page from flipping the order.
                if request_pressure > agent_pressure * 1.05:
                    reclaim_order = (
                        ("agent", True),
                        ("agent", False),
                        ("request", True),
                        ("request", False),
                    )
                elif agent_pressure > request_pressure * 1.05:
                    reclaim_order = (
                        ("request", True),
                        ("request", False),
                        ("agent", True),
                        ("agent", False),
                    )
            # A cold one-sided burst follows the baseline borrow contract;
            # once the stale class has established history, retain the soft
            # tier so alternating mixed traffic can use the shared pool.
            preferred_reclaim = self._elastic_preferred_reclaim_active()
            if preferred_reclaim:
                self._refresh_elastic_preferred_borrowed(pending_tokens=remaining)
            else:
                seen_candidates: set[str] = set()
                simple_order = []
                for candidate, _preferred in reclaim_order:
                    if candidate in ("agent", "request") and candidate not in seen_candidates:
                        seen_candidates.add(candidate)
                        simple_order.append((candidate, False))
                reclaim_order = tuple(simple_order)
        else:
            reclaim_order = (
                (region, False) if region == "request" else (other, False),
                (other, False) if region == "request" else (region, False),
            )

        for candidate, preferred_only in reclaim_order:
            if remaining <= 0:
                break
            available = (
                self.region_preferred_borrowed_tokens[candidate]
                if preferred_only
                else self.region_borrowed_tokens[candidate]
            )
            candidate_target = min(remaining, available)
            if candidate_target <= 0:
                continue
            result = self.evict(
                EvictParams(
                    num_tokens=candidate_target,
                    region=candidate,
                    borrowed_only=True,
                    preferred_borrowed_only=preferred_only,
                    borrow_reclaim_reason=reason,
                )
            )
            amount = int(result.num_tokens_evicted)
            if (
                amount > 0
                and preferred_only
                and candidate in self._elastic_tail_first_regions
            ):
                self._elastic_tail_first_reclaim_calls += 1
                self._elastic_tail_first_evicted_tokens[candidate] += amount
            reclaimed += amount
            remaining = max(remaining - amount, 0)
        return reclaimed

    def _refresh_borrow_reclassification(self) -> None:
        """Promote newly loanable pages without revoking existing loans.

        ``borrow`` labels a node only when it is inserted.  That leaves a
        stale gap after one region frees space: pages that were inserted while
        both regions were full remain protected even though the other region
        now has idle guaranteed capacity.  The reclass variant fills that gap
        at a pressure boundary. Existing loans stay loans until reclaimed, so
        a returning owner cannot make a page disappear from the reclaim set
        merely because a pending reservation has consumed the idle space.
        """
        if (
            not self.request_regions_enabled
            or (
                self.request_cache_region_policy
                not in ("borrow_dynamic", "borrow_reclass", "borrow_request_reclass")
                and not (
                    self.request_cache_borrow_lazy_reclassify
                    and self.request_cache_region_policy == "borrow"
                )
            )
        ):
            return
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return
        base_quotas = self._region_base_quotas(total_capacity)
        nodes_by_region: dict[str, list[TreeNode]] = {"agent": [], "request": []}
        stack = [self.root_node]
        while stack:
            node = stack.pop()
            if node.cache_region in nodes_by_region and not node.region_borrowed:
                nodes_by_region[node.cache_region].append(node)
            stack.extend(node.children.values())

        regions = (
            ("request",)
            if self.request_cache_region_policy == "borrow_request_reclass"
            else ("agent", "request")
        )
        for region in regions:
            other = "request" if region == "agent" else "agent"
            excess = max(self.region_used_tokens[region] - base_quotas[region], 0)
            idle = max(base_quotas[other] - self.region_used_tokens[other], 0)
            target = min(excess, idle)
            current = self.region_borrowed_tokens[region]
            needed = max(target - current, 0)
            if needed <= 0:
                continue
            nodes = nodes_by_region[region]
            # The newest segment is usually the current Agent tail. Agent
            # histories are revisited through their shared prefix, while the
            # tail has the weakest reuse evidence, so promote newest pages
            # first and keep the older chain resident.
            nodes.sort(key=lambda node: node.last_access_time, reverse=True)
            promoted = 0
            for node in nodes:
                if promoted >= needed:
                    break
                node.region_borrowed = True
                promoted += len(node.key)
                self.region_borrowed_tokens[region] += len(node.key)

    def _reclassify_borrowed_for_fallback(self) -> None:
        """Expose stale surplus pages only at the last legal reclaim tier.

        The regular ``borrow`` policy labels a newly inserted node when the
        opposite region has idle guaranteed capacity.  A later release can
        create the same idle capacity after insertion, leaving an old surplus
        node protected.  The lazy experiment promotes that surplus only when
        the allocator has already exhausted its region-scoped candidates, so
        normal LRU behavior and the common fast path remain unchanged.
        """
        if (
            self.request_cache_borrow_lazy_reclassify
            and self.request_cache_region_policy == "borrow"
        ):
            self._refresh_borrow_reclassification()

    def _region_base_quotas(self, total_capacity: int) -> dict[str, int]:
        """Return the protected quota for each request region.

        ``borrow`` uses the configured Agent split as two complementary
        guarantees.  ``elastic`` uses the lower bound of each side instead;
        the gap between those two minima is an unassigned shared pool.
        """
        if self.request_cache_region_policy == "elastic":
            # An inactive class should not lose its original return reserve
            # merely because the resident mix is temporarily dominated by the
            # other class.  When only one class has been observed recently
            # (or the cache is still cold), fall back to the configured
            # baseline split.  The elastic 20/20 floor is used only while
            # both classes are active in the online window.
            floor_ratio = self._elastic_activity_floor_ratio()
            if floor_ratio is not None:
                agent_quota = int(total_capacity * floor_ratio)
                return {
                    "agent": agent_quota,
                    "request": total_capacity - agent_quota,
                }
            return {
                "agent": int(total_capacity * self.request_cache_agent_min_ratio),
                "request": int(
                    total_capacity * (1.0 - self.request_cache_agent_max_ratio)
                ),
            }
        agent_quota = int(total_capacity * self.request_agent_cache_ratio)
        return {
            "agent": agent_quota,
            "request": total_capacity - agent_quota,
        }

    def _elastic_activity_floor_ratio(self) -> Optional[float]:
        """Return the hard quota line while one region is absent from the window.

        A stale class keeps its minimum return reserve, while the active class
        may use the rest of the shared pool.  The old implementation restored
        ``request_agent_cache_ratio`` here, which made elastic cold start
        depend on an offline traffic ratio: a one-sided Agent burst started at
        50/50 (or 61/39) even though the configured guarantees were 20/20.
        ``None`` means both classes are recent and the two minimum guarantees
        can share the pool normally.  The decision uses only observed request
        epochs; it does not inspect future phases or elapsed turn/tool time.
        """
        window = self.request_cache_elastic_activity_window
        if window <= 0:
            return None
        recent = {
            region: (
                self._elastic_region_last_access[region] >= 0
                and self._elastic_region_access_epoch
                - self._elastic_region_last_access[region]
                <= window
            )
            for region in ("agent", "request")
        }
        if recent["agent"] and recent["request"]:
            return None
        if recent["agent"] and not recent["request"]:
            return self.request_agent_cache_ratio
        if recent["request"] and not recent["agent"]:
            return self.request_agent_cache_ratio
        # Cold start has no evidence for either side.  Use the configured
        # neutral/fixed line until the first class becomes observable.
        return self.request_agent_cache_ratio

    def _elastic_preferred_reclaim_active(self) -> bool:
        """Whether the soft reclaim tier has enough history to be useful.

        A stale class with almost no observed history is a cold return
        reserve; applying the soft tier there can evict the active class's
        continuation suffix. Once the stale class has accumulated a full
        activity window, keeping the soft tier preserves mixed-traffic
        behavior. The signal uses only observed class accesses.
        """
        if not self.request_cache_elastic_preferred_reclaim:
            return False
        if self._elastic_activity_floor_ratio() is None:
            return True
        window = self.request_cache_elastic_activity_window
        if window <= 0:
            return True
        epoch = self._elastic_region_access_epoch
        stale = [
            region
            for region in ("agent", "request")
            if self._elastic_region_last_access[region] < 0
            or epoch - self._elastic_region_last_access[region] > window
        ]
        if not stale:
            return True
        counts = getattr(self, "_elastic_region_access_count", {})
        return all(int(counts.get(region, 0)) >= window for region in stale)

    def _elastic_feedback_update_allowed(self) -> bool:
        """Gate elastic quota feedback to one correction per observed phase.

        A phase transition is visible before the old activity window marks the
        opposite class stale.  If the new class has already caused borrowed
        eviction, consume that first signal at the transition boundary.  This
        avoids charging the whole cold-start burst to the old quota line while
        retaining the one-update-per-phase guard against ratio chasing.
        """
        if (
            self.request_cache_region_policy != "elastic"
            or not self.request_cache_elastic_feedback
        ):
            return True
        controller = self.request_region_quota_controller
        current_region = self._elastic_last_access_region
        pending_feedback = bool(
            controller is not None
            and sum(getattr(controller, "feedback_evicted_tokens", {}).values()) > 0
        )
        one_sided = self._elastic_activity_floor_ratio() is not None
        if not one_sided:
            if not self._elastic_feedback_phase_active:
                self._elastic_feedback_phase_active = True
                self._elastic_feedback_phase_updated = False
                self._elastic_feedback_phase_region = current_region
                return False
            if (
                current_region is not None
                and current_region != self._elastic_feedback_phase_region
            ):
                self._elastic_feedback_phase_updated = False
                self._elastic_feedback_phase_region = current_region
                # Only a transition carrying actual borrowed eviction is
                # actionable; otherwise keep the mixed phase unchanged.
                return pending_feedback
            if pending_feedback and not self._elastic_feedback_phase_updated:
                # The first request after a transition may finish before its
                # borrowed pages are reclaimed.  Keep the phase armed so the
                # next safe boundary can consume that delayed signal.
                return True
            if pending_feedback and controller is not None:
                controller.discard_pending_feedback()
            return False
        if (
            not self._elastic_feedback_phase_active
            or (
                current_region is not None
                and current_region != self._elastic_feedback_phase_region
            )
        ):
            self._elastic_feedback_phase_active = True
            self._elastic_feedback_phase_updated = False
            self._elastic_feedback_phase_region = current_region
        return not self._elastic_feedback_phase_updated

    def _elastic_target_agent_ratio(self, pending_tokens: int = 0) -> float:
        """Return the resident-mix target before optional temporal smoothing.

        The safety-band maximum is a reclaim preference, not a hard cap on a
        region that is currently using otherwise idle capacity.  When the
        cache is full and the request side is still below its minimum, the
        Agent side may temporarily consume that unused minimum.  Relaxing the
        soft line in this case avoids reclaiming a live Agent continuation
        merely to preserve an empty request reservation.  The opposite case
        is handled symmetrically for request traffic.
        """
        total_used = sum(self.region_used_tokens.values())
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_used <= 0:
            return 0.5 * (
                self.request_cache_agent_min_ratio
                + self.request_cache_agent_max_ratio
            )
        observed = self.region_used_tokens["agent"] / total_used
        lower = self.request_cache_agent_min_ratio
        upper = self.request_cache_agent_max_ratio
        # Only relax the soft bound while the physical pool is full (or
        # transiently overfull).  At low occupancy the target remains inside
        # the configured safety band, so an empty cache does not immediately
        # move the preferred tier.
        del pending_tokens
        target = min(max(observed, lower), upper)
        ghost = self.request_region_ghost
        if ghost is not None and ghost.enabled:
            # A ghost revisit is an observed recomputation loss.  Normalize by
            # each region's minimum guarantee so a larger region does not win
            # merely because it has more resident tokens.  The bias is capped
            # to keep the soft line a small correction to resident mix.
            agent_base = max(total_capacity * lower, 1.0)
            request_base = max(total_capacity * (1.0 - upper), 1.0)
            ghost_gap = (
                ghost.pressure["agent"] / agent_base
                - ghost.pressure["request"] / request_base
            )
            max_bias = min(self.request_cache_elastic_ghost_bias * 0.2, 0.2)
            target += max(-max_bias, min(ghost_gap * max_bias, max_bias))
        return min(max(target, lower), upper)

    def _record_elastic_ghost_eviction(self, node: TreeNode) -> None:
        ghost = self.request_region_ghost
        if ghost is None or node.cache_region not in self.region_used_tokens:
            return
        pages = prefix_pages_for_node(node, self.page_size)
        if not pages:
            return
        extra_key = getattr(node.key, "extra_key", None)
        ghost.record_eviction(
            pages,
            extra_key=extra_key,
            region=node.cache_region,
            evicted_tokens=len(node.key),
        )

    def _elastic_preferred_agent_ratio(self) -> float:
        """Return the soft split, optionally with bounded temporal hysteresis."""
        target = self._elastic_target_agent_ratio()
        if self.request_cache_elastic_soft_step >= 1.0:
            return target
        if self._elastic_soft_agent_ratio_state is None:
            return 0.5 * (
                self.request_cache_agent_min_ratio
                + self.request_cache_agent_max_ratio
            )
        return self._elastic_soft_agent_ratio_state

    def _refresh_elastic_preferred_borrowed(self, pending_tokens: int = 0) -> None:
        """Reclassify shared-tier pages after the resident mix changes.

        The preferred flag is an eviction tier, rather than a permanent
        ownership label. A page that was surplus at the initial split should
        stop being a preferred victim after Agent occupancy moves the soft
        split toward the Agent side.
        """
        if (
            not self.request_regions_enabled
            or self.request_cache_region_policy != "elastic"
        ):
            return

        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return
        total_used = sum(self.region_used_tokens.values())
        target_agent_ratio = self._elastic_target_agent_ratio(pending_tokens)
        if self.request_cache_elastic_soft_step >= 1.0:
            self._elastic_soft_agent_ratio_state = target_agent_ratio
        else:
            if self._elastic_soft_agent_ratio_state is None:
                self._elastic_soft_agent_ratio_state = 0.5 * (
                    self.request_cache_agent_min_ratio
                    + self.request_cache_agent_max_ratio
                )
            delta = target_agent_ratio - self._elastic_soft_agent_ratio_state
            step = self.request_cache_elastic_soft_step
            self._elastic_soft_agent_ratio_state += max(-step, min(delta, step))
        soft_agent_ratio = (
            target_agent_ratio
            if self.request_cache_elastic_soft_step >= 1.0
            else self._elastic_soft_agent_ratio_state
        )
        tail_first_regions: set[str] = set()
        if pending_tokens > 0 and total_used + pending_tokens >= total_capacity:
            request_min_tokens = total_capacity * (
                1.0 - self.request_cache_agent_max_ratio
            )
            agent_min_tokens = total_capacity * self.request_cache_agent_min_ratio
            if self.region_used_tokens["request"] < request_min_tokens:
                tail_first_regions.add("agent")
            if self.region_used_tokens["agent"] < agent_min_tokens:
                tail_first_regions.add("request")
        if pending_tokens > 0 and tail_first_regions:
            self._elastic_tail_first_pressure_events += 1
        if self.request_cache_elastic_activity_window > 0:
            stale_regions = {
                region
                for region in tail_first_regions
                if (
                    self._elastic_region_last_access[
                        "request" if region == "agent" else "agent"
                    ]
                    < 0
                    or self._elastic_region_access_epoch
                    - self._elastic_region_last_access[
                        "request" if region == "agent" else "agent"
                    ]
                    > self.request_cache_elastic_activity_window
                )
            }
            self._elastic_tail_first_activity_suppressed += len(stale_regions)
            tail_first_regions.difference_update(stale_regions)
        for region in tail_first_regions - self._elastic_tail_first_regions:
            self._elastic_tail_first_activations[region] += 1
        # Insertions and deletions already maintain the tier while the soft
        # line is stable. Rewalk the tree only after a meaningful ratio move.
        if (
            self._elastic_last_reclassified_ratio is not None
            and abs(soft_agent_ratio - self._elastic_last_reclassified_ratio)
            < 0.01
            and tail_first_regions == self._elastic_tail_first_regions
        ):
            return
        self._elastic_last_reclassified_ratio = soft_agent_ratio
        self._elastic_tail_first_regions = tail_first_regions
        soft_quotas = {
            "agent": int(total_capacity * soft_agent_ratio),
            "request": int(total_capacity * (1.0 - soft_agent_ratio)),
        }

        nodes_by_region: dict[str, list[TreeNode]] = {"agent": [], "request": []}
        stack = [self.root_node]
        while stack:
            node = stack.pop()
            if node.cache_region in nodes_by_region and node.region_borrowed:
                nodes_by_region[node.cache_region].append(node)
            stack.extend(node.children.values())

        for region, nodes in nodes_by_region.items():
            preferred_tokens = max(
                self.region_used_tokens[region] - soft_quotas[region], 0
            )
            preferred_nodes: set[TreeNode] = set()
            selected_tokens = 0
            if preferred_tokens > 0:
                if region in tail_first_regions:
                    # A burst is consuming idle capacity from the opposite
                    # region.  Reclaim its newest suffix segments first and
                    # leave older continuation history available.
                    nodes.sort(key=lambda node: node.last_access_time, reverse=True)
                else:
                    nodes.sort(key=self._get_eviction_priority)
                for node in nodes:
                    if selected_tokens >= preferred_tokens:
                        break
                    preferred_nodes.add(node)
                    selected_tokens += len(node.key)

            preferred_total = 0
            for node in nodes:
                preferred = node in preferred_nodes
                node.region_preferred_borrowed = preferred
                if preferred:
                    preferred_total += len(node.key)
            self.region_preferred_borrowed_tokens[region] = preferred_total

    def _ensure_region_capacity_single(
        self, region: Optional[str], num_tokens: int
    ) -> None:
        if not self.request_regions_enabled or region not in self.region_used_tokens:
            return
        if num_tokens < 0:
            return
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return
        if not self.request_cache_borrow_lazy_reclassify:
            self._refresh_borrow_reclassification()
        base_quotas = self._region_base_quotas(total_capacity)
        if self.request_cache_region_policy in (
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            other = "request" if region == "agent" else "agent"
            total_used = sum(self.region_used_tokens.values())
            global_overage = max(total_used + num_tokens - total_capacity, 0)
            pressure = self.region_used_tokens[region] + num_tokens - base_quotas[region]
            reclaim_target = global_overage
            reclaim_reason = None
            if (
                region == "request"
                and
                self.request_cache_borrow_high_watermark_tokens > 0
                and pressure > self.request_cache_borrow_high_watermark_tokens
            ):
                watermark_target = pressure - self.request_cache_borrow_low_watermark_tokens
                if watermark_target > reclaim_target:
                    reclaim_target = watermark_target
                    reclaim_reason = "high_watermark"
            if reclaim_target > 0 and reclaim_reason is None:
                reclaim_reason = "global_overage"
            if reclaim_target > 0:
                self._reclaim_borrowed_tokens(
                    region,
                    other,
                    reclaim_target,
                    reclaim_reason or "global_overage",
                )
                if not self.request_cache_borrow_lazy_reclassify:
                    self._refresh_borrow_reclassification()
            if self.request_cache_region_policy in (
                "borrow",
                "borrow_dynamic",
                "borrow_global",
                "borrow_reclass",
                "borrow_request_reclass",
            ):
                quota = base_quotas[region] + max(
                    base_quotas[other] - self.region_used_tokens[other], 0
                )
            else:
                # Elastic mode protects the other region's resident pages;
                # any unused portion of its minimum is immediately reusable.
                # Pages above the minimum are tagged borrowed and are the
                # first victims when the global pool fills.
                quota = total_capacity - self.region_used_tokens[other]
        else:
            quota = base_quotas[region]
        overage = self.region_used_tokens[region] + num_tokens - quota
        if overage > 0:
            self.evict(EvictParams(num_tokens=overage, region=region))

    def ensure_region_capacity(self, region: Optional[str], num_tokens: int) -> None:
        self._ensure_region_capacity_single(region, num_tokens)

    def ensure_region_capacities(self, region_tokens: dict[str, int]) -> None:
        pending = {
            region: max(int(num_tokens), 0)
            for region, num_tokens in region_tokens.items()
            if region in self.region_used_tokens and num_tokens >= 0
        }
        if not pending:
            return
        if not self.request_regions_enabled:
            return
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return
        base_quotas = self._region_base_quotas(total_capacity)
        if self.request_cache_region_policy not in (
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            for region, num_tokens in pending.items():
                self._ensure_region_capacity_single(region, num_tokens)
            return

        # A single-region reservation keeps the exact historical behavior,
        # including watermark handling. The aggregate path below is only for
        # genuinely mixed scheduling batches.
        if len(pending) == 1:
            region, num_tokens = next(iter(pending.items()))
            self._ensure_region_capacity_single(region, num_tokens)
            return

        # Project the complete batch before evicting. The old per-region loop
        # could undercount a mixed batch and leave the generic allocator to
        # evict without region ownership information.
        projected = {
            region: self.region_used_tokens[region] + pending.get(region, 0)
            for region in self.region_used_tokens
        }
        global_overage = max(sum(projected.values()) - total_capacity, 0)
        high_watermark = self.request_cache_borrow_high_watermark_tokens
        low_watermark = self.request_cache_borrow_low_watermark_tokens
        for region in pending:
            other = "request" if region == "agent" else "agent"
            reclaim_target = global_overage
            reclaim_reason = "global_overage" if reclaim_target > 0 else None
            pressure = projected[region] - base_quotas[region]
            if (
                region == "request"
                and high_watermark > 0
                and pressure > high_watermark
            ):
                watermark_target = pressure - low_watermark
                if watermark_target > reclaim_target:
                    reclaim_target = watermark_target
                    reclaim_reason = "high_watermark"
            if reclaim_target <= 0:
                continue
            before_region = self.region_used_tokens[region]
            before_other = self.region_used_tokens[other]
            reclaimed = self._reclaim_borrowed_tokens(
                region,
                other,
                reclaim_target,
                reclaim_reason or "global_overage",
            )
            projected[region] = max(
                projected[region] - (before_region - self.region_used_tokens[region]),
                0,
            )
            projected[other] = max(
                projected[other] - (before_other - self.region_used_tokens[other]),
                0,
            )
            global_overage = max(global_overage - reclaimed, 0)

        # Keep the batch path conservative: borrowed pages are the only pages
        # that can be reclaimed without changing the per-region LRU decision.
        # Any remaining physical shortage is handled by the allocator's normal
        # path; current (already occupied) quota violations still use LRU.
        for region in pending:
            self._ensure_region_capacity_single(region, 0)

    def _on_request_region_finished(self, region: Optional[str]) -> None:
        controller = self.request_region_quota_controller
        if controller is None:
            self.ensure_region_capacity(region, 0)
            return

        if not self._elastic_feedback_update_allowed():
            controller.discard_pending_feedback()
            self.ensure_region_capacity(region, 0)
            return

        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        base_quotas = self._region_base_quotas(total_capacity)
        agent_capacity = base_quotas["agent"]
        request_capacity = base_quotas["request"]
        update = controller.consume_feedback(
            agent_capacity_tokens=agent_capacity,
            request_capacity_tokens=request_capacity,
        )
        if update is None:
            self.ensure_region_capacity(region, 0)
            return

        self.request_agent_cache_ratio = update.new_ratio
        if self.request_cache_region_policy == "elastic":
            self._elastic_feedback_phase_updated = True
        evicted_before = dict(self.region_evicted_tokens)
        self.ensure_region_capacity("agent", 0)
        self.ensure_region_capacity("request", 0)
        controller.discard_pending_feedback()
        logger.info(
            "Updated dynamic request cache ratio: old=%.6f new=%.6f "
            "agent_evicted=%d request_evicted=%d agent_eviction_share=%.6f "
            "rebalanced_agent_evicted=%d rebalanced_request_evicted=%d",
            update.old_ratio,
            update.new_ratio,
            update.agent_evicted_tokens,
            update.request_evicted_tokens,
            update.agent_eviction_share,
            self.region_evicted_tokens["agent"] - evicted_before["agent"],
            self.region_evicted_tokens["request"] - evicted_before["request"],
        )

    def region_quota_stats(self) -> dict[str, object]:
        if self.request_region_quota_controller is not None:
            stats = self.request_region_quota_controller.stats()
            if self.request_cache_region_policy == "elastic":
                stats.update(
                    {
                        "elastic_feedback": self.request_cache_elastic_feedback,
                        "elastic_reclaim_order": self.request_cache_elastic_reclaim_order,
                        "elastic_preferred_reclaim": self.request_cache_elastic_preferred_reclaim,
                        "elastic_preferred_reclaim_active": self._elastic_preferred_reclaim_active(),
                        "elastic_soft_step": self.request_cache_elastic_soft_step,
                        "elastic_activity_window": self.request_cache_elastic_activity_window,
                        "elastic_activity_requires_hit": self.request_cache_elastic_activity_requires_hit,
                        "elastic_ghost_protect": self.request_cache_elastic_ghost_protect,
                        "elastic_ghost_protect_min_tokens": self.request_cache_elastic_ghost_protect_min_tokens,
                        "elastic_activity_floor_ratio": self._elastic_activity_floor_ratio(),
                        "elastic_region_access_epoch": self._elastic_region_access_epoch,
                        "elastic_region_last_access": dict(self._elastic_region_last_access),
                        "elastic_region_access_count": dict(self._elastic_region_access_count),
                        "elastic_region_run_length": dict(self._elastic_region_run_length),
                        "elastic_tail_first_activity_suppressed": self._elastic_tail_first_activity_suppressed,
                        "elastic_tail_first_regions": sorted(self._elastic_tail_first_regions),
                        "elastic_tail_first_pressure_events": self._elastic_tail_first_pressure_events,
                        "elastic_tail_first_activations": dict(self._elastic_tail_first_activations),
                        "elastic_tail_first_reclaim_calls": self._elastic_tail_first_reclaim_calls,
                        "elastic_tail_first_evicted_tokens": dict(self._elastic_tail_first_evicted_tokens),
                        "elastic_feedback_phase_active": self._elastic_feedback_phase_active,
                        "elastic_feedback_phase_updated": self._elastic_feedback_phase_updated,
                        "elastic_feedback_phase_region": self._elastic_feedback_phase_region,
                    }
                )
            return stats
        stats: dict[str, object] = {
            "policy": self.request_cache_region_policy,
            "current_agent_ratio": self.request_agent_cache_ratio,
            "elastic_feedback": self.request_cache_elastic_feedback,
            "elastic_feedback_phase_active": self._elastic_feedback_phase_active,
            "elastic_feedback_phase_updated": self._elastic_feedback_phase_updated,
            "elastic_feedback_phase_region": self._elastic_feedback_phase_region,
            "elastic_reclaim_order": self.request_cache_elastic_reclaim_order,
            "elastic_preferred_reclaim": self.request_cache_elastic_preferred_reclaim,
            "elastic_preferred_reclaim_active": self._elastic_preferred_reclaim_active(),
            "elastic_soft_step": self.request_cache_elastic_soft_step,
            "elastic_activity_window": self.request_cache_elastic_activity_window,
            "elastic_activity_requires_hit": self.request_cache_elastic_activity_requires_hit,
            "elastic_ghost_protect": self.request_cache_elastic_ghost_protect,
            "elastic_ghost_protect_min_tokens": self.request_cache_elastic_ghost_protect_min_tokens,
            "elastic_activity_floor_ratio": self._elastic_activity_floor_ratio(),
            "elastic_region_access_epoch": self._elastic_region_access_epoch,
            "elastic_region_last_access": dict(self._elastic_region_last_access),
            "elastic_region_access_count": dict(self._elastic_region_access_count),
            "elastic_region_run_length": dict(self._elastic_region_run_length),
            "elastic_tail_first_activity_suppressed": self._elastic_tail_first_activity_suppressed,
            "elastic_ghost": (
                self.request_region_ghost.stats()
                if self.request_region_ghost is not None
                else {
                    "enabled": False,
                    "capacity_tokens": self.request_cache_elastic_ghost_capacity_tokens,
                    "pressure_decay": self.request_cache_elastic_ghost_pressure_decay,
                    "bias": self.request_cache_elastic_ghost_bias,
                    "reclaim": self.request_cache_elastic_ghost_reclaim,
                    "protect": self.request_cache_elastic_ghost_protect,
                    "protect_min_tokens": self.request_cache_elastic_ghost_protect_min_tokens,
                }
            ),
            "elastic_tail_first_regions": sorted(self._elastic_tail_first_regions),
            "elastic_tail_first_pressure_events": self._elastic_tail_first_pressure_events,
            "elastic_tail_first_activations": dict(self._elastic_tail_first_activations),
            "elastic_tail_first_reclaim_calls": self._elastic_tail_first_reclaim_calls,
            "elastic_tail_first_evicted_tokens": dict(
                self._elastic_tail_first_evicted_tokens
            ),
        }
        if self.request_cache_region_policy == "elastic":
            total_used = sum(self.region_used_tokens.values())
            observed_ratio = (
                self.region_used_tokens["agent"] / total_used
                if total_used > 0
                else 0.5
                * (
                    self.request_cache_agent_min_ratio
                    + self.request_cache_agent_max_ratio
                )
            )
            stats.update(
                {
                    "agent_min_ratio": self.request_cache_agent_min_ratio,
                    "request_min_ratio": 1.0 - self.request_cache_agent_max_ratio,
                    "elastic_observed_agent_ratio": observed_ratio,
                    "elastic_target_agent_ratio": self._elastic_target_agent_ratio(),
                    "elastic_soft_agent_ratio": self._elastic_preferred_agent_ratio(),
                    "elastic_pool_ratio": max(
                        1.0
                        - self.request_cache_agent_min_ratio
                        - (1.0 - self.request_cache_agent_max_ratio),
                        0.0,
                    ),
                }
            )
        return stats

    def region_stats(self) -> dict[str, dict[str, int]]:
        """Return token usage and evictable usage for observability/tests."""
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        base_quotas = self._region_base_quotas(total_capacity)
        stats = {
            region: {
                "base_capacity_tokens": base_quotas[region],
                "capacity_tokens": base_quotas[region],
                "effective_capacity_tokens": base_quotas[region],
                "borrowed_tokens": 0,
                "used_tokens": used,
                "evictable_tokens": 0,
                "eviction_count": self.region_eviction_count[region],
                "evicted_tokens": self.region_evicted_tokens[region],
                "over_quota_tokens": max(used - base_quotas[region], 0),
            }
            for region, used in self.region_used_tokens.items()
        }
        if self.request_cache_region_policy in (
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            for region in stats:
                other = "request" if region == "agent" else "agent"
                if self.request_cache_region_policy in (
                    "borrow",
                    "borrow_dynamic",
                    "borrow_global",
                    "borrow_reclass",
                    "borrow_request_reclass",
                ):
                    borrowed = max(
                        base_quotas[other] - self.region_used_tokens[other], 0
                    )
                else:
                    borrowed = max(
                        total_capacity
                        - self.region_used_tokens[other]
                        - base_quotas[region],
                        0,
                    )
                stats[region]["borrowed_tokens"] = borrowed
                stats[region]["effective_capacity_tokens"] = (
                    base_quotas[region] + borrowed
                )
                stats[region]["capacity_tokens"] = stats[region][
                    "effective_capacity_tokens"
                ]
                stats[region]["over_quota_tokens"] = max(
                    self.region_used_tokens[region]
                    - stats[region]["effective_capacity_tokens"],
                    0,
                )
                stats[region]["cached_borrowed_tokens"] = self.region_borrowed_tokens[
                    region
                ]
                stats[region]["cached_preferred_borrowed_tokens"] = (
                    self.region_preferred_borrowed_tokens[region]
                )
                stats[region]["borrowed_eviction_count"] = (
                    self.region_borrowed_eviction_count[region]
                )
                stats[region]["borrowed_evicted_tokens"] = (
                    self.region_borrowed_evicted_tokens[region]
                )
                stats[region]["borrow_reclaim_reasons"] = dict(
                    self.region_borrow_reclaim_reason_count[region]
                )
                stats[region]["elastic_tail_first_activations"] = (
                    self._elastic_tail_first_activations[region]
                )
                stats[region]["elastic_tail_first_evicted_tokens"] = (
                    self._elastic_tail_first_evicted_tokens[region]
                )
        else:
            for region in stats:
                stats[region]["cached_borrowed_tokens"] = 0
                stats[region]["cached_preferred_borrowed_tokens"] = 0
                stats[region]["borrowed_eviction_count"] = 0
                stats[region]["borrowed_evicted_tokens"] = 0
                stats[region]["borrow_reclaim_reasons"] = {}
        for node in self.evictable_leaves:
            if node.cache_region in stats:
                stats[node.cache_region]["evictable_tokens"] += len(node.key)
        return stats

    def inc_lock_ref(self, node: TreeNode) -> IncLockRefResult:
        if self.disable:
            return IncLockRefResult(delta=0)

        delta = 0
        while node != self.root_node:
            if node.lock_ref == 0:
                self.evictable_size_ -= len(node.key)
                self.protected_size_ += len(node.key)
                delta -= len(node.key)
            node.lock_ref += 1
            self._update_leaf_status(node)
            node = node.parent
        return IncLockRefResult(delta=delta)

    def dec_lock_ref(
        self, node: TreeNode, params: Optional[DecLockRefParams] = None
    ) -> DecLockRefResult:
        if self.disable:
            return DecLockRefResult(delta=0)

        delta = 0
        while node != self.root_node:
            if node.lock_ref == 1:
                self.evictable_size_ += len(node.key)
                self.protected_size_ -= len(node.key)
                delta += len(node.key)
            node.lock_ref -= 1
            self._update_leaf_status(node)
            if node.parent is None:
                assert (
                    node is self.root_node
                ), f"This request holds the node from another tree"
            node = node.parent
        return DecLockRefResult(delta=delta)

    def evictable_size(self):
        return self.evictable_size_

    def protected_size(self):
        # protected size refers to the size of the cache that is locked
        return self.protected_size_

    def all_values_flatten(self):
        values = []

        def _dfs_helper(node: TreeNode):
            for _, child in node.children.items():
                values.append(child.value)
                _dfs_helper(child)

        _dfs_helper(self.root_node)
        return torch.cat(values)

    ##### Internal Helper Functions #####

    def _match_prefix_helper(
        self, node: TreeNode, key: RadixKey, update_reuse_strength: bool = True
    ):
        access_time = time.monotonic()
        node.last_access_time = access_time

        child_key = key.child_key(self.page_size)

        value = []
        while len(key) > 0 and child_key in node.children.keys():
            child = node.children[child_key]
            child.last_access_time = access_time
            prefix_len = child.key.match(key, page_size=self.page_size)
            if prefix_len < len(child.key):
                new_node = self._split_node(child.key, child, prefix_len)
                value.append(new_node.value)
                node = new_node
                if update_reuse_strength:
                    self._record_reuse(new_node)
                break
            else:
                value.append(child.value)
                node = child
                if update_reuse_strength:
                    self._record_reuse(child)
                key = key[prefix_len:]

                if len(key):
                    child_key = key.child_key(self.page_size)

        return value, node

    def _split_node(self, key: RadixKey, child: TreeNode, split_len: int):
        # new_node -> child
        # New node inherits child's priority (represents shared prefix)
        new_node = TreeNode(priority=child.priority)
        new_node.hit_count = child.hit_count
        new_node.reuse_strength = child.reuse_strength
        new_node.last_turnover = child.last_turnover
        new_node.reuse_count = child.reuse_count
        new_node.children = {key[split_len:].child_key(self.page_size): child}
        new_node.parent = child.parent
        new_node.lock_ref = child.lock_ref
        new_node.key = child.key[:split_len]
        new_node.value = child.value[:split_len].clone()
        new_node.prefix_depth = new_node.parent.prefix_depth + split_len
        copy_mlp_on_split(new_node, child)
        # The original request endpoint remains at the end of ``child``.
        # A structural split must not copy terminal evidence to the prefix.
        new_node.terminal_count = 0
        new_node.cache_region = child.cache_region
        new_node.region_borrowed = child.region_borrowed
        new_node.region_preferred_borrowed = child.region_preferred_borrowed
        child.parent = new_node
        child.key = child.key[split_len:]
        child.value = child.value[split_len:].clone()
        # A ghost score is keyed by the complete parent-chain prefix.  A
        # structural split changes that chain and the logical prefix owned by
        # both nodes, so any cached fingerprints/score must be rebuilt before
        # the next borrowed reclaim.  Keeping the old values would allow a
        # revisit of the pre-split node to protect an unrelated suffix.
        for split_node in (new_node, child):
            split_node.__dict__.pop("_elastic_ghost_prefix_keys", None)
            split_node.__dict__.pop("_elastic_ghost_extra_key", None)
            split_node.__dict__.pop("_elastic_ghost_score_step", None)
            split_node.__dict__.pop("_elastic_ghost_score", None)
        new_node.parent.children[key.child_key(self.page_size)] = new_node

        # Split hash_value if it was already computed, otherwise leave as None
        new_node.hash_value, child.hash_value = split_node_hash_value(
            child.hash_value, split_len, self.page_size
        )

        return new_node

    def _inc_hit_count(self, node: TreeNode, chunked: bool = False):
        # Skip the hit count update for chunked requests to avoid self-referencing
        # inflation where a chunked request increments hit_count on nodes it created
        # in previous chunks.
        if chunked:
            return
        node.hit_count += 1

    def _dec_hit_count(self, node: TreeNode, chunked: bool = False, delta: int = 1):
        if chunked or delta <= 0:
            return
        node.hit_count -= delta

    def _request_cache_insert_segment_len(
        self, key_len: int, region: Optional[str]
    ) -> int:
        """Choose a bounded suffix segment when a region can borrow capacity.

        Radix insertion historically stores the complete unmatched suffix in
        one leaf.  That is efficient for lookup, but a borrowed reclaim of a
        few pages then removes the complete suffix.  The experimental bound is
        applied only when the suffix crosses the region's protected line.  A
        prefix that still fits below that line remains one node; only the
        crossing/borrowed tail is segmented.
        """
        if key_len <= 0 or region not in self.region_used_tokens:
            return key_len
        if self.request_cache_region_policy not in (
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            return key_len
        configured = self.request_cache_borrowed_segment_tokens
        if configured <= 0:
            return key_len
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return key_len
        base = self._region_base_quotas(total_capacity)[region]
        used = self.region_used_tokens[region]
        if used + key_len <= base:
            return key_len
        page = max(int(self.page_size), 1)
        granularity = max((configured // page) * page, page)
        below_base = max(base - used, 0)
        aligned_below_base = (below_base // page) * page
        if aligned_below_base > 0:
            return min(key_len, aligned_below_base)
        return min(key_len, granularity)

    def _demote_on_miss(self) -> bool:
        return bool(getattr(self.eviction_strategy, "demote_on_miss", False))

    def _insert_helper(
        self,
        node: TreeNode,
        key: RadixKey,
        value,
        priority: int = 0,
        chunked: bool = False,
        is_terminal: bool = False,
        region: Optional[str] = None,
    ):
        # Convert None priority to 0
        if priority is None:
            priority = 0
        access_time = time.monotonic()
        node.last_access_time = access_time
        # Update priority along the path (take max to propagate higher priority)
        node.priority = max(node.priority, priority)
        if len(key) == 0:
            return 0

        child_key = key.child_key(self.page_size)

        total_prefix_length = 0
        matched_nodes: list[TreeNode] = []
        while len(key) > 0 and child_key in node.children.keys():
            node = node.children[child_key]
            node.last_access_time = access_time
            prefix_len = node.key.match(key, page_size=self.page_size)
            total_prefix_length += prefix_len
            key = key[prefix_len:]
            value = value[prefix_len:]

            if prefix_len < len(node.key):
                new_node = self._split_node(node.key, node, prefix_len)
                new_node.priority = max(new_node.priority, priority)
                self._inc_hit_count(new_node, chunked)
                node = new_node
            else:
                node.priority = max(node.priority, priority)
                self._inc_hit_count(node, chunked)
            matched_nodes.append(node)
            if len(key):
                child_key = key.child_key(self.page_size)

        if len(key):
            # agentic: relative to LFU, demote matched path by 1 when a miss
            # suffix exists; cold miss leaf starts at -1 instead of +1.
            if self._demote_on_miss() and not chunked:
                for matched in matched_nodes:
                    self._dec_hit_count(matched, chunked=False, delta=1)
            while len(key):
                segment_len = self._request_cache_insert_segment_len(len(key), region)
                borrowed = False
                preferred_borrowed = False
                if self.request_regions_enabled and region in self.region_used_tokens:
                    total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
                    base_quotas = self._region_base_quotas(total_capacity)
                    other = "request" if region == "agent" else "agent"
                    over_base = (
                        self.region_used_tokens[region] + segment_len
                        > base_quotas[region]
                    )
                    # A cache page may straddle the guarantee boundary. Keep
                    # that page reclaimable as elastic/borrowed instead of
                    # losing the excess just because insertion started below
                    # the boundary.  Classic borrow additionally requires the
                    # other region to have unused guaranteed capacity; elastic
                    # mode owns an explicit shared pool, so it does not.
                    if self.request_cache_region_policy == "elastic":
                        borrowed = over_base
                        preferred_ratio = self._elastic_preferred_agent_ratio()
                        preferred_quota = int(
                            total_capacity
                            * (
                                preferred_ratio
                                if region == "agent"
                                else 1.0 - preferred_ratio
                            )
                        )
                        preferred_borrowed = (
                            self.region_used_tokens[region] + segment_len
                            > preferred_quota
                        )
                    else:
                        borrowed = over_base and (
                            self.request_cache_region_policy
                            in (
                                "borrow",
                                "borrow_dynamic",
                                "borrow_global",
                                "borrow_reclass",
                                "borrow_request_reclass",
                            )
                            and self.region_used_tokens[other] < base_quotas[other]
                        )
                segment_key = key[:segment_len]
                segment_value = value[:segment_len]
                new_node = TreeNode(priority=priority)
                new_node.parent = node
                new_node.key = segment_key
                new_node.value = segment_value.clone()
                new_node.prefix_depth = node.prefix_depth + segment_len
                new_node.cache_region = region
                new_node.region_borrowed = borrowed
                new_node.region_preferred_borrowed = preferred_borrowed
                self._mlp_stamp_new_node(new_node)
                if self.reuse_value_enabled:
                    self._initialize_reuse_value_node(new_node, node)
                    self._record_reuse_value_insert(segment_len)
                    new_node.last_turnover = self.reuse_value_global_turnover
                if self._demote_on_miss() and not chunked:
                    new_node.hit_count = -1
                else:
                    self._inc_hit_count(new_node, chunked)
                node.children[segment_key.child_key(self.page_size)] = new_node
                node = new_node
                self.evictable_size_ += segment_len
                if self.request_regions_enabled and region in self.region_used_tokens:
                    self.region_used_tokens[region] += segment_len
                    if borrowed:
                        self.region_borrowed_tokens[region] += segment_len
                    if preferred_borrowed:
                        self.region_preferred_borrowed_tokens[region] += segment_len
                self._update_leaf_status(new_node.parent)
                self._update_leaf_status(new_node)
                self._record_store_event(new_node)
                key = key[segment_len:]
                value = value[segment_len:]
                if len(key):
                    child_key = key.child_key(self.page_size)
        if is_terminal and self.reuse_value_enabled:
            node.terminal_count += 1
        return total_prefix_length

    def _print_helper(self, node: TreeNode, indent: int):
        """Prints the radix tree in a human-readable format."""
        stack = [(node, indent)]
        while stack:
            current_node, current_indent = stack.pop()
            print(
                " " * current_indent,
                len(current_node.key),
                current_node.key.token_ids[:10],
                f"r={current_node.lock_ref}",
            )
            for key, child in current_node.children.items():
                stack.append((child, current_indent + 2))

                assert key == child.key.child_key(
                    self.page_size
                ), f"{key=}, {child.key.child_key(self.page_size)=}"

    def _delete_leaf(self, node):
        key = node.key.child_key(self.page_size)
        v = node.parent.children.pop(key, None)
        assert v == node, f"parent does not have child key, {key}"

        self.evictable_size_ -= len(node.key)
        if self.request_regions_enabled and node.cache_region in self.region_used_tokens:
            self.region_used_tokens[node.cache_region] -= len(node.key)
            if node.region_borrowed:
                self.region_borrowed_tokens[node.cache_region] -= len(node.key)
            if node.region_preferred_borrowed:
                self.region_preferred_borrowed_tokens[node.cache_region] -= len(
                    node.key
                )
        if node in self.evictable_leaves:
            self.evictable_leaves.remove(node)
        self._update_leaf_status(node.parent)

    def _update_leaf_status(self, node: TreeNode):
        if node.evicted or node.lock_ref > 0:
            if node in self.evictable_leaves:
                self.evictable_leaves.remove(node)
            return

        for child in node.children.values():
            if not child.evicted:
                if node in self.evictable_leaves:
                    self.evictable_leaves.remove(node)
                return

        if node not in self.evictable_leaves:
            self.evictable_leaves.add(node)

    def _total_size_helper(self):
        total_size = 0
        stack = [self.root_node]
        while stack:
            current_node = stack.pop()
            total_size += len(current_node.value)
            for child in current_node.children.values():
                if child.evicted:
                    continue
                stack.append(child)
        return total_size


if __name__ == "__main__":
    tree = RadixCache.create_simulated()

    tree.insert(InsertParams(key=RadixKey(token_ids=array("q", [1, 2, 3]))))
    tree.insert(InsertParams(key=RadixKey(token_ids=array("q", [1, 2, 3]))))
    tree.insert(InsertParams(key=RadixKey(token_ids=array("q", [1, 2, 4, 5]))))
    tree.insert(InsertParams(key=RadixKey(token_ids=array("q", [1, 2, 4, 5, 6, 7]))))
    tree.insert(InsertParams(key=RadixKey(token_ids=array("q", [8, 9, 10, 11, 12]))))
    tree.pretty_print()

    print(
        tree.match_prefix(
            MatchPrefixParams(key=RadixKey(token_ids=array("q", [1, 2, 3, 13, 14])))
        )
    )
