from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Tuple, Union

if TYPE_CHECKING:
    from sglang.srt.mem_cache.radix_cache import TreeNode


class EvictionStrategy(ABC):
    @abstractmethod
    def get_priority(self, node: "TreeNode") -> Union[float, Tuple]:
        pass


class LRUStrategy(EvictionStrategy):
    def get_priority(self, node: "TreeNode") -> float:
        return node.last_access_time


class LFUStrategy(EvictionStrategy):
    def get_priority(self, node: "TreeNode") -> Tuple[int, float]:
        return (node.hit_count, node.last_access_time)


class FIFOStrategy(EvictionStrategy):
    def get_priority(self, node: "TreeNode") -> float:
        return node.creation_time


class MRUStrategy(EvictionStrategy):
    def get_priority(self, node: "TreeNode") -> float:
        return -node.last_access_time


class FILOStrategy(EvictionStrategy):
    def get_priority(self, node: "TreeNode") -> float:
        return -node.creation_time


class PriorityStrategy(EvictionStrategy):
    """Priority-aware eviction: lower priority values evicted first, then LRU within same priority."""

    def get_priority(self, node: "TreeNode") -> Tuple[int, float]:
        # Return (priority, last_access_time) so lower priority nodes are evicted first
        return (node.priority, node.last_access_time)


class AgenticStrategy(EvictionStrategy):
    """LFU ranking with miss demotion for agentic / prefix-reuse workloads.

    Eviction key is the same as LFU: ``(hit_count, last_access_time)``.
    Insert-path updates (see radix / unified insert helpers):

    * matched (hit) nodes: ``hit_count += 1`` (same as LFU)
    * if the request still has unmatched pages (miss suffix):
      - each matched node on this path: ``hit_count -= 1``
      - newly inserted miss leaf: ``hit_count = -1`` (no free +1)

    So relative to LFU, a partial-hit request demotes path priority by 1 and
    cold miss blocks start below zero.
    """

    demote_on_miss: bool = True

    def get_priority(self, node: "TreeNode") -> Tuple[int, float]:
        return (node.hit_count, node.last_access_time)


class ReuseValueStrategy(EvictionStrategy):
    """Evict lower per-token reuse value first, then use LRU as a tie-breaker.

    ``RadixCache`` materializes ``node.reuse_value_density`` against the
    current cache-turnover counter immediately before calling this strategy.
    Keeping the strategy itself stateless preserves the existing eviction API.
    """

    uses_reuse_value: bool = True

    def get_priority(self, node: "TreeNode") -> Tuple[float, float]:
        return (node.reuse_value_density, node.last_access_time)


class MlpReuseStrategy(EvictionStrategy):
    """Evict lower NetValue first: (π − λ) × KVSize, then lower π, then larger KV.

    ``RadixCache`` / ``SWARadixCache`` materialize ``node.mlp_net_value`` and
    ``node.mlp_pi`` immediately before calling this strategy.
    """

    uses_mlp: bool = True

    def get_priority(self, node: "TreeNode") -> Tuple[float, float, int]:
        from sglang.srt.mem_cache.mlp_reuse import mlp_victim_sort_key

        return mlp_victim_sort_key(node)


class SLRUStrategy(EvictionStrategy):
    def __init__(self, protected_threshold: int = 2):
        self.protected_threshold = protected_threshold

    def get_priority(self, node: "TreeNode") -> Tuple[int, float]:
        # Priority Logic:
        # Smaller value = Evicted earlier.
        #
        # Segment 0 (Probationary): hit_count < threshold
        # Segment 1 (Protected): hit_count >= threshold
        #
        # Tuple comparison: (segment, last_access_time)
        # Nodes in segment 0 will always be evicted before segment 1.
        # Inside the same segment, older nodes (smaller time) are evicted first.

        is_protected = 1 if node.hit_count >= self.protected_threshold else 0
        return (is_protected, node.last_access_time)
