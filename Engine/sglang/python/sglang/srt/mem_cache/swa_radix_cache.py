from __future__ import annotations

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
The radix tree data structure for managing the hybrid (full and SWA) KV cache.
"""

import heapq
import time
from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional, Tuple

import torch
from numpy import float64

from sglang.srt.environ import envs
from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
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
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.events import KVCacheEventMixin
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.mlp_reuse import (
    MlpReuseMixin,
    copy_mlp_on_split,
    init_mlp_fields,
)
from sglang.srt.mem_cache.reuse_value import (
    ReuseValueMixin,
    copy_reuse_value_on_split,
    init_reuse_value_fields,
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

import logging

logger = logging.getLogger(__name__)


class TreeNode:

    counter = 0
    swa_uuid_counter = 1
    last_access_time_counter_float = float64(1.0)

    def __init__(self, id: Optional[int] = None):
        self.children = defaultdict(TreeNode)
        self.parent: TreeNode = None
        self.key: RadixKey = None
        self.value: Optional[torch.Tensor] = None
        # swa_tombstone is used to indicate the kv indices have been freed for swa layers
        self.swa_tombstone = False
        # invariant: for any node, if swa_lock_ref is locked, full_lock_ref must be locked;
        # if full_lock_ref is locked, swa_lock_ref doesn't need to be locked. So,
        # full_lock_ref is always >= swa_lock_ref.
        self.full_lock_ref = 0
        self.swa_lock_ref = 0
        # last access time is only used for sanity check. LRU is maintained by the lru list.
        self.last_access_time = get_last_access_time()

        self.hit_count = 0
        init_reuse_value_fields(self)
        init_mlp_fields(self)
        # store the host indices of KV cache
        self.host_value = None
        # store hash values of each page
        self.hash_value: Optional[List[str]] = None

        # for lru list, invariant:
        # 1. prev has greater last_access_time
        # 2. next has smaller last_access_time
        self.prev = None
        self.next = None
        self.swa_prev = None
        self.swa_next = None

        self.id = TreeNode.counter if id is None else id
        TreeNode.counter += 1
        self.swa_uuid = None
        self.cache_region: Optional[str] = None
        self.full_borrowed = False
        self.swa_borrowed = False
        self.full_preferred_borrowed = False
        self.swa_preferred_borrowed = False

    @property
    def evicted(self):
        return self.value is None

    @property
    def backuped(self):
        return self.host_value is not None

    def __lt__(self, other: "TreeNode"):
        return self.last_access_time < other.last_access_time


def gen_swa_uuid() -> int:
    TreeNode.swa_uuid_counter += 1
    return TreeNode.swa_uuid_counter


def get_last_access_time() -> float64:
    ret = TreeNode.last_access_time_counter_float
    TreeNode.last_access_time_counter_float += 1.0
    return ret


class LRUList:
    def __init__(self, is_swa_list: bool = False):
        self.is_swa_list = is_swa_list
        if self.is_swa_list:
            self.prv = "swa_prev"
            self.nxt = "swa_next"
            self.lock_ref = "swa_lock_ref"
        else:
            self.prv = "prev"
            self.nxt = "next"
            self.lock_ref = "full_lock_ref"
        # Initialize dummy head and tail nodes
        self.head = TreeNode()  # Most recently used side
        self.tail = TreeNode()  # Least recently used side
        setattr(self.head, self.nxt, self.tail)  # self.head.next = self.tail
        setattr(self.tail, self.prv, self.head)  # self.tail.prev = self.head
        self.cache = {}

    def _add_node(self, node):
        """Helper to add node right after head (most recently used)"""
        self._add_node_after(self.head, node)

    def _add_node_after(self, old_node, new_node):
        """Helper to add node right after old_node"""
        setattr(new_node, self.prv, old_node)  # new_node.prev = old_node
        setattr(
            new_node, self.nxt, getattr(old_node, self.nxt)
        )  # new_node.next = old_node.next
        setattr(
            getattr(old_node, self.nxt), self.prv, new_node
        )  # old_node.next.prev = new_node
        setattr(old_node, self.nxt, new_node)  # old_node.next = new_node

    def _remove_node(self, node):
        """Helper to remove node from linked list"""
        setattr(
            getattr(node, self.prv), self.nxt, getattr(node, self.nxt)
        )  # node.prev.next = node.next
        setattr(
            getattr(node, self.nxt), self.prv, getattr(node, self.prv)
        )  # node.next.prev = node.prev
        # Clear self pointers to break reference cycles among evicted nodes.
        setattr(node, self.prv, None)
        setattr(node, self.nxt, None)

    def _get_lru(self) -> Optional[TreeNode]:
        """
        Get the least recently used node
        """
        if len(self.cache) == 0:
            return None
        return getattr(self.tail, self.prv)

    def reset_node_mru(self, node):
        """
        Move a (existing) node to most recently used position
        """
        assert node.id in self.cache, f"Resetting node {node.id=} not in lru list"
        assert (
            not self.is_swa_list or not node.swa_tombstone
        ), f"Resetting swa tombstone node in swa lru list: {node.id=}"
        self._remove_node(node)
        self._add_node(node)

    def reset_node_and_parents_mru(self, node, root_node):
        """
        Move an (existing) node and its parents to most recently used position. Child node is
        more recently used than parent node.
        """
        prev_node = self.head
        while node != root_node:
            # for swa lru list, only reset non-tombstone nodes
            if not self.is_swa_list or not node.swa_tombstone:
                assert (
                    node.id in self.cache
                ), f"Resetting node {node.id=} not in lru list when resetting node and parents mru"
                self._remove_node(node)
                self._add_node_after(prev_node, node)
                prev_node = node
            node = node.parent

    def insert_mru(self, node):
        """
        Insert a (new) node as most recently used
        """
        assert (
            not self.is_swa_list or not node.swa_tombstone
        ), f"Inserting swa tombstone node in swa lru list: {node.id=}"
        assert (
            node.id not in self.cache
        ), f"Inserting node {node.id=} already in lru list, existing node: {self.cache[node.id].id=}"
        self.cache[node.id] = node
        self._add_node(node)

    def remove_node(self, node: TreeNode):
        """
        Remove node from lru list
        """
        assert node.id in self.cache, f"Removing node {node.id=} not in lru list"
        assert (
            not self.is_swa_list or not node.swa_tombstone
        ), f"Removing swa tombstone node from swa lru list: {node.id=}"
        del self.cache[node.id]
        self._remove_node(node)

    def get_lru_no_lock(self) -> Optional[TreeNode]:
        """
        Get the least recently used node that is not locked
        """
        return self.get_prev_no_lock(self.tail, check_id=False)

    def get_leaf_lru_no_lock(self) -> Optional[TreeNode]:
        """
        Get the least recently used leaf node that is not locked
        """
        return self.get_prev_leaf_no_lock(self.tail, check_id=False)

    def get_prev_no_lock(
        self, node: TreeNode, check_id: bool = True
    ) -> Optional[TreeNode]:
        """
        Get the previous (i.e. more recently used) node that is not locked
        """
        if check_id:
            assert (
                node.id in self.cache
            ), f"Getting prev of node {node.id=} not in lru list"
        x = getattr(node, self.prv)  # x = node.prev
        while getattr(x, self.lock_ref) > 0:
            x = getattr(x, self.prv)  # x = x.prev
        # if x is the head, it means there is no node in the lru list without lock
        if x == self.head:
            return None
        return x

    def get_prev_leaf_no_lock(self, node: TreeNode, check_id: bool = True):
        """
        Get the previous (i.e. more recently used) leaf node that is not locked
        """
        if check_id:
            assert (
                node.id in self.cache
            ), f"Getting prev of node {node.id=} not in lru list"
        x = getattr(node, self.prv)  # x = node.prev
        while getattr(x, self.lock_ref) > 0 or len(x.children) > 0:
            x = getattr(x, self.prv)  # x = x.prev
        # if x is the head, it means there is no leaf node in the lru list without lock
        if x == self.head:
            return None
        return x

    def in_list(self, node: Optional[TreeNode]):
        """
        Check if the node is in the lru list
        """
        if not node:
            return False
        return node.id in self.cache

    # Note: this is expensive, only use for debug
    def sanity_check_evictable_size(self):
        """
        Check the evictable size (i.e. the size of the nodes that are not locked)
        """
        node = self.get_lru_no_lock()
        evictable_size = 0
        while self.in_list(node):
            evictable_size += len(node.value)
            node = self.get_prev_no_lock(node)
        return evictable_size

    # Note: this is expensive, only use for debug or idle check
    def sanity_check(self, tree_cache: "SWARadixCache"):
        """
        Check if the lru list is valid by rebuilding the lru list from the tree, heapifying it, and
        checking if the lru list is valid.
        """
        try:
            if self.is_swa_list:
                nodes = tree_cache._collect_nontombstone_nodes()
            else:
                nodes = tree_cache._collect_all_nodes()
            total_nodes = len(nodes)
            total_lru_plus_1 = len(self.cache) + 1
            # heapify based on last_access_time
            heapq.heapify(nodes)
            # the root node is not in the lru list
            assert (
                len(nodes) == len(self.cache) + 1
            ), f"len(nodes): {len(nodes)} != len(self.cache) + 1: {len(self.cache) + 1}"

            x_lru = self._get_lru()
            while len(nodes):
                x = heapq.heappop(nodes)
                if x == tree_cache.root_node:
                    # root node is not in the lru list
                    continue
                assert (
                    x == x_lru
                ), f"Incorrect LRU list, {self.is_swa_list=}, x: {x.id=} != x_lru: {x_lru.id=}"
                assert (
                    x_lru.full_lock_ref == 0
                ), f"x_lru should not be locked when idle, {x_lru.full_lock_ref=}, {x_lru.swa_uuid=}, {x_lru.id=}"
                assert (
                    x_lru.swa_lock_ref == 0
                ), f"x_lru should not be locked when idle, {x_lru.swa_lock_ref=}, {x_lru.swa_uuid=}, {x_lru.id=}"
                x_lru = getattr(x, self.prv)

            if self.is_swa_list:
                evictable_size = tree_cache.swa_evictable_size()
                lru_list_evictable_size = self.sanity_check_evictable_size()
            else:
                evictable_size = tree_cache.full_evictable_size()
                lru_list_evictable_size = self.sanity_check_evictable_size()

            assert (
                evictable_size == lru_list_evictable_size
            ), f"{self.is_swa_list=}, total nodes: {total_nodes}, total lru plus 1: {total_lru_plus_1}, evictable size: {evictable_size} != lru list evictable size: {lru_list_evictable_size}"
        except Exception as e:
            msg = f"SWA Radix tree sanity check failed, ping @hanming-lu: {e}"
            logger.error(msg)
            raise Exception(msg)


class SWARadixCache(MlpReuseMixin, ReuseValueMixin, KVCacheEventMixin, BasePrefixCache):
    def __init__(self, params: CacheInitParams):
        assert isinstance(params.token_to_kv_pool_allocator, SWATokenToKVPoolAllocator)
        self.req_to_token_pool = params.req_to_token_pool
        self.token_to_kv_pool_allocator = params.token_to_kv_pool_allocator
        self.page_size = params.page_size
        self.disable = params.disable
        self.is_eagle = params.is_eagle
        self.enable_kv_cache_events = params.enable_kv_cache_events
        self.kv_event_queue = []
        self.eviction_policy = params.eviction_policy.lower()
        self.eviction_strategy = get_eviction_strategy(self.eviction_policy)
        self.init_reuse_value_from_params(
            params,
            self.eviction_policy,
            bool(getattr(self.eviction_strategy, "uses_reuse_value", False)),
        )
        self.init_mlp_from_params(
            params,
            self.eviction_policy,
            bool(getattr(self.eviction_strategy, "uses_mlp", False)),
        )

        if self.token_to_kv_pool_allocator:
            self.device = self.token_to_kv_pool_allocator.device
        else:
            self.device = torch.device("cpu")

        if params.enable_metrics:
            self.init_metrics_collector()

        self.sliding_window_size = params.sliding_window_size
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
            raise ValueError("borrow watermarks must satisfy 0 <= low <= high")
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
        self.reset()

    ##### Public API #####

    def supports_swa(self) -> bool:
        assert (
            self.sliding_window_size is not None
        ), "sliding_window_size must be set for SWARadixCache"
        return True

    def reset(self) -> None:
        self.root_node = TreeNode()
        self.root_node.key = []
        self.root_node.value = []
        self.root_node.hash_value = []
        self.root_node.full_lock_ref = 1
        self.root_node.swa_lock_ref = 1
        self.root_node.prefix_depth = 0
        self.reset_reuse_value_counters()
        if getattr(self, "mlp_sessions", None) is not None:
            self.mlp_sessions.clear()
        self.full_evictable_size_ = 0
        self.swa_evictable_size_ = 0
        self.full_protected_size_ = 0
        self.swa_protected_size_ = 0
        self.region_full_used_tokens = {"agent": 0, "request": 0}
        self.region_swa_used_tokens = {"agent": 0, "request": 0}
        self.region_eviction_count = {"agent": 0, "request": 0}
        self.region_full_evicted_tokens = {"agent": 0, "request": 0}
        self.region_swa_evicted_tokens = {"agent": 0, "request": 0}
        self.region_full_borrowed_tokens = {"agent": 0, "request": 0}
        self.region_swa_borrowed_tokens = {"agent": 0, "request": 0}
        if self.request_region_ghost is not None:
            self.request_region_ghost.reset()
        self.region_full_preferred_borrowed_tokens = {"agent": 0, "request": 0}
        self.region_swa_preferred_borrowed_tokens = {"agent": 0, "request": 0}
        self.region_borrowed_eviction_count = {"agent": 0, "request": 0}
        self.region_borrowed_full_evicted_tokens = {"agent": 0, "request": 0}
        self.region_borrowed_swa_evicted_tokens = {"agent": 0, "request": 0}
        self.region_borrow_reclaim_reason_count = {"agent": {}, "request": {}}
        self._elastic_last_reclassified_ratio: Optional[float] = None
        self._elastic_soft_agent_ratio_state: Optional[float] = None
        self._elastic_tail_first_regions: set[str] = set()
        self._elastic_tail_first_pressure_events = 0
        self._elastic_tail_first_activations = {"agent": 0, "request": 0}
        self._elastic_tail_first_reclaim_calls = 0
        self._elastic_tail_first_evicted_full_tokens = {"agent": 0, "request": 0}
        self._elastic_tail_first_evicted_swa_tokens = {"agent": 0, "request": 0}
        self._elastic_region_access_epoch = 0
        self._elastic_region_last_access = {"agent": -1, "request": -1}
        self._elastic_region_access_count = {"agent": 0, "request": 0}
        self._elastic_region_run_length = {"agent": 0, "request": 0}
        self._elastic_last_access_region: Optional[str] = None
        self._elastic_tail_first_activity_suppressed = 0
        # Elastic feedback is a cold-start correction, not a continuously
        # chasing controller. Allow one update per one-sided phase and hold
        # the line until both classes become recent again.
        self._elastic_feedback_phase_active = False
        self._elastic_feedback_phase_updated = False
        self._elastic_feedback_phase_region: Optional[str] = None
        if self.request_region_quota_controller is not None:
            self.request_region_quota_controller.reset()
            self.request_agent_cache_ratio = (
                self.request_region_quota_controller.current_ratio
            )
        # LRU lists are used to maintain the order of eviction of the nodes in the tree
        self.full_lru_list = LRUList(is_swa_list=False)
        self.swa_lru_list = LRUList(is_swa_list=True)
        self._record_all_cleared_event()

    def match_prefix(self, params: MatchPrefixParams) -> MatchResult:
        """Find the matching prefix from the radix tree.
        Args:
            params: MatchPrefixParams containing key.
        Returns:
            A tuple of a tensor of matching prefix token IDs and
            the last node that contains the prefix values. Note that
            this API can modify the internal state of the Radix tree.
            The last node create a new child if the prefix is shorter
            than the last node's value.
        """

        key = self._match_pre_processor(params)
        if key is None:
            return MatchResult(
                device_indices=torch.empty(
                    (0,),
                    dtype=torch.int64,
                    device=self.device,
                ),
                last_device_node=self.root_node,
                last_host_node=self.root_node,
                best_match_node=self.root_node,
            )

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

        value, last_node, best_value_len = self._match_prefix_helper(
            key, params.update_reuse_strength
        )
        result = self._match_post_processor(params, value, last_node, best_value_len)
        if elastic_activity_region and (
            not self.request_cache_elastic_activity_requires_hit
            or len(value) > 0
            or int(getattr(result, "host_hit_length", 0)) > 0
            or int(getattr(result, "swa_host_hit_length", 0)) > 0
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
                    actual_tokens=len(result.device_indices),
                    request_region=region,
                    request_event_key=request_event_key,
                )
        self._mlp_note_match(params.req, result.last_device_node)
        return result

    def insert(self, params: InsertParams) -> InsertResult:
        if self.disable:
            return InsertResult(prefix_len=0)

        key = params.key
        value = params.value
        prev_prefix_len = params.prev_prefix_len
        swa_evicted_seqlen = params.swa_evicted_seqlen
        region = getattr(params.req, "cache_region", None)

        key, value = key.maybe_to_bigram_view(self.is_eagle, value)
        key = key.page_aligned(self.page_size)
        if value is not None:
            value = value[: len(key)]
        else:
            value = torch.tensor(key.token_ids[: len(key)], dtype=torch.int64)

        self._mlp_begin_insert(params.req)
        try:
            prefix_len = self._insert_helper(
                self.root_node,
                key,
                value,
                prev_prefix_len,
                swa_evicted_seqlen,
                params.is_terminal,
                region,
            )
        finally:
            self._mlp_end_insert()
        return InsertResult(prefix_len=prefix_len)

    def cache_finished_req(self, req: Req, is_insert: bool = True) -> None:
        """Cache request when it finishes."""
        kv_committed_len = req.pop_committed_kv_cache()
        if self.disable:
            kv_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, :kv_committed_len
            ]
            self.token_to_kv_pool_allocator.free(kv_indices)
            return

        token_ids = (req.origin_input_ids + req.output_ids)[:kv_committed_len]
        kv_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, :kv_committed_len
        ]

        radix_key = RadixKey(
            token_ids, req.extra_key, is_bigram=self.is_eagle
        ).page_aligned(self.page_size)
        page_aligned_len = len(radix_key)
        values = kv_indices[:page_aligned_len].to(dtype=torch.int64, copy=True)
        old_prefix_len = req.cache_protected_len

        # Radix Cache takes one ref in memory pool
        # Note: the insert function already frees the overlapped kv_indices
        if is_insert:
            self.insert(
                InsertParams(
                    key=radix_key,
                    value=values,
                    prev_prefix_len=old_prefix_len,
                    swa_evicted_seqlen=req.swa_evicted_seqlen,
                    is_terminal=True,
                    req=req,
                )
            )
        else:
            self.token_to_kv_pool_allocator.free(
                kv_indices[old_prefix_len:page_aligned_len]
            )
        self._mlp_note_finished(req)

        # free the unaligned tail
        self.token_to_kv_pool_allocator.free(kv_indices[page_aligned_len:])

        # Remove req slot release the cache lock
        self.dec_lock_ref(
            req.last_node,
            DecLockRefParams(swa_uuid_for_lock=req.swa_uuid_for_lock),
            skip_swa=req.swa_prefix_lock_released,
        )
        req.swa_prefix_lock_released = False
        if self.request_regions_enabled:
            self._on_request_region_finished(getattr(req, "cache_region", None))

    def cache_unfinished_req(self, req: Req, chunked=False) -> None:
        """Cache request when it is unfinished."""
        if self.disable:
            kv_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, : req.fill_len
            ]

            # `req.prefix_indices` will be used in `PrefillAdder::add_chunked_req` later
            req.prefix_indices = kv_indices
            return

        token_ids = req.get_fill_ids()
        kv_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, : len(token_ids)
        ]

        radix_key = RadixKey(
            token_ids, req.extra_key, is_bigram=self.is_eagle
        ).page_aligned(self.page_size)
        values = kv_indices[: len(radix_key)].to(dtype=torch.int64, copy=True)
        old_prefix_len = req.cache_protected_len

        # Radix Cache takes one ref in memory pool
        # Note: the insert function already frees the overlapped kv_indices
        result = self.insert(
            InsertParams(
                key=radix_key,
                value=values,
                prev_prefix_len=old_prefix_len,
                req=req,
            )
        )
        new_prefix_len = result.prefix_len

        # The prefix indices could be updated, reuse it
        match_result = self.match_prefix(
            MatchPrefixParams(key=radix_key, update_reuse_strength=False)
        )
        new_indices, new_last_node = (
            match_result.device_indices,
            match_result.last_device_node,
        )

        assert old_prefix_len <= len(new_indices), f"{old_prefix_len=}, {new_indices=}"
        assert new_prefix_len <= len(new_indices), f"{new_prefix_len=}, {new_indices=}"
        self.req_to_token_pool.write(
            (req.req_pool_idx, slice(old_prefix_len, len(new_indices))),
            new_indices[old_prefix_len:],
        )

        req.cache_protected_len = len(new_indices)

        self.dec_lock_ref(
            req.last_node,
            DecLockRefParams(swa_uuid_for_lock=req.swa_uuid_for_lock),
            skip_swa=req.swa_prefix_lock_released,
        )
        req.swa_prefix_lock_released = False
        result = self.inc_lock_ref(new_last_node)
        swa_uuid_for_lock = result.swa_uuid_for_lock

        # `req.prefix_indices` will be used in `PrefillAdder::add_chunked_req` later
        if len(new_indices) < len(kv_indices):
            req.prefix_indices = torch.cat(
                [new_indices, kv_indices[len(new_indices) :]]
            )
        else:
            req.prefix_indices = new_indices
        req.last_node = new_last_node
        req.swa_uuid_for_lock = swa_uuid_for_lock

    def pretty_print(self) -> None:
        self._print_helper(self.root_node, 0)
        total_size, total_swa_size = self._total_size_helper()
        print(f"#full_tokens: {total_size}, #swa_tokens: {total_swa_size}")

    def total_size(self) -> Tuple[int, int]:
        return self._total_size_helper()

    def evict(self, params: EvictParams) -> EvictResult:
        if self.disable:
            return EvictResult()
        start_time = time.perf_counter()
        self._mlp_on_evict_start()
        full_num_tokens = params.num_tokens
        swa_num_tokens = params.swa_num_tokens
        full_num_evicted = 0
        swa_num_evicted = 0
        evicted_by_region = defaultdict(lambda: [0, 0])
        if full_num_tokens > 0:
            # MLP: rescore remaining full leaves after each victim (same as the
            # 0.246 long-window run). One-shot heap does not match that ranking.
            x = self._select_full_leaf_victim(
                params.region,
                borrowed_only=params.borrowed_only,
                preferred_borrowed_only=params.preferred_borrowed_only,
            )
            while full_num_evicted < full_num_tokens and self.full_lru_list.in_list(
                x
            ):
                region = x.cache_region
                d_full, d_swa, _ = self._evict_one_full_unlocked_leaf(
                    x,
                    borrowed_only=params.borrowed_only,
                    preferred_borrowed_only=params.preferred_borrowed_only,
                )
                full_num_evicted += d_full
                swa_num_evicted += d_swa
                if region in self.region_full_used_tokens:
                    evicted_by_region[region][0] += d_full
                    evicted_by_region[region][1] += d_swa
                x = self._select_full_leaf_victim(
                    params.region,
                    borrowed_only=params.borrowed_only,
                    preferred_borrowed_only=params.preferred_borrowed_only,
                )

        if swa_num_evicted < swa_num_tokens:
            x = self._select_swa_victim(
                params.region,
                borrowed_only=params.borrowed_only,
                preferred_borrowed_only=params.preferred_borrowed_only,
            )
            while swa_num_evicted < swa_num_tokens and self.swa_lru_list.in_list(x):
                region = x.cache_region
                d_full, d_swa = self._evict_one_swa_unlocked_node(
                    x,
                    borrowed_only=params.borrowed_only,
                    preferred_borrowed_only=params.preferred_borrowed_only,
                )
                full_num_evicted += d_full
                swa_num_evicted += d_swa
                if region in self.region_full_used_tokens:
                    evicted_by_region[region][0] += d_full
                    evicted_by_region[region][1] += d_swa
                x = self._select_swa_victim(
                    params.region,
                    borrowed_only=params.borrowed_only,
                    preferred_borrowed_only=params.preferred_borrowed_only,
                )

        for region, (full_evicted, swa_evicted) in evicted_by_region.items():
            if full_evicted or swa_evicted:
                self.region_eviction_count[region] += 1
                self.region_full_evicted_tokens[region] += full_evicted
                self.region_swa_evicted_tokens[region] += swa_evicted
                if params.borrowed_only:
                    self.region_borrowed_eviction_count[region] += 1
                    self.region_borrowed_full_evicted_tokens[region] += full_evicted
                    self.region_borrowed_swa_evicted_tokens[region] += swa_evicted
                    reason = params.borrow_reclaim_reason or "unspecified"
                    reasons = self.region_borrow_reclaim_reason_count[region]
                    reasons[reason] = reasons.get(reason, 0) + 1
                # The hybrid controller only reacts to a loan being reclaimed.
                # Ordinary region-local LRU evictions measure working-set
                # churn, not evidence that the protected split should move.
                if self.request_region_quota_controller is not None and (
                    self.request_cache_region_policy not in ("borrow_dynamic", "elastic")
                    or params.borrowed_only
                ):
                    # A hybrid eviction can release the same prefix from both
                    # pools. Count it once using the larger pool contribution.
                    self.request_region_quota_controller.observe_eviction(
                        region, max(full_evicted, swa_evicted)
                    )

        self.update_eviction_metrics(full_num_evicted + swa_num_evicted, start_time)
        self._mlp_on_evict_end(
            time.perf_counter() - start_time,
            full=full_num_evicted,
            swa=swa_num_evicted,
        )
        return EvictResult(
            num_tokens_evicted=full_num_evicted, swa_num_tokens_evicted=swa_num_evicted
        )

    def _reclaim_borrowed_tokens(
        self,
        region: str,
        other: str,
        full_target: int,
        swa_target: int,
        reason: str,
    ) -> tuple[int, int]:
        """Reclaim borrowed pages while preserving Agent history when possible.

        Request pressure releases request-owned borrowed pages first. Agent
        pressure also releases request-owned borrowed pages first, and only
        falls back to Agent-owned borrowed pages when the other side is short.
        Full and SWA use the same region order and differ only in accounting.
        """
        remaining_full = max(int(full_target), 0)
        remaining_swa = max(int(swa_target), 0)
        reclaimed_full = 0
        reclaimed_swa = 0

        if (
            self.request_cache_region_policy == "borrow_global"
            and reason == "global_overage"
        ):
            # The hard quotas still protect both regions. Once the shared
            # pool is full, select the oldest eligible borrowed pages across
            # both regions instead of imposing a fixed request-first order.
            result = self.evict(
                EvictParams(
                    num_tokens=remaining_full,
                    swa_num_tokens=remaining_swa,
                    borrowed_only=True,
                    borrow_reclaim_reason=reason,
                )
            )
            return int(result.num_tokens_evicted), int(result.swa_num_tokens_evicted)

        if self.request_cache_region_policy == "elastic":
            # Use one region order for Full and SWA. Pages above the soft
            # split are reclaimed first, followed by the lower shared-minimum
            # tier. The default request-first order preserves Agent
            # continuations; pressure-first preserves the opposite region's
            # return reserve during a burst.
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
                self._refresh_elastic_preferred_borrowed(
                    full_pending=remaining_full,
                    swa_pending=remaining_swa,
                )
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
            if remaining_full <= 0 and remaining_swa <= 0:
                break
            if preferred_only:
                available_full = self.region_full_preferred_borrowed_tokens[
                    candidate
                ]
                available_swa = self.region_swa_preferred_borrowed_tokens[
                    candidate
                ]
            else:
                available_full = self.region_full_borrowed_tokens[candidate]
                available_swa = self.region_swa_borrowed_tokens[candidate]
            candidate_full = min(remaining_full, available_full)
            candidate_swa = min(remaining_swa, available_swa)
            if candidate_full <= 0 and candidate_swa <= 0:
                continue
            result = self.evict(
                EvictParams(
                    num_tokens=candidate_full,
                    swa_num_tokens=candidate_swa,
                    region=candidate,
                    borrowed_only=True,
                    preferred_borrowed_only=preferred_only,
                    borrow_reclaim_reason=reason,
                )
            )
            if (
                (result.num_tokens_evicted > 0 or result.swa_num_tokens_evicted > 0)
                and preferred_only
                and candidate in self._elastic_tail_first_regions
            ):
                self._elastic_tail_first_reclaim_calls += 1
                self._elastic_tail_first_evicted_full_tokens[candidate] += int(
                    result.num_tokens_evicted
                )
                self._elastic_tail_first_evicted_swa_tokens[candidate] += int(
                    result.swa_num_tokens_evicted
                )
            reclaimed_full += int(result.num_tokens_evicted)
            reclaimed_swa += int(result.swa_num_tokens_evicted)
            remaining_full = max(remaining_full - int(result.num_tokens_evicted), 0)
            remaining_swa = max(
                remaining_swa - int(result.swa_num_tokens_evicted), 0
            )
        return reclaimed_full, reclaimed_swa

    def _region_base_quotas(
        self, full_capacity: int, swa_capacity: int
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Return protected Full and SWA quotas for both request regions."""
        if self.request_cache_region_policy == "elastic":
            # Keep the configured baseline split while one class is absent
            # from the recent online activity window. The elastic minimums
            # are reserved for periods in which both classes are active, so
            # an inactive class retains a usable return reserve in both pools.
            floor_ratio = self._elastic_activity_floor_ratio()
            if floor_ratio is not None:
                full_agent = int(full_capacity * floor_ratio)
                swa_agent = int(swa_capacity * floor_ratio)
                return (
                    {
                        "agent": full_agent,
                        "request": full_capacity - full_agent,
                    },
                    {
                        "agent": swa_agent,
                        "request": swa_capacity - swa_agent,
                    },
                )
            return (
                {
                    "agent": int(full_capacity * self.request_cache_agent_min_ratio),
                    "request": int(
                        full_capacity * (1.0 - self.request_cache_agent_max_ratio)
                    ),
                },
                {
                    "agent": int(swa_capacity * self.request_cache_agent_min_ratio),
                    "request": int(
                        swa_capacity * (1.0 - self.request_cache_agent_max_ratio)
                    ),
                },
            )
        agent_full_capacity = int(full_capacity * self.request_agent_cache_ratio)
        agent_swa_capacity = int(swa_capacity * self.request_agent_cache_ratio)
        return (
            {
                "agent": agent_full_capacity,
                "request": full_capacity - agent_full_capacity,
            },
            {
                "agent": agent_swa_capacity,
                "request": swa_capacity - agent_swa_capacity,
            },
        )

    def _elastic_activity_floor_ratio(self) -> Optional[float]:
        """Return the hard quota line while one region is absent from the window.

        A stale class keeps its minimum return reserve, while the active class
        may use the rest of the shared pool.  This avoids making elastic cold
        start depend on an offline traffic ratio while retaining the history
        gate that suppresses tail-first reclaim for a class with little
        observed history.
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
        return self.request_agent_cache_ratio

    def _elastic_preferred_reclaim_active(self) -> bool:
        """Enable soft reclaim once a stale class has enough history."""
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

    def _elastic_target_agent_ratio(
        self, full_pending: int = 0, swa_pending: int = 0
    ) -> float:
        """Return the shared resident-mix target before temporal smoothing.

        The configured safety band describes the minimum protected service
        guarantees.  It should not force an active region to give back idle
        capacity while the other region has not reached its own minimum.  At
        physical pressure, relax the soft bound to the actually resident
        opposite side; this keeps Full and SWA on one decision while allowing
        a burst to use unused capacity.
        """
        if not self.request_regions_enabled:
            return self.request_agent_cache_ratio
        full_agent = self.region_full_used_tokens["agent"]
        full_request = self.region_full_used_tokens["request"]
        swa_agent = self.region_swa_used_tokens["agent"]
        swa_request = self.region_swa_used_tokens["request"]
        total_used = full_agent + full_request + swa_agent + swa_request
        if total_used <= 0:
            return 0.5 * (
                self.request_cache_agent_min_ratio
                + self.request_cache_agent_max_ratio
            )
        observed = (full_agent + swa_agent) / total_used
        lower = self.request_cache_agent_min_ratio
        upper = self.request_cache_agent_max_ratio
        del full_pending, swa_pending
        target = min(max(observed, lower), upper)
        ghost = self.request_region_ghost
        if ghost is not None and ghost.enabled:
            full_capacity = float(self.token_to_kv_pool_allocator.size_full)
            swa_capacity = float(self.token_to_kv_pool_allocator.size_swa)
            agent_base = max((full_capacity + swa_capacity) * lower, 1.0)
            request_base = max((full_capacity + swa_capacity) * (1.0 - upper), 1.0)
            ghost_gap = (
                ghost.pressure["agent"] / agent_base
                - ghost.pressure["request"] / request_base
            )
            max_bias = min(self.request_cache_elastic_ghost_bias * 0.2, 0.2)
            target += max(-max_bias, min(ghost_gap * max_bias, max_bias))
        return min(max(target, lower), upper)

    def _record_elastic_ghost_eviction(self, node: TreeNode) -> None:
        ghost = self.request_region_ghost
        if ghost is None or node.cache_region not in self.region_full_used_tokens:
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
        """Return one Full/SWA soft split with optional bounded hysteresis."""
        target = self._elastic_target_agent_ratio()
        if self.request_cache_elastic_soft_step >= 1.0:
            return target
        if self._elastic_soft_agent_ratio_state is None:
            return 0.5 * (
                self.request_cache_agent_min_ratio
                + self.request_cache_agent_max_ratio
            )
        return self._elastic_soft_agent_ratio_state

    def _refresh_elastic_preferred_borrowed(
        self, *, full_pending: int = 0, swa_pending: int = 0
    ) -> None:
        """Reclassify Full and SWA shared-tier pages using one soft split.

        Preferred status is a reclaim tier and must follow the current
        resident mix. Otherwise pages created while the initial split was
        61/39 remain preferred victims after a later Agent burst moves the
        soft split toward 80/20. Full and SWA are reclassified independently,
        but both use the same ratio.
        """
        if (
            not self.request_regions_enabled
            or self.request_cache_region_policy != "elastic"
        ):
            return

        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        full_agent = self.region_full_used_tokens["agent"]
        full_request = self.region_full_used_tokens["request"]
        swa_agent = self.region_swa_used_tokens["agent"]
        swa_request = self.region_swa_used_tokens["request"]
        target_agent_ratio = self._elastic_target_agent_ratio(
            full_pending=full_pending,
            swa_pending=swa_pending,
        )
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
        for pool_used, pool_pending, pool_capacity, pool_agent, pool_request in (
            (
                full_agent + full_request,
                max(int(full_pending), 0),
                full_capacity,
                full_agent,
                full_request,
            ),
            (
                swa_agent + swa_request,
                max(int(swa_pending), 0),
                swa_capacity,
                swa_agent,
                swa_request,
            ),
        ):
            if pool_capacity <= 0 or pool_used + pool_pending < pool_capacity:
                continue
            request_min_tokens = pool_capacity * (
                1.0 - self.request_cache_agent_max_ratio
            )
            agent_min_tokens = pool_capacity * self.request_cache_agent_min_ratio
            if pool_request < request_min_tokens:
                tail_first_regions.add("agent")
            if pool_agent < agent_min_tokens:
                tail_first_regions.add("request")
        if (full_pending > 0 or swa_pending > 0) and tail_first_regions:
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
            "full": {
                "agent": int(full_capacity * soft_agent_ratio),
                "request": int(full_capacity * (1.0 - soft_agent_ratio)),
            },
            "swa": {
                "agent": int(swa_capacity * soft_agent_ratio),
                "request": int(swa_capacity * (1.0 - soft_agent_ratio)),
            },
        }

        all_nodes = self._collect_all_nodes()
        for pool, used, borrowed_attr, preferred_attr, counters in (
            (
                "full",
                self.region_full_used_tokens,
                "full_borrowed",
                "full_preferred_borrowed",
                self.region_full_preferred_borrowed_tokens,
            ),
            (
                "swa",
                self.region_swa_used_tokens,
                "swa_borrowed",
                "swa_preferred_borrowed",
                self.region_swa_preferred_borrowed_tokens,
            ),
        ):
            for region in ("agent", "request"):
                candidates = [
                    node
                    for node in all_nodes
                    if node.cache_region == region
                    and getattr(node, borrowed_attr)
                    and (pool != "swa" or not node.swa_tombstone)
                ]
                preferred_tokens = max(
                    used[region] - soft_quotas[pool][region], 0
                )
                if region in tail_first_regions:
                    candidates.sort(key=lambda node: node.last_access_time, reverse=True)
                else:
                    candidates.sort(key=lambda node: node.last_access_time)
                selected_tokens = 0
                preferred_nodes: set[TreeNode] = set()
                for node in candidates:
                    if selected_tokens >= preferred_tokens:
                        break
                    preferred_nodes.add(node)
                    selected_tokens += len(node.key)
                preferred_total = 0
                for node in candidates:
                    preferred = node in preferred_nodes
                    setattr(node, preferred_attr, preferred)
                    if preferred:
                        preferred_total += len(node.key)
                counters[region] = preferred_total

    def _refresh_borrow_reclassification(self) -> None:
        """Promote newly loanable Full/SWA pages at a pressure boundary.

        Nodes are tagged at insertion in the classic policy. If the other
        region later frees guaranteed space, that insertion-time decision can
        leave reclaimable capacity stranded behind protected labels. This
        variant only adds loans; existing loans remain reclaimable until the
        owner actually takes the space back.
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
        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        base_full_quotas, base_swa_quotas = self._region_base_quotas(
            full_capacity, swa_capacity
        )
        all_nodes = self._collect_all_nodes()
        for pool, used, base_quotas, borrowed_attr, counters in (
            (
                "full",
                self.region_full_used_tokens,
                base_full_quotas,
                "full_borrowed",
                self.region_full_borrowed_tokens,
            ),
            (
                "swa",
                self.region_swa_used_tokens,
                base_swa_quotas,
                "swa_borrowed",
                self.region_swa_borrowed_tokens,
            ),
        ):
            regions = (
                ("request",)
                if self.request_cache_region_policy == "borrow_request_reclass"
                else ("agent", "request")
            )
            for region in regions:
                other = "request" if region == "agent" else "agent"
                excess = max(used[region] - base_quotas[region], 0)
                idle = max(base_quotas[other] - used[other], 0)
                target = min(excess, idle)
                needed = max(target - counters[region], 0)
                if needed <= 0:
                    continue
                candidates = [
                    node
                    for node in all_nodes
                    if node.cache_region == region
                    and not getattr(node, borrowed_attr)
                    and (pool != "swa" or not node.swa_tombstone)
                ]
                # Prefer newly appended tail segments for promotion. The
                # shared history has stronger reuse evidence than a fresh
                # Agent tail, so keeping the older chain protects continuation
                # hits while still exposing surplus capacity to reclaim.
                candidates.sort(key=lambda node: node.last_access_time, reverse=True)
                promoted = 0
                for node in candidates:
                    if promoted >= needed:
                        break
                    setattr(node, borrowed_attr, True)
                    promoted += len(node.key)
                    counters[region] += len(node.key)

    def _reclassify_borrowed_for_fallback(self) -> None:
        """Promote stale surplus pages only when fallback reclaim is needed."""
        if (
            self.request_cache_borrow_lazy_reclassify
            and self.request_cache_region_policy == "borrow"
        ):
            self._refresh_borrow_reclassification()

    def _ensure_region_capacity_single(
        self, region: Optional[str], num_tokens: int
    ) -> None:
        if not self.request_regions_enabled or region not in self.region_full_used_tokens:
            return
        if num_tokens < 0:
            return
        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        if not self.request_cache_borrow_lazy_reclassify:
            self._refresh_borrow_reclassification()
        base_full_quotas, base_swa_quotas = self._region_base_quotas(
            full_capacity, swa_capacity
        )
        other = "request" if region == "agent" else "agent"
        if self.request_cache_region_policy in (
            "borrow",
            "borrow_dynamic",
            "borrow_global",
            "borrow_reclass",
            "borrow_request_reclass",
            "elastic",
        ):
            full_global_overage = max(
                sum(self.region_full_used_tokens.values()) + num_tokens - full_capacity,
                0,
            )
            full_pressure = (
                self.region_full_used_tokens[region] + num_tokens
                - base_full_quotas[region]
            )
            full_reclaim_target = full_global_overage
            full_reclaim_reason = None
            if (
                region == "request"
                and
                self.request_cache_borrow_high_watermark_tokens > 0
                and full_pressure > self.request_cache_borrow_high_watermark_tokens
            ):
                full_watermark_target = (
                    full_pressure - self.request_cache_borrow_low_watermark_tokens
                )
                if full_watermark_target > full_reclaim_target:
                    full_reclaim_target = full_watermark_target
                    full_reclaim_reason = "high_watermark"
            if full_reclaim_target > 0 and full_reclaim_reason is None:
                full_reclaim_reason = "global_overage"
            swa_global_overage = max(
                sum(self.region_swa_used_tokens.values()) + num_tokens - swa_capacity,
                0,
            )
            swa_pressure = (
                self.region_swa_used_tokens[region] + num_tokens
                - base_swa_quotas[region]
            )
            swa_reclaim_target = swa_global_overage
            swa_reclaim_reason = None
            if (
                region == "request"
                and
                self.request_cache_borrow_high_watermark_tokens > 0
                and swa_pressure > self.request_cache_borrow_high_watermark_tokens
            ):
                swa_watermark_target = (
                    swa_pressure - self.request_cache_borrow_low_watermark_tokens
                )
                if swa_watermark_target > swa_reclaim_target:
                    swa_reclaim_target = swa_watermark_target
                    swa_reclaim_reason = "high_watermark"
            if swa_reclaim_target > 0 and swa_reclaim_reason is None:
                swa_reclaim_reason = "global_overage"
            reclaim_reason = (
                "high_watermark"
                if full_reclaim_reason == "high_watermark"
                or swa_reclaim_reason == "high_watermark"
                else "global_overage"
            )
            if full_reclaim_target > 0 or swa_reclaim_target > 0:
                self._reclaim_borrowed_tokens(
                    region,
                    other,
                    full_reclaim_target,
                    swa_reclaim_target,
                    reclaim_reason,
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
                full_quota = base_full_quotas[region] + max(
                    base_full_quotas[other] - self.region_full_used_tokens[other], 0
                )
                swa_quota = base_swa_quotas[region] + max(
                    base_swa_quotas[other] - self.region_swa_used_tokens[other], 0
                )
            else:
                # Protect the other region's resident pages; unused portions
                # of its minimum are immediately reusable. Pages above the
                # minimum are tagged borrowed and reclaimed first.
                full_quota = full_capacity - self.region_full_used_tokens[other]
                swa_quota = swa_capacity - self.region_swa_used_tokens[other]
        else:
            full_quota = base_full_quotas[region]
            swa_quota = base_swa_quotas[region]
        full_overage = self.region_full_used_tokens[region] + num_tokens - full_quota
        swa_overage = self.region_swa_used_tokens[region] + num_tokens - swa_quota
        if full_overage > 0 or swa_overage > 0:
            self.evict(
                EvictParams(
                    num_tokens=max(full_overage, 0),
                    swa_num_tokens=max(swa_overage, 0),
                    region=region,
                )
            )

    def ensure_region_capacity(self, region: Optional[str], num_tokens: int) -> None:
        self._ensure_region_capacity_single(region, num_tokens)

    def ensure_region_capacities(self, region_tokens: dict[str, int]) -> None:
        pending = {
            region: max(int(num_tokens), 0)
            for region, num_tokens in region_tokens.items()
            if region in self.region_full_used_tokens and num_tokens >= 0
        }
        if not pending:
            return
        if not self.request_regions_enabled:
            return
        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        base_full_quotas, base_swa_quotas = self._region_base_quotas(
            full_capacity, swa_capacity
        )
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

        if len(pending) == 1:
            region, num_tokens = next(iter(pending.items()))
            self._ensure_region_capacity_single(region, num_tokens)
            return

        # Project all allocations in the batch before selecting victims. This
        # keeps Full and SWA ownership aligned when both request classes are in
        # the same scheduling batch.
        projected_full = {
            region: self.region_full_used_tokens[region] + pending.get(region, 0)
            for region in self.region_full_used_tokens
        }
        projected_swa = {
            region: self.region_swa_used_tokens[region] + pending.get(region, 0)
            for region in self.region_swa_used_tokens
        }
        full_global_overage = max(sum(projected_full.values()) - full_capacity, 0)
        swa_global_overage = max(sum(projected_swa.values()) - swa_capacity, 0)
        high_watermark = self.request_cache_borrow_high_watermark_tokens
        low_watermark = self.request_cache_borrow_low_watermark_tokens
        for region in pending:
            other = "request" if region == "agent" else "agent"
            full_target = full_global_overage
            swa_target = swa_global_overage
            full_reason = "global_overage" if full_target > 0 else None
            swa_reason = "global_overage" if swa_target > 0 else None
            full_pressure = projected_full[region] - base_full_quotas[region]
            swa_pressure = projected_swa[region] - base_swa_quotas[region]
            if (
                region == "request"
                and high_watermark > 0
                and full_pressure > high_watermark
            ):
                target = full_pressure - low_watermark
                if target > full_target:
                    full_target = target
                    full_reason = "high_watermark"
            if (
                region == "request"
                and high_watermark > 0
                and swa_pressure > high_watermark
            ):
                target = swa_pressure - low_watermark
                if target > swa_target:
                    swa_target = target
                    swa_reason = "high_watermark"
            reclaim_reason = (
                "high_watermark"
                if full_reason == "high_watermark"
                or swa_reason == "high_watermark"
                else "global_overage"
            )
            if full_target <= 0 and swa_target <= 0:
                continue
            before_full = {
                current: self.region_full_used_tokens[current]
                for current in self.region_full_used_tokens
            }
            before_swa = {
                current: self.region_swa_used_tokens[current]
                for current in self.region_swa_used_tokens
            }
            reclaimed_full, reclaimed_swa = self._reclaim_borrowed_tokens(
                region,
                other,
                full_target,
                swa_target,
                reclaim_reason,
            )
            for current in projected_full:
                reclaimed = before_full[current] - self.region_full_used_tokens[current]
                projected_full[current] = max(projected_full[current] - reclaimed, 0)
            for current in projected_swa:
                reclaimed = before_swa[current] - self.region_swa_used_tokens[current]
                projected_swa[current] = max(projected_swa[current] - reclaimed, 0)
            full_global_overage = max(full_global_overage - reclaimed_full, 0)
            swa_global_overage = max(swa_global_overage - reclaimed_swa, 0)

        # Reclaiming borrowed pages is safe to do with projected batch usage.
        # Keep the remaining per-region victim choice on the normal LRU path.
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

        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        base_full_quotas, base_swa_quotas = self._region_base_quotas(
            full_capacity, swa_capacity
        )
        # Hybrid eviction feedback counts the larger Full/SWA contribution
        # once, so normalize against the corresponding larger quota.
        agent_capacity = max(
            base_full_quotas["agent"], base_swa_quotas["agent"]
        )
        request_capacity = max(
            base_full_quotas["request"],
            base_swa_quotas["request"],
        )
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
        full_evicted_before = dict(self.region_full_evicted_tokens)
        swa_evicted_before = dict(self.region_swa_evicted_tokens)
        self.ensure_region_capacity("agent", 0)
        self.ensure_region_capacity("request", 0)
        controller.discard_pending_feedback()
        logger.info(
            "Updated dynamic request cache ratio: old=%.6f new=%.6f "
            "agent_evicted=%d request_evicted=%d agent_eviction_share=%.6f "
            "agent_full_evicted=%d request_full_evicted=%d "
            "agent_swa_evicted=%d request_swa_evicted=%d",
            update.old_ratio,
            update.new_ratio,
            update.agent_evicted_tokens,
            update.request_evicted_tokens,
            update.agent_eviction_share,
            self.region_full_evicted_tokens["agent"] - full_evicted_before["agent"],
            self.region_full_evicted_tokens["request"]
            - full_evicted_before["request"],
            self.region_swa_evicted_tokens["agent"] - swa_evicted_before["agent"],
            self.region_swa_evicted_tokens["request"]
            - swa_evicted_before["request"],
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
                        "elastic_tail_first_evicted_full_tokens": dict(self._elastic_tail_first_evicted_full_tokens),
                        "elastic_tail_first_evicted_swa_tokens": dict(self._elastic_tail_first_evicted_swa_tokens),
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
            "elastic_tail_first_evicted_full_tokens": dict(
                self._elastic_tail_first_evicted_full_tokens
            ),
            "elastic_tail_first_evicted_swa_tokens": dict(
                self._elastic_tail_first_evicted_swa_tokens
            ),
        }
        if self.request_cache_region_policy == "elastic":
            total_used = sum(self.region_full_used_tokens.values()) + sum(
                self.region_swa_used_tokens.values()
            )
            observed_ratio = (
                (
                    self.region_full_used_tokens["agent"]
                    + self.region_swa_used_tokens["agent"]
                )
                / total_used
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
        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        base_full_quotas, base_swa_quotas = self._region_base_quotas(
            full_capacity, swa_capacity
        )
        stats = {}
        for region in self.region_full_used_tokens:
            other = "request" if region == "agent" else "agent"
            full_borrowed = 0
            swa_borrowed = 0
            if self.request_cache_region_policy in (
                "borrow",
                "borrow_dynamic",
                "borrow_global",
                "borrow_reclass",
                "borrow_request_reclass",
            ):
                full_borrowed = max(
                    base_full_quotas[other] - self.region_full_used_tokens[other], 0
                )
                swa_borrowed = max(
                    base_swa_quotas[other] - self.region_swa_used_tokens[other], 0
                )
            elif self.request_cache_region_policy == "elastic":
                full_borrowed = max(
                    full_capacity
                    - self.region_full_used_tokens[other]
                    - base_full_quotas[region],
                    0,
                )
                swa_borrowed = max(
                    swa_capacity
                    - self.region_swa_used_tokens[other]
                    - base_swa_quotas[region],
                    0,
                )
            stats[region] = {
                "base_full_capacity_tokens": base_full_quotas[region],
                "base_swa_capacity_tokens": base_swa_quotas[region],
                "full_capacity_tokens": (
                    base_full_quotas[region] + full_borrowed
                ),
                "swa_capacity_tokens": (
                    base_swa_quotas[region] + swa_borrowed
                ),
                "full_borrowed_tokens": full_borrowed,
                "swa_borrowed_tokens": swa_borrowed,
                "full_cached_borrowed_tokens": self.region_full_borrowed_tokens[
                    region
                ],
                "swa_cached_borrowed_tokens": self.region_swa_borrowed_tokens[
                    region
                ],
                "full_cached_preferred_borrowed_tokens": (
                    self.region_full_preferred_borrowed_tokens[region]
                ),
                "swa_cached_preferred_borrowed_tokens": (
                    self.region_swa_preferred_borrowed_tokens[region]
                ),
                "borrowed_eviction_count": self.region_borrowed_eviction_count[
                    region
                ],
                "borrowed_full_evicted_tokens": self.region_borrowed_full_evicted_tokens[
                    region
                ],
                "borrowed_swa_evicted_tokens": self.region_borrowed_swa_evicted_tokens[
                    region
                ],
                "borrow_reclaim_reasons": dict(
                    self.region_borrow_reclaim_reason_count[region]
                ),
                "elastic_tail_first_activations": self._elastic_tail_first_activations[
                    region
                ],
                "elastic_tail_first_evicted_full_tokens": self._elastic_tail_first_evicted_full_tokens[
                    region
                ],
                "elastic_tail_first_evicted_swa_tokens": self._elastic_tail_first_evicted_swa_tokens[
                    region
                ],
                "full_used_tokens": self.region_full_used_tokens[region],
                "swa_used_tokens": self.region_swa_used_tokens[region],
                "full_evictable_tokens": 0,
                "swa_evictable_tokens": 0,
                "eviction_count": self.region_eviction_count[region],
                "full_evicted_tokens": self.region_full_evicted_tokens[region],
                "swa_evicted_tokens": self.region_swa_evicted_tokens[region],
                "full_over_quota_tokens": max(
                    self.region_full_used_tokens[region]
                    - (
                        base_full_quotas[region]
                        if self.request_cache_region_policy
                        not in (
                            "borrow",
                            "borrow_dynamic",
                            "borrow_global",
                            "borrow_reclass",
                            "borrow_request_reclass",
                            "elastic",
                        )
                        else base_full_quotas[region] + full_borrowed
                    ),
                    0,
                ),
                "swa_over_quota_tokens": max(
                    self.region_swa_used_tokens[region]
                    - (
                        base_swa_quotas[region]
                        if self.request_cache_region_policy
                        not in (
                            "borrow",
                            "borrow_dynamic",
                            "borrow_global",
                            "borrow_reclass",
                            "borrow_request_reclass",
                            "elastic",
                        )
                        else base_swa_quotas[region] + swa_borrowed
                    ),
                    0,
                ),
            }
        for node in self._collect_all_nodes():
            if node.cache_region not in stats:
                continue
            if node.full_lock_ref == 0:
                stats[node.cache_region]["full_evictable_tokens"] += len(node.key)
            if not node.swa_tombstone and node.swa_lock_ref == 0:
                stats[node.cache_region]["swa_evictable_tokens"] += len(node.key)
        return stats

    def inc_lock_ref(self, node: TreeNode) -> IncLockRefResult:
        """
        Increment the lock reference count for the node. Returns the swa_uuid_for_lock, which needs
        to be passed to dec_lock_ref.
        It locks the full_lock_ref for nodes between the [last node, root), exclusive.
        It locks the swa_lock_ref for nodes between the [last node, swa_uuid_for_lock], inclusive.
        """
        if self.disable:
            return IncLockRefResult()

        swa_lock_size = 0
        swa_uuid_for_lock = None
        while node != self.root_node:
            # lock full from node to root
            assert (
                node.full_lock_ref >= 0
            ), f"inc_lock_ref on node with {node.full_lock_ref=}, {node.id=}"
            if node.full_lock_ref == 0:
                self.full_evictable_size_ -= len(node.value)
                self.full_protected_size_ += len(node.value)
            node.full_lock_ref += 1

            # lock swa if we have not reached the sliding window size.
            # When we reach the sliding window size, we will set the swa_uuid_for_lock.
            # caller needs to pass the swa_uuid_for_lock to dec_lock_ref
            if swa_lock_size < self.sliding_window_size:
                assert (
                    not node.swa_tombstone
                ), f"inc_lock_swa on swa_tombstone node, {node.id=}"
                if node.swa_lock_ref == 0:
                    self.swa_evictable_size_ -= len(node.value)
                    self.swa_protected_size_ += len(node.value)
                node.swa_lock_ref += 1
                swa_lock_size += len(node.value)
                if swa_lock_size >= self.sliding_window_size:
                    if node.swa_uuid is None:
                        node.swa_uuid = gen_swa_uuid()
                    swa_uuid_for_lock = node.swa_uuid
            node = node.parent
        return IncLockRefResult(swa_uuid_for_lock=swa_uuid_for_lock)

    def dec_lock_ref(
        self,
        node: TreeNode,
        params: Optional[DecLockRefParams] = None,
        skip_swa: bool = False,
    ) -> DecLockRefResult:
        """
        Decrement the lock reference count for the node.
        It unlocks the full_lock_ref for nodes between the [last node, root), exclusive.
        It unlocks the swa_lock_ref for nodes between the [last node, swa_uuid_for_lock], inclusive.
        If swa_uuid_for_lock is None, it unlocks to the root, exclusive.

        If skip_swa is True, only the full_lock_ref is decremented; the SWA lock is
        assumed to have been released already (e.g. via `dec_swa_lock_only`).
        """
        swa_uuid_for_lock = params.swa_uuid_for_lock if params is not None else None

        if self.disable:
            return DecLockRefResult()

        dec_lock_swa = not skip_swa
        while node != self.root_node:
            assert (
                node.full_lock_ref > 0
            ), f"dec_lock_ref on node with {node.full_lock_ref=}, {node.id=}"
            if node.full_lock_ref == 1:
                self.full_evictable_size_ += len(node.value)
                self.full_protected_size_ -= len(node.value)
            node.full_lock_ref -= 1

            if dec_lock_swa:
                assert (
                    not node.swa_tombstone
                ), f"dec_lock_ref on swa_tombstone node, {node.id=}"
                assert (
                    node.swa_lock_ref > 0
                ), f"dec_lock_ref on node with {node.swa_lock_ref=}, {node.id=}"

                if node.swa_lock_ref == 1:
                    self.swa_evictable_size_ += len(node.value)
                    self.swa_protected_size_ -= len(node.value)
                node.swa_lock_ref -= 1
                if swa_uuid_for_lock and node.swa_uuid == swa_uuid_for_lock:
                    dec_lock_swa = False

            node = node.parent

        return DecLockRefResult()

    def dec_swa_lock_only(
        self, node: TreeNode, swa_uuid_for_lock: Optional[int] = None
    ):
        """
        Decrement only the swa_lock_ref (and swa_protected_size_) along the chain
        [node, swa_uuid_for_lock], inclusive. The full_lock_ref is left untouched
        so the caller's full-cache protection is preserved.

        Used to early-release the SWA portion of a request's tree lock once the
        request's decode position has advanced past the sliding window, so the
        protected window can be reclaimed.

        For internal nodes, the standard protected -> evictable transition is
        applied (node stays in swa_lru_list and may be evicted by SWA LRU later).
        For leaf nodes, since `swa_lru_list` cannot contain a leaf with
        `full_lock_ref > 0` (SWA-eviction would also delete the still-referenced
        leaf), we instead free the SWA pool slots immediately and mark the leaf
        as `swa_tombstone=True`. The full kv stays alive until the full-side
        lock drops; future prefix-matches stop before this tombstoned leaf.

        Caller must ensure this is invoked at most once per (node, swa_uuid_for_lock)
        pair (track via e.g. `Req.swa_prefix_lock_released`). When the request
        finally releases its full lock via `dec_lock_ref`, pass `skip_swa=True`
        to avoid touching SWA state again.
        """
        if self.disable:
            return

        while node != self.root_node:
            assert (
                not node.swa_tombstone
            ), f"dec_swa_lock_only on swa_tombstone node, {node.id=}"
            assert (
                node.swa_lock_ref > 0
            ), f"dec_swa_lock_only on node with {node.swa_lock_ref=}, {node.id=}"

            if node.swa_lock_ref == 1:
                self.swa_protected_size_ -= len(node.value)
                if len(node.children) == 0:
                    # Leaf: free SWA pool slots and tombstone, and remove from
                    # swa_lru_list so SWA-eviction won't pick this tombstoned
                    # leaf (which still holds full_lock_ref > 0). The full kv
                    # stays alive until the request releases its full lock.
                    self.token_to_kv_pool_allocator.free_swa(node.value)
                    self.swa_lru_list.remove_node(node)
                    node.swa_tombstone = True
                    if node.cache_region in self.region_swa_used_tokens:
                        self.region_swa_used_tokens[node.cache_region] -= len(
                            node.value
                        )
                        if node.swa_borrowed:
                            self.region_swa_borrowed_tokens[node.cache_region] -= len(
                                node.value
                            )
                        if node.swa_preferred_borrowed:
                            self.region_swa_preferred_borrowed_tokens[
                                node.cache_region
                            ] -= len(node.value)
                else:
                    # Internal: standard protected -> evictable.
                    self.swa_evictable_size_ += len(node.value)
            node.swa_lock_ref -= 1

            if swa_uuid_for_lock and node.swa_uuid == swa_uuid_for_lock:
                break
            node = node.parent

    def sanity_check(self):
        self.full_lru_list.sanity_check(self)
        self.swa_lru_list.sanity_check(self)

    def evictable_size(self) -> Tuple[int, int]:
        # Note: use full_evictable_size() and swa_evictable_size() instead.
        raise NotImplementedError

    def full_evictable_size(self) -> int:
        return self.full_evictable_size_

    def swa_evictable_size(self) -> int:
        return self.swa_evictable_size_

    def protected_size(self) -> Tuple[int, int]:
        # Note: use full_protected_size() and swa_protected_size() instead.
        raise NotImplementedError

    def full_protected_size(self) -> int:
        # protected size refers to the size of the full cache that is locked
        return self.full_protected_size_

    def swa_protected_size(self) -> int:
        # protected size refers to the size of the swa cache that is locked
        return self.swa_protected_size_

    def all_values_flatten(self) -> torch.Tensor:
        values = []

        def _dfs_helper(node: TreeNode):
            for _, child in node.children.items():
                values.append(child.value)
                _dfs_helper(child)

        _dfs_helper(self.root_node)
        return torch.cat(values)

    def available_and_evictable_str(self) -> str:
        full_available_size = self.token_to_kv_pool_allocator.full_available_size()
        swa_available_size = self.token_to_kv_pool_allocator.swa_available_size()
        full_evictable_size = self.full_evictable_size()
        swa_evictable_size = self.swa_evictable_size()
        return (
            f"Available full tokens: {full_available_size + full_evictable_size} ({full_available_size=} + {full_evictable_size=})\n"
            f"Available swa tokens: {swa_available_size + swa_evictable_size} ({swa_available_size=} + {swa_evictable_size=})\n"
            f"Full LRU list evictable size: {self.full_lru_list.sanity_check_evictable_size()}\n"
            f"SWA LRU list evictable size: {self.swa_lru_list.sanity_check_evictable_size()}\n"
        )

    ##### Internal Helper Functions #####

    def _iter_full_unlocked_leaves(
        self,
        region: Optional[str] = None,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ):
        node = self.full_lru_list.get_leaf_lru_no_lock()
        while self.full_lru_list.in_list(node):
            if (region is None or node.cache_region == region) and (
                not borrowed_only or node.full_borrowed
            ) and (
                not preferred_borrowed_only or node.full_preferred_borrowed
            ):
                yield node
            node = self.full_lru_list.get_prev_leaf_no_lock(node)

    def _iter_swa_unlocked(
        self,
        region: Optional[str] = None,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ):
        node = self.swa_lru_list.get_lru_no_lock()
        while self.swa_lru_list.in_list(node):
            if (region is None or node.cache_region == region) and (
                not borrowed_only or node.swa_borrowed
            ) and (
                not preferred_borrowed_only or node.swa_preferred_borrowed
            ):
                yield node
            node = self.swa_lru_list.get_prev_no_lock(node)

    def _elastic_ghost_revisit_score(self, node: TreeNode) -> float:
        """Return observed recomputation pressure for one Full/SWA node."""

        if (
            not getattr(self, "request_cache_elastic_ghost_protect", False)
            or self.request_region_ghost is None
            or not self.request_region_ghost.enabled
            or node.cache_region not in self.region_full_used_tokens
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

    def _elastic_ghost_protection_active(
        self, borrowed_only: bool, preferred_borrowed_only: bool
    ) -> bool:
        """Use node-level ghost protection only on borrowed reclaim paths."""

        return bool(
            getattr(self, "request_cache_elastic_ghost_protect", False)
            and self.request_cache_region_policy == "elastic"
            and self.request_region_ghost is not None
            and self.request_region_ghost.enabled
            and (borrowed_only or preferred_borrowed_only)
        )

    def _unprotected_first(
        self,
        candidates: list[TreeNode],
        *,
        borrowed_only: bool,
        preferred_borrowed_only: bool,
    ) -> list[TreeNode]:
        """Partition eligible victims while preserving their base order."""

        if not self._elastic_ghost_protection_active(
            borrowed_only, preferred_borrowed_only
        ):
            return candidates
        unprotected = [
            node
            for node in candidates
            if self._elastic_ghost_revisit_score(node)
            < self._elastic_ghost_protect_threshold()
        ]
        return unprotected or candidates

    def _evict_one_swa_unlocked_node(
        self,
        x: TreeNode,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ) -> Tuple[int, int]:
        assert not x.swa_tombstone, f"duplicate swa tombstone node, {x.id=}"
        assert x != self.root_node, f"root node is not evictable, {x.id=}"
        assert x.swa_lock_ref == 0, f"node is in use by swa kv indices, {x.id=}"

        full_num_evicted = 0
        swa_num_evicted = 0
        if len(x.children) > 0:
            self.token_to_kv_pool_allocator.free_swa(x.value)
            swa_num_evicted += len(x.value)
            self.swa_lru_list.remove_node(x)
            self._tombstone_internal_node(x)
        elif x.full_lock_ref > 0:
            # Leaf still holds a full-side lock (can happen when the
            # SWA leaf-lock early-release optimization revived a
            # tombstoned leaf. Treat it like an internal tombstone.
            self.token_to_kv_pool_allocator.free_swa(x.value)
            swa_num_evicted += len(x.value)
            self.swa_lru_list.remove_node(x)
            self.swa_evictable_size_ -= len(x.value)
            x.swa_tombstone = True
            if x.cache_region in self.region_swa_used_tokens:
                self.region_swa_used_tokens[x.cache_region] -= len(x.value)
                if x.swa_borrowed:
                    self.region_swa_borrowed_tokens[x.cache_region] -= len(x.value)
                if x.swa_preferred_borrowed:
                    self.region_swa_preferred_borrowed_tokens[x.cache_region] -= len(
                        x.value
                    )
        else:
            assert (
                x.full_lock_ref == 0
            ), f"leaf node with full lock must also have swa lock, {x.id=}"
            self._record_remove_event(x)
            self.token_to_kv_pool_allocator.free(x.value)
            full_num_evicted += len(x.value)
            swa_num_evicted += len(x.value)
            self.full_lru_list.remove_node(x)
            self.swa_lru_list.remove_node(x)
            self._delete_leaf(x)
            _, leaf_full_num_evicted = self._iteratively_delete_tombstone_leaf(
                x,
                borrowed_only=borrowed_only,
                preferred_borrowed_only=preferred_borrowed_only,
            )
            full_num_evicted += leaf_full_num_evicted
        return full_num_evicted, swa_num_evicted

    def _select_swa_victim(
        self,
        region: Optional[str] = None,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ):
        candidates = self._unprotected_first(
            list(
                self._iter_swa_unlocked(
                    region, borrowed_only, preferred_borrowed_only
                )
            ),
            borrowed_only=borrowed_only,
            preferred_borrowed_only=preferred_borrowed_only,
        )
        fallback = candidates[0] if candidates else None
        if getattr(self, "mlp_enabled", False):
            return self._select_mlp_swa_victim(
                iter(candidates),
                fallback,
            )
        return fallback

    def _evict_one_full_unlocked_leaf(
        self,
        x: TreeNode,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ) -> Tuple[int, int, TreeNode]:
        assert x != self.root_node, f"root node should not exist in full lru list, {x.id=}"
        assert x.full_lock_ref == 0, f"node is in use, {x.id=}"

        full_num_evicted = 0
        swa_num_evicted = 0
        self._record_remove_event(x)
        self.token_to_kv_pool_allocator.free(x.value)
        full_num_evicted += len(x.value)
        if not x.swa_tombstone:
            swa_num_evicted += len(x.value)

        self.full_lru_list.remove_node(x)
        if not x.swa_tombstone:
            self.swa_lru_list.remove_node(x)

        self._delete_leaf(x)
        walked, leaf_full_num_evicted = self._iteratively_delete_tombstone_leaf(
            x,
            borrowed_only=borrowed_only,
            preferred_borrowed_only=preferred_borrowed_only,
        )
        full_num_evicted += leaf_full_num_evicted
        return full_num_evicted, swa_num_evicted, walked

    def _select_full_leaf_victim(
        self,
        region: Optional[str] = None,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ):
        candidates = self._unprotected_first(
            list(
                self._iter_full_unlocked_leaves(
                    region, borrowed_only, preferred_borrowed_only
                )
            ),
            borrowed_only=borrowed_only,
            preferred_borrowed_only=preferred_borrowed_only,
        )
        fallback = candidates[0] if candidates else None
        if getattr(self, "mlp_enabled", False):
            return self._select_mlp_victim(
                iter(candidates),
                fallback,
            )
        return self._select_reuse_value_victim(
            iter(candidates),
            fallback,
        )

    def _match_prefix_helper(
        self, key: RadixKey, update_reuse_strength: bool = True
    ) -> Tuple[List[torch.Tensor], TreeNode, int]:
        """
        SWA prefix matching helper. It factors in the sliding window size such that
        the matched node is guaranteed to either 1. connected to root without swa tombstone,
        or 2. the number of matching tokens from the matched node to the last swa tombstone
        node is greater than or equal to the sliding window size.
        """
        node = self.root_node
        child_key = key.child_key(self.page_size)

        value = []
        # for path connected to root without tombstone, always match, so set to inf
        match_len_since_tombstone = float("inf")
        best_value_len = 0
        best_last_node = node
        enable_compact = envs.SGLANG_OPT_SWA_RADIX_CACHE_COMPACT.get()
        while len(key) > 0 and child_key in node.children.keys():
            child = node.children[child_key]

            if enable_compact:
                self._compact_single_child_chain(child)

            if child.swa_tombstone:
                # update best_value_len and best_last_node if needed
                if match_len_since_tombstone >= self.sliding_window_size:
                    best_value_len = len(value)
                    best_last_node = node
                # reset match_len_since_tombstone if we hit a tombstone node
                match_len_since_tombstone = 0

            prefix_len = child.key.match(key, page_size=self.page_size)
            if prefix_len < len(child.key):
                new_node = self._split_node(child.key, child, prefix_len)
                value.append(new_node.value)
                if not new_node.swa_tombstone:
                    match_len_since_tombstone += len(new_node.value)
                node = new_node
                if update_reuse_strength:
                    self._record_reuse(new_node)
                break
            else:
                value.append(child.value)
                if not child.swa_tombstone:
                    match_len_since_tombstone += len(child.value)
                node = child
                if update_reuse_strength:
                    self._record_reuse(child)
                key = key[prefix_len:]

                if len(key):
                    child_key = key.child_key(self.page_size)

        # handle best_value_len and best_last_node, for the case that last node is fully matched
        if match_len_since_tombstone >= self.sliding_window_size:
            best_value_len = len(value)
            best_last_node = node

        return value, best_last_node, best_value_len

    def _match_pre_processor(self, params: MatchPrefixParams) -> Optional[RadixKey]:
        """Preprocess the key before matching."""
        key = params.key
        key, _ = key.maybe_to_bigram_view(self.is_eagle)
        if self.disable or len(key) == 0:
            return None
        key = key.page_aligned(self.page_size)
        if len(key) == 0:
            return None
        return key

    def _match_post_processor(
        self,
        params: MatchPrefixParams,
        value: List[torch.Tensor],
        last_node: TreeNode,
        best_value_len: int,
    ) -> MatchResult:
        """Post-process the matched result."""
        node_update = last_node
        # update time for matched nodes, and make nodes closer to root to be least recently used
        # this allows swa to evict nodes closer to root first
        self.full_lru_list.reset_node_and_parents_mru(node_update, self.root_node)
        self.swa_lru_list.reset_node_and_parents_mru(node_update, self.root_node)

        # This last_access_time is for sanity check, can be deleted after validation in production
        cur_time = get_last_access_time()
        while node_update:
            node_update.last_access_time = cur_time
            cur_time -= (
                0.00001  # assuming less than 100000 nodes in a branch of the tree
            )
            node_update = node_update.parent

        value = value[:best_value_len]
        if value:
            value = torch.cat(value)
        else:
            value = torch.empty((0,), dtype=torch.int64, device=self.device)

        return MatchResult(
            device_indices=value,
            last_device_node=last_node,
            last_host_node=last_node,
            best_match_node=last_node,
        )

    def _compact_single_child_chain(self, node: TreeNode) -> None:
        # FIXME(ispobock): drifts retract pool accounting (commit 6348cb506);
        # also overwrites active swa_uuid when window > page_size. Off by
        # default via SGLANG_OPT_SWA_RADIX_CACHE_COMPACT.
        while len(node.children) == 1:
            child = next(iter(node.children.values()))
            if len(child.children) == 0:
                break
            sum_gc_full_lock_ref = sum(
                gc.full_lock_ref for gc in child.children.values()
            )
            if child.full_lock_ref > sum_gc_full_lock_ref:
                break
            if (
                child.swa_tombstone != node.swa_tombstone
                or child.full_lock_ref != node.full_lock_ref
                or child.swa_lock_ref != node.swa_lock_ref
                or child.cache_region != node.cache_region
                or child.full_borrowed != node.full_borrowed
                or child.swa_borrowed != node.swa_borrowed
                or child.full_preferred_borrowed != node.full_preferred_borrowed
                or child.swa_preferred_borrowed != node.swa_preferred_borrowed
            ):
                break

            # Preserve is_bigram: main #23106 made bigram an O(1) flag on RadixKey;
            # the constructor defaults to False, so concat without explicit flag
            # silently demotes EAGLE/MTP bigram keys → match() returns 0 →
            # _split_node assert.
            node.key = RadixKey(
                node.key.token_ids + child.key.token_ids,
                node.key.extra_key,
                is_bigram=node.key.is_bigram,
            )
            node.value = torch.cat([node.value, child.value])
            node.children = child.children
            for grandchild in node.children.values():
                grandchild.parent = node

            if child.swa_uuid is not None:
                node.swa_uuid = child.swa_uuid

            if node.hash_value is not None and child.hash_value is not None:
                node.hash_value = list(node.hash_value) + list(child.hash_value)
            else:
                node.hash_value = None

            self.full_lru_list.remove_node(child)
            if not child.swa_tombstone:
                self.swa_lru_list.remove_node(child)

    def _maybe_split_leaf_for_swa_lock(self, leaf: TreeNode) -> TreeNode:
        """``inc_lock_ref`` protects ``len(leaf.value)`` SWA tokens for the
        leaf even though SWA only actually needs the last
        ``sliding_window_size`` tokens. With chunked prefill, leaves can be
        thousands of tokens long, which inflates ``swa_protected_size_`` by
        ~``chunked_prefill_size / sliding_window_size`` and causes premature
        SWA pool exhaustion / retract thrashing.
        """
        if (
            leaf is self.root_node
            or leaf.swa_lock_ref > 0
            or leaf.swa_tombstone
            or len(leaf.value) == 0
        ):
            return leaf

        # Smallest page-aligned size that still covers the sliding window.
        tail_size = (
            (self.sliding_window_size + self.page_size - 1)
            // self.page_size
            * self.page_size
        )
        if len(leaf.value) <= tail_size:
            return leaf

        split_at = len(leaf.value) - tail_size

        if split_at <= 0 or split_at >= len(leaf.value):
            return leaf
        if self.page_size > 1 and (
            split_at % self.page_size != 0 or len(leaf.value) % self.page_size != 0
        ):
            return leaf

        self._split_node(leaf.key, leaf, split_at)
        return leaf

    def _split_node(self, key: RadixKey, child: TreeNode, split_len: int) -> TreeNode:
        # new_node -> child
        new_node = TreeNode()
        new_node.children = {key[split_len:].child_key(self.page_size): child}
        new_node.parent = child.parent
        new_node.swa_tombstone = child.swa_tombstone
        new_node.cache_region = child.cache_region
        new_node.full_borrowed = child.full_borrowed
        new_node.swa_borrowed = child.swa_borrowed
        new_node.full_preferred_borrowed = child.full_preferred_borrowed
        new_node.swa_preferred_borrowed = child.swa_preferred_borrowed
        new_node.full_lock_ref = child.full_lock_ref
        new_node.swa_lock_ref = child.swa_lock_ref
        new_node.key = child.key[:split_len]
        assert len(new_node.key) > 0, f"new_node.key should not be empty"
        new_node.value = child.value[:split_len].clone()
        copy_reuse_value_on_split(new_node, child)
        copy_mlp_on_split(new_node, child)
        # parent inherits the swa_uuid from child for swa lock ref
        new_node.swa_uuid = child.swa_uuid
        child.swa_uuid = None
        # child time should be later than parent's time for swa tombstone
        child.last_access_time = get_last_access_time()

        # remove the child from the lru lists because it is being split
        self.full_lru_list.remove_node(child)
        if not new_node.swa_tombstone:
            self.swa_lru_list.remove_node(child)
        child.parent = new_node
        child.key = child.key[split_len:]
        assert len(child.key) > 0, f"child.key should not be empty"
        child.value = child.value[split_len:].clone()
        # Splitting changes the complete parent-chain prefix used by the
        # bounded ghost index.  Drop both nodes' cached fingerprints and
        # scores so Full and SWA apply the same valid protection decision.
        for split_node in (new_node, child):
            split_node.__dict__.pop("_elastic_ghost_prefix_keys", None)
            split_node.__dict__.pop("_elastic_ghost_extra_key", None)
            split_node.__dict__.pop("_elastic_ghost_score_step", None)
            split_node.__dict__.pop("_elastic_ghost_score", None)
        new_node.parent.children[key.child_key(self.page_size)] = new_node
        new_node.hash_value, child.hash_value = split_node_hash_value(
            child.hash_value, split_len, self.page_size
        )

        # insert the new node and child into the lru lists, insert
        # parent first so that parent is after child in the lru list
        self.full_lru_list.insert_mru(new_node)
        self.full_lru_list.insert_mru(child)
        if not new_node.swa_tombstone:
            self.swa_lru_list.insert_mru(new_node)
            self.swa_lru_list.insert_mru(child)
        return new_node

    def _request_cache_insert_segment_len(
        self, key_len: int, region: Optional[str]
    ) -> int:
        """Bound newly inserted borrowed suffix nodes in both KV pools.

        Full and SWA use the same configured segment size.  The first segment
        may cover the remaining protected quota; once the suffix crosses that
        line, subsequent segments are page aligned and independently
        reclaimable.
        """
        if key_len <= 0 or region not in self.region_full_used_tokens:
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
        full_capacity = int(self.token_to_kv_pool_allocator.size_full)
        swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
        if full_capacity <= 0 and swa_capacity <= 0:
            return key_len
        full_base, swa_base = self._region_base_quotas(full_capacity, swa_capacity)
        full_used = self.region_full_used_tokens[region]
        swa_used = self.region_swa_used_tokens[region]
        crosses_full = full_used + key_len > full_base[region]
        crosses_swa = swa_used + key_len > swa_base[region]
        if not (crosses_full or crosses_swa):
            return key_len
        page = max(int(self.page_size), 1)
        granularity = max((configured // page) * page, page)
        remaining_to_base = []
        if crosses_full:
            remaining_to_base.append(max(full_base[region] - full_used, 0))
        if crosses_swa:
            remaining_to_base.append(max(swa_base[region] - swa_used, 0))
        below_base = min(remaining_to_base) if remaining_to_base else 0
        aligned_below_base = (below_base // page) * page
        if aligned_below_base > 0:
            return min(key_len, aligned_below_base)
        return min(key_len, granularity)

    def _insert_helper(
        self,
        node: TreeNode,
        key: RadixKey,
        value,
        update_kv_after_len: int,
        swa_evicted_seqlen: int = 0,
        is_terminal: bool = False,
        region: Optional[str] = None,
    ) -> int:
        # Update the last access time from root to leaf, so that
        # swa will tombstone the node closer to root first
        node.last_access_time = get_last_access_time()
        if node != self.root_node:
            self.full_lru_list.reset_node_mru(node)
            if not node.swa_tombstone:
                self.swa_lru_list.reset_node_mru(node)
        if len(key) == 0:
            if is_terminal and self.reuse_value_enabled:
                node.terminal_count += 1
            return 0

        child_key = key.child_key(self.page_size)

        total_prefix_length = 0
        while len(key) > 0 and child_key in node.children.keys():
            node = node.children[child_key]
            node.last_access_time = get_last_access_time()
            self.full_lru_list.reset_node_mru(node)
            if not node.swa_tombstone:
                self.swa_lru_list.reset_node_mru(node)
            prefix_len = node.key.match(key, page_size=self.page_size)

            if prefix_len < len(node.key):
                new_node = self._split_node(node.key, node, prefix_len)
                node = new_node

            # if tombstone after update_kv_after_len, update node.value to be the input value.
            # This is needed because it is possible that the last sliding window size tokens
            # contains tombstone. If this is the case and we don't update the kv value, then
            # the prefill prefix matching will stuck.
            if update_kv_after_len < total_prefix_length + prefix_len:
                # For page_size > 1 and chunked prefill case, update_kv_after_len may be not page-aligned due to a trailing partial page
                # (kept in the request but not inserted into the radix tree) appended to prefix_indices.
                if node.swa_tombstone:
                    assert (
                        node.swa_lock_ref == 0
                    ), f"tombstone swa_lock_ref should always be 0, {node.full_lock_ref=}, {node.swa_lock_ref=}, {node.id=}"
                    assert (
                        swa_evicted_seqlen % self.page_size == 0
                    ), f"swa_evicted_seqlen must be page aligned, {swa_evicted_seqlen=}, {self.page_size=}"
                    if swa_evicted_seqlen <= total_prefix_length:
                        # Branch 1: all swa tokens of value[:prefix_len] are not evicted, so we can insert it to the tree directly.
                        # Free full tokens in the original tree node.
                        self.token_to_kv_pool_allocator.free(node.value[:prefix_len])
                        # Overwrite the new value in request to the tree node.
                        node.value = value[:prefix_len].clone()
                        node.swa_tombstone = False
                        self.swa_lru_list.insert_mru(node)
                        self.swa_evictable_size_ += len(node.value)
                        if node.cache_region in self.region_swa_used_tokens:
                            self.region_swa_used_tokens[node.cache_region] += len(
                                node.value
                            )
                            if node.swa_borrowed:
                                self.region_swa_borrowed_tokens[node.cache_region] += len(
                                    node.value
                                )
                            if node.swa_preferred_borrowed:
                                self.region_swa_preferred_borrowed_tokens[
                                    node.cache_region
                                ] += len(node.value)
                    elif swa_evicted_seqlen < total_prefix_length + prefix_len:
                        # Branch 2: part of swa tokens of value[:prefix_len] are evicted, so we need to split the node and insert the value to new node.
                        start_update_idx = swa_evicted_seqlen - total_prefix_length
                        self.token_to_kv_pool_allocator.free(
                            node.value[start_update_idx:prefix_len]
                        )
                        self._split_node(node.key, node, start_update_idx)
                        # Here node is the new node after split, so we can overwrite the value to the new node.
                        # The old node is still swa tombstone and the full token is not freed.
                        node.value = value[start_update_idx:prefix_len].clone()
                        self.token_to_kv_pool_allocator.free(value[:start_update_idx])
                        node.swa_tombstone = False
                        self.swa_lru_list.insert_mru(node)
                        self.swa_evictable_size_ += len(node.value)
                        if node.cache_region in self.region_swa_used_tokens:
                            self.region_swa_used_tokens[node.cache_region] += len(
                                node.value
                            )
                            if node.swa_borrowed:
                                self.region_swa_borrowed_tokens[node.cache_region] += len(
                                    node.value
                                )
                            if node.swa_preferred_borrowed:
                                self.region_swa_preferred_borrowed_tokens[
                                    node.cache_region
                                ] += len(node.value)
                    else:
                        # Branch 3: all swa tokens of value[:prefix_len] are evicted, so we don't need to update the node.
                        self.token_to_kv_pool_allocator.free(value[:prefix_len])
                else:
                    # The node is not tombstone, so we don't need to update the node.
                    self.token_to_kv_pool_allocator.free(value[:prefix_len])

            total_prefix_length += prefix_len
            key = key[prefix_len:]
            value = value[prefix_len:]

            if len(key):
                child_key = key.child_key(self.page_size)

        if len(key):
            # Layout: |--- total_prefix_length ---|--- len(key) ---|
            #         ^                           ^                ^
            #         0              total_prefix_length     total_length
            #
            # Cases based on swa_evicted_seqlen position:
            # 1. swa_evicted_seqlen <= total_prefix_length:
            #    Already handled in the while loop above. All of len(key) is non-tombstone.
            # 2. total_prefix_length < swa_evicted_seqlen < total_length:
            #    Split: [total_prefix_length, swa_evicted_seqlen) as tombstone,
            #           [swa_evicted_seqlen, total_length) as non-tombstone.
            # 3. swa_evicted_seqlen == total_length:
            #    All remaining tokens are evicted. Free value and return without
            #    creating a node (leaf nodes must not be tombstone).
            #    Note: the -page_size fix in _evict_swa prevents this case from
            #    occurring in normal operation. This check is a defensive guard
            #    against unexpected eviction states from other code paths.
            if swa_evicted_seqlen == total_prefix_length + len(key):
                self.token_to_kv_pool_allocator.free(value)
                if is_terminal and self.reuse_value_enabled:
                    node.terminal_count += 1
                return total_prefix_length

            if (
                swa_evicted_seqlen > total_prefix_length
                and swa_evicted_seqlen < total_prefix_length + len(key)
            ):
                swa_tombstone_len = swa_evicted_seqlen - total_prefix_length
                node = self._add_new_node(
                    node,
                    key[:swa_tombstone_len],
                    value[:swa_tombstone_len],
                    swa_tombstone=True,
                    region=region,
                )
                key = key[swa_tombstone_len:]
                value = value[swa_tombstone_len:]

            # Keep the same borrowed-suffix granularity for Full and SWA. The
            # helper returns the whole suffix when the experimental option is
            # disabled, preserving the historical tree layout.
            while len(key):
                segment_len = self._request_cache_insert_segment_len(
                    len(key), region
                )
                new_leaf = self._add_new_node(
                    node,
                    key[:segment_len],
                    value[:segment_len],
                    swa_tombstone=False,
                    region=region,
                )

                if envs.SGLANG_OPT_SWA_SPLIT_LEAF_ON_INSERT.get():
                    # Cap each newly created leaf at one (page-aligned)
                    # sliding window so future SWA locks do not protect a
                    # complete long borrowed suffix.
                    self._maybe_split_leaf_for_swa_lock(new_leaf)
                node = new_leaf
                key = key[segment_len:]
                value = value[segment_len:]

        if is_terminal and self.reuse_value_enabled:
            node.terminal_count += 1
        return total_prefix_length

    def _add_new_node(
        self,
        parent: TreeNode,
        key: RadixKey,
        value: torch.Tensor,
        swa_tombstone: bool = False,
        region: Optional[str] = None,
    ) -> TreeNode:
        assert len(key) > 0, f"key should not be empty"
        new_node = TreeNode()
        new_node.parent = parent
        new_node.key = key
        new_node.value = value.clone()
        new_node.swa_tombstone = swa_tombstone
        new_node.cache_region = region
        if self.request_regions_enabled and region in self.region_full_used_tokens:
            full_capacity = int(self.token_to_kv_pool_allocator.size_full)
            swa_capacity = int(self.token_to_kv_pool_allocator.size_swa)
            base_full_quotas, base_swa_quotas = self._region_base_quotas(
                full_capacity, swa_capacity
            )
            full_base = (
                base_full_quotas[region]
            )
            swa_base = (
                base_swa_quotas[region]
            )
            other = "request" if region == "agent" else "agent"
            other_full_base = base_full_quotas[other]
            other_swa_base = base_swa_quotas[other]
            full_over_base = self.region_full_used_tokens[region] + len(value) > full_base
            swa_over_base = self.region_swa_used_tokens[region] + len(value) > swa_base
            # A cache page may straddle the guarantee boundary.  Classic
            # borrow marks it only when the other region has idle guaranteed
            # capacity; elastic mode marks every page above the minimum as
            # belonging to the shared pool.
            if self.request_cache_region_policy == "elastic":
                preferred_ratio = self._elastic_preferred_agent_ratio()
                full_preferred_quota = int(
                    full_capacity
                    * (
                        preferred_ratio
                        if region == "agent"
                        else 1.0 - preferred_ratio
                    )
                )
                swa_preferred_quota = int(
                    swa_capacity
                    * (
                        preferred_ratio
                        if region == "agent"
                        else 1.0 - preferred_ratio
                    )
                )
                new_node.full_borrowed = full_over_base
                new_node.swa_borrowed = not swa_tombstone and swa_over_base
                new_node.full_preferred_borrowed = (
                    self.region_full_used_tokens[region] + len(value)
                    > full_preferred_quota
                )
                new_node.swa_preferred_borrowed = (
                    not swa_tombstone
                    and self.region_swa_used_tokens[region] + len(value)
                    > swa_preferred_quota
                )
            else:
                new_node.full_borrowed = full_over_base and (
                    self.request_cache_region_policy
                    in (
                        "borrow",
                        "borrow_dynamic",
                        "borrow_global",
                        "borrow_reclass",
                        "borrow_request_reclass",
                    )
                    and self.region_full_used_tokens[other] < other_full_base
                )
                new_node.swa_borrowed = (
                    not swa_tombstone
                    and swa_over_base
                    and self.request_cache_region_policy
                    in (
                        "borrow",
                        "borrow_dynamic",
                        "borrow_global",
                        "borrow_reclass",
                        "borrow_request_reclass",
                    )
                    and self.region_swa_used_tokens[other] < other_swa_base
                )
        new_node.prefix_depth = parent.prefix_depth + len(key)
        self._mlp_stamp_new_node(new_node)
        if self.reuse_value_enabled:
            self._initialize_reuse_value_node(new_node, parent)
            self._record_reuse_value_insert(len(key))
            new_node.last_turnover = self.reuse_value_global_turnover
        parent.children[key.child_key(self.page_size)] = new_node
        self.full_lru_list.insert_mru(new_node)
        self.full_evictable_size_ += len(value)
        if region in self.region_full_used_tokens:
            self.region_full_used_tokens[region] += len(value)
            if new_node.full_borrowed:
                self.region_full_borrowed_tokens[region] += len(value)
            if new_node.full_preferred_borrowed:
                self.region_full_preferred_borrowed_tokens[region] += len(value)
        if not swa_tombstone:
            self.swa_lru_list.insert_mru(new_node)
            self.swa_evictable_size_ += len(value)
            if region in self.region_swa_used_tokens:
                self.region_swa_used_tokens[region] += len(value)
                if new_node.swa_borrowed:
                    self.region_swa_borrowed_tokens[region] += len(value)
                if new_node.swa_preferred_borrowed:
                    self.region_swa_preferred_borrowed_tokens[region] += len(value)
        self._record_store_event(new_node)
        return new_node

    def _iteratively_delete_tombstone_leaf(
        self,
        node: TreeNode,
        borrowed_only: bool = False,
        preferred_borrowed_only: bool = False,
    ) -> Tuple[TreeNode, int]:
        full_num_evicted = 0
        while node.parent.swa_tombstone and len(node.parent.children) == 0:
            # root node is not evictable
            if node.parent == self.root_node:
                break
            # if locked, means node is in use, skip
            if node.parent.full_lock_ref > 0:
                break
            if borrowed_only and not node.parent.full_borrowed:
                break
            if preferred_borrowed_only and not node.parent.full_preferred_borrowed:
                break
            assert (
                node.parent.swa_lock_ref == 0
            ), f"tombstone swa_lock_ref should always be 0, {node.parent.full_lock_ref=}, {node.parent.swa_lock_ref=}, {node.parent.id=}"
            # delete tombstone node evicts full tokens
            self._record_remove_event(node.parent)
            self._record_elastic_ghost_eviction(node.parent)
            self.token_to_kv_pool_allocator.free(node.parent.value)
            full_num_evicted += len(node.parent.value)
            self.full_lru_list.remove_node(node.parent)
            self._delete_tombstone_leaf(node.parent)
            node = node.parent

        return node, full_num_evicted

    def _delete_leaf(self, node: TreeNode) -> None:
        assert len(node.children) == 0, f"leaf node has children, {node.id=}"
        self._record_elastic_ghost_eviction(node)
        key = node.key.child_key(self.page_size)
        v = node.parent.children.pop(key, None)
        assert v == node, f"parent does not have child key, {key}"
        self.full_evictable_size_ -= len(node.key)
        if node.cache_region in self.region_full_used_tokens:
            self.region_full_used_tokens[node.cache_region] -= len(node.key)
            if node.full_borrowed:
                self.region_full_borrowed_tokens[node.cache_region] -= len(node.key)
            if node.full_preferred_borrowed:
                self.region_full_preferred_borrowed_tokens[node.cache_region] -= len(
                    node.key
                )
        # Tombstoned leaves were never (re-)added to swa_lru_list and were
        # already removed from swa_evictable_size_ when they were tombstoned.
        if not node.swa_tombstone:
            self.swa_evictable_size_ -= len(node.key)
            if node.cache_region in self.region_swa_used_tokens:
                self.region_swa_used_tokens[node.cache_region] -= len(node.key)
                if node.swa_borrowed:
                    self.region_swa_borrowed_tokens[node.cache_region] -= len(
                        node.key
                    )
                if node.swa_preferred_borrowed:
                    self.region_swa_preferred_borrowed_tokens[node.cache_region] -= len(
                        node.key
                    )

    def _tombstone_internal_node(self, node: TreeNode) -> None:
        assert len(node.children) != 0, f"Cannot tombstone a leaf node, {node.id=}"
        node.swa_tombstone = True
        self.swa_evictable_size_ -= len(node.key)
        if node.cache_region in self.region_swa_used_tokens:
            self.region_swa_used_tokens[node.cache_region] -= len(node.key)
            if node.swa_borrowed:
                self.region_swa_borrowed_tokens[node.cache_region] -= len(node.key)
            if node.swa_preferred_borrowed:
                self.region_swa_preferred_borrowed_tokens[node.cache_region] -= len(
                    node.key
                )

    def _delete_tombstone_leaf(self, node: TreeNode) -> None:
        assert (
            node.swa_tombstone
        ), f"Deleting a unexpected non-tombstone leaf node, {node.id=}"
        assert len(node.children) == 0, f"leaf node has children, {node.id=}"
        self._record_elastic_ghost_eviction(node)
        key = node.key.child_key(self.page_size)
        v = node.parent.children.pop(key, None)
        assert v == node, f"parent does not have child key, {key}"

        self.full_evictable_size_ -= len(node.key)
        if node.cache_region in self.region_full_used_tokens:
            self.region_full_used_tokens[node.cache_region] -= len(node.key)
            if node.full_borrowed:
                self.region_full_borrowed_tokens[node.cache_region] -= len(node.key)
            if node.full_preferred_borrowed:
                self.region_full_preferred_borrowed_tokens[node.cache_region] -= len(
                    node.key
                )

    def _collect_nontombstone_nodes(self) -> List[TreeNode]:
        ret_list = []
        stack = [self.root_node]

        while stack:
            cur_node = stack.pop()
            if not cur_node.swa_tombstone:
                ret_list.append(cur_node)
            stack.extend(cur_node.children.values())

        return ret_list

    def _collect_all_nodes(self) -> List[TreeNode]:
        ret_list = []
        stack = [self.root_node]
        while stack:
            cur_node = stack.pop()
            ret_list.append(cur_node)
            stack.extend(cur_node.children.values())
        return ret_list

    def _print_helper(self, node: TreeNode, indent: int) -> None:
        """Prints the radix tree in a human-readable format."""
        stack = [(node, indent)]
        while stack:
            current_node, current_indent = stack.pop()
            print(
                " " * current_indent,
                current_node.id,
                len(current_node.key),
                f"fr={current_node.full_lock_ref}",
                f"sr={current_node.swa_lock_ref}",
                f"fll={self.full_lru_list.in_list(current_node)}",
                f"sll={self.swa_lru_list.in_list(current_node)}",
                f"ts={current_node.swa_tombstone}",
            )
            for key, child in current_node.children.items():
                stack.append((child, current_indent + 2))

                assert key == child.key.child_key(
                    self.page_size
                ), f"{key=}, {child.key.child_key(self.page_size)=}"

    def _total_size_helper(self) -> Tuple[int, int]:
        total_size = 0
        total_swa_size = 0
        stack = [self.root_node]
        while stack:
            current_node = stack.pop()
            total_size += len(current_node.value)
            if not current_node.swa_tombstone:
                total_swa_size += len(current_node.value)
            for child in current_node.children.values():
                if child.evicted:
                    continue
                stack.append(child)
        return total_size, total_swa_size
