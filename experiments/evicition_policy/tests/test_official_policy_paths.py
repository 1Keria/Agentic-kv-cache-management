from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
import unittest

import sglang
from sglang.srt.mem_cache.base_prefix_cache import EvictParams
from sglang.srt.mem_cache.evict_policy import LFUStrategy, LRUStrategy, SLRUStrategy
from sglang.srt.mem_cache.unified_cache_components.full_component import FullComponent
from sglang.srt.mem_cache.unified_cache_components.swa_component import SWAComponent
from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache


@dataclass(eq=False)
class Node:
    name: str
    last_access_time: float
    hit_count: int
    parent: object = None
    component_data: dict = field(default_factory=lambda: {ComponentType.SWA: SimpleNamespace(value=[1])})


class OfficialPolicyTest(unittest.TestCase):
    def test_import_is_isolated(self):
        self.assertTrue(Path(sglang.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1] / "runtime/venv"))

    def test_full_eviction_calls_selected_strategy(self):
        for strategy, expected in [(LRUStrategy(), "old_hot"), (LFUStrategy(), "new_cold"), (SLRUStrategy(), "middle_probation")]:
            with self.subTest(strategy=type(strategy).__name__):
                nodes = [Node("old_hot", 1, 10), Node("middle_probation", 2, 1), Node("new_cold", 3, 0)]
                victims = []
                cache = SimpleNamespace(eviction_strategy=strategy, evictable_device_leaves=set(nodes))
                def evict(node, tracker):
                    cache.evictable_device_leaves.remove(node)
                    victims.append(node.name)
                    tracker[ComponentType.FULL] += 256
                cache._evict_device_leaf = evict
                component = FullComponent.__new__(FullComponent)
                component.cache = cache
                component.drive_eviction(EvictParams(num_tokens=256), defaultdict(int))
                self.assertEqual(victims, [expected])

    def test_parent_enters_full_candidate_heap_after_child_eviction(self):
        parent = Node("parent", 2, 0)
        child = Node("child", 1, 0, parent=parent)
        cache = SimpleNamespace(eviction_strategy=LRUStrategy(), evictable_device_leaves={child})
        victims = []
        def evict(node, tracker):
            cache.evictable_device_leaves.remove(node)
            victims.append(node.name)
            if node.parent is not None:
                cache.evictable_device_leaves.add(node.parent)
            tracker[ComponentType.FULL] += 256
        cache._evict_device_leaf = evict
        component = FullComponent.__new__(FullComponent)
        component.cache = cache
        component.drive_eviction(EvictParams(num_tokens=512), defaultdict(int))
        self.assertEqual(victims, ["child", "parent"])

    def test_slru_threshold_is_two_without_segment_size_parameter(self):
        policy = SLRUStrategy()
        self.assertEqual(policy.protected_threshold, 2)
        self.assertEqual(policy.get_priority(Node("one_hit", 9, 1)), (0, 9))
        self.assertEqual(policy.get_priority(Node("two_hits", 1, 2)), (1, 1))

    def test_locked_node_is_not_a_legal_device_leaf(self):
        cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
        cache.root_node = object()
        node = SimpleNamespace(evicted=False, component_data=[SimpleNamespace(lock_ref=1)], children={})
        self.assertFalse(cache._is_device_leaf(node))
        node.component_data[0].lock_ref = 0
        self.assertTrue(cache._is_device_leaf(node))

    def test_swa_driver_uses_lru_not_selected_score(self):
        old_hot = Node("old_hot", 1, 10)
        new_cold = Node("new_cold", 2, 0)
        ordering = [old_hot, new_cold]
        lru = SimpleNamespace(get_lru_no_lock=lambda: ordering[0] if ordering else None,
                              in_list=lambda node: node in ordering,
                              get_prev_no_lock=lambda node: ordering[ordering.index(node) + 1] if ordering.index(node) + 1 < len(ordering) else None)
        def reject_score(node):
            raise AssertionError("SWA should not invoke the configured scoring strategy")
        cache = SimpleNamespace(lru_lists={ComponentType.SWA: lru}, evictable_device_leaves=set(ordering),
                                eviction_strategy=SimpleNamespace(get_priority=reject_score))
        victims = []
        def evict(node, tracker):
            ordering.remove(node)
            cache.evictable_device_leaves.remove(node)
            tracker[ComponentType.SWA] += 256
            victims.append(node.name)
        cache._evict_device_leaf = evict
        component = SWAComponent.__new__(SWAComponent)
        component.cache = cache
        component.drive_eviction(EvictParams(num_tokens=0, swa_num_tokens=256), defaultdict(int))
        self.assertEqual(victims, ["old_hot"])


if __name__ == "__main__":
    unittest.main()
