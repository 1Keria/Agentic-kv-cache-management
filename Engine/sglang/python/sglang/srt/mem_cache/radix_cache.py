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
from sglang.srt.mem_cache.mlp_reuse import MlpReuseMixin, copy_mlp_on_split, init_mlp_fields
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
        if self.request_regions_enabled and not 0.0 < self.request_agent_cache_ratio < 1.0:
            raise ValueError("request_agent_cache_ratio must be between 0 and 1")
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
            self.ensure_region_capacity(getattr(req, "cache_region", None), 0)

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
        self._log_reuse_value_shadow(leaves)
        if getattr(self, "mlp_enabled", False) and leaves:
            self._mlp_net_values(leaves)
        eviction_heap = [(self._get_eviction_priority(node), node) for node in leaves]
        heapq.heapify(eviction_heap)

        num_evicted = 0
        evicted_by_region: dict[str, int] = defaultdict(int)
        while num_evicted < num_tokens and len(eviction_heap):
            _priority, x = heapq.heappop(eviction_heap)

            self.token_to_kv_pool_allocator.free(x.value)
            num_evicted += len(x.value)
            if x.cache_region in self.region_evicted_tokens:
                evicted_by_region[x.cache_region] += len(x.value)
            self._delete_leaf(x)

            if len(x.parent.children) == 0 and x.parent.lock_ref == 0:
                if getattr(self, "mlp_enabled", False) and not getattr(
                    self, "mlp_shadow_only", False
                ):
                    self._mlp_net_values([x.parent])
                new_priority = self._get_eviction_priority(x.parent)
                heapq.heappush(eviction_heap, (new_priority, x.parent))

            self._record_remove_event(x)

        for region, region_tokens in evicted_by_region.items():
            self.region_eviction_count[region] += 1
            self.region_evicted_tokens[region] += region_tokens

        self.update_eviction_metrics(num_evicted, start_time)
        self._mlp_on_evict_end(time.perf_counter() - start_time, full=num_evicted)
        self._record_evict_end_diagnostic(num_evicted)
        return EvictResult(num_tokens_evicted=num_evicted)

    def ensure_region_capacity(self, region: Optional[str], num_tokens: int) -> None:
        if not self.request_regions_enabled or region not in self.region_used_tokens:
            return
        if num_tokens < 0:
            return
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        if total_capacity <= 0:
            return
        quota = (
            int(total_capacity * self.request_agent_cache_ratio)
            if region == "agent"
            else total_capacity - int(total_capacity * self.request_agent_cache_ratio)
        )
        overage = self.region_used_tokens[region] + num_tokens - quota
        if overage > 0:
            self.evict(EvictParams(num_tokens=overage, region=region))

    def region_stats(self) -> dict[str, dict[str, int]]:
        """Return token usage and evictable usage for observability/tests."""
        total_capacity = int(getattr(self.token_to_kv_pool_allocator, "size", 0))
        agent_capacity = int(total_capacity * self.request_agent_cache_ratio)
        stats = {
            region: {
                "capacity_tokens": (
                    agent_capacity if region == "agent" else total_capacity - agent_capacity
                ),
                "used_tokens": used,
                "evictable_tokens": 0,
                "eviction_count": self.region_eviction_count[region],
                "evicted_tokens": self.region_evicted_tokens[region],
            }
            for region, used in self.region_used_tokens.items()
        }
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
        child.parent = new_node
        child.key = child.key[split_len:]
        child.value = child.value[split_len:].clone()
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
            new_node = TreeNode(priority=priority)
            new_node.parent = node
            new_node.key = key
            new_node.value = value.clone()
            new_node.prefix_depth = node.prefix_depth + len(key)
            new_node.cache_region = region
            self._mlp_stamp_new_node(new_node)
            if self.reuse_value_enabled:
                self._initialize_reuse_value_node(new_node, node)
                self._record_reuse_value_insert(len(key))
                # A node must not be aged by the KV tokens used to create it.
                new_node.last_turnover = self.reuse_value_global_turnover
            if self._demote_on_miss() and not chunked:
                new_node.hit_count = -1
            else:
                self._inc_hit_count(new_node, chunked)
            node.children[child_key] = new_node
            node = new_node
            self.evictable_size_ += len(key)
            if self.request_regions_enabled and region in self.region_used_tokens:
                self.region_used_tokens[region] += len(key)
            self._update_leaf_status(new_node.parent)
            self._update_leaf_status(new_node)
            # Hash will be computed lazily during event emission
            self._record_store_event(new_node)
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
