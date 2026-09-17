"""Unit tests for MLP eviction on SWARadixCache (V4Flash path)."""

from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=6, suite="base-a-test-cpu")

import unittest
from array import array
from types import SimpleNamespace

import torch

from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import EvictParams, InsertParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.mlp_reuse import (
    FEATURE_NAMES,
    _SessionSide,
    compose_pi,
    mlp_swa_victim_sort_key,
    mlp_victim_sort_key,
)
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.swa_radix_cache import SWARadixCache


class FakeSWAAllocator(SWATokenToKVPoolAllocator):
    def __init__(self, size=100):
        self._size_full = size
        self._size_swa = size
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


class AliveScorer:
    horizons_s = [5.0, 14.0, 23.0]

    def score(self, x):
        # session_alive is feature 7; broadcast to K horizons
        alive = x[:, 7:8]
        return alive.repeat(1, 3)


def _make_cache(**kwargs):
    return SWARadixCache(
        CacheInitParams(
            disable=False,
            req_to_token_pool=None,
            token_to_kv_pool_allocator=FakeSWAAllocator(kwargs.get("size", 100)),
            page_size=1,
            sliding_window_size=8,
            eviction_policy=kwargs.get("eviction_policy", "lru"),
        )
    )


class TestSWAMlpEvict(unittest.TestCase):
    def test_feature_layout(self):
        self.assertEqual(len(FEATURE_NAMES), 16)
        self.assertEqual(FEATURE_NAMES[7], "session_alive")

    def test_evicts_dead_session_leaf(self):
        cache = _make_cache()
        cache.mlp_enabled = True
        cache.mlp_shadow_only = False
        cache.mlp_scorer = AliveScorer()
        cache.mlp_hold_lambda = 0.0
        cache.mlp_delta_alpha = [1.0, 0.7, 0.5]
        cache.mlp_sessions = {
            "alive": _SessionSide(hops=2, traffic_class="glm", ended=False),
            "dead": _SessionSide(hops=1, traffic_class="request", ended=True),
        }

        live_key = RadixKey(array("q", [1, 2]))
        dead_key = RadixKey(array("q", [3, 4]))
        cache.insert(InsertParams(key=live_key, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=dead_key, value=torch.tensor([30, 40])))
        live = cache.root_node.children[live_key.child_key(1)]
        dead = cache.root_node.children[dead_key.child_key(1)]
        live.mlp_last_session_id = "alive"
        dead.mlp_last_session_id = "dead"

        result = cache.evict(EvictParams(num_tokens=2))
        self.assertEqual(result.num_tokens_evicted, 2)
        self.assertNotIn(dead_key.child_key(1), cache.root_node.children)
        self.assertIn(live_key.child_key(1), cache.root_node.children)

    def test_note_match_stamps_session(self):
        cache = _make_cache()
        cache.mlp_enabled = True
        cache.mlp_shadow_only = False
        cache.mlp_scorer = AliveScorer()
        key = RadixKey(array("q", [1, 2, 3]))
        cache.insert(InsertParams(key=key, value=torch.tensor([10, 20, 30])))
        req = SimpleNamespace(
            rid="r1",
            sampling_params=SimpleNamespace(
                custom_params={
                    "session_id": "s1",
                    "turn_idx": 2,
                    "traffic_class": "openhands",
                    "has_tools": True,
                }
            ),
        )
        from sglang.srt.mem_cache.base_prefix_cache import MatchPrefixParams

        cache.match_prefix(MatchPrefixParams(key=key, req=req))
        leaf = cache.root_node
        while leaf.children:
            leaf = next(iter(leaf.children.values()))
        self.assertEqual(leaf.mlp_last_session_id, "s1")
        self.assertEqual(cache.mlp_sessions["s1"].hops, 3)
        self.assertTrue(cache.mlp_sessions["s1"].has_tools)

    def test_compose_pi_uses_increments(self):
        p = torch.tensor([[0.2, 0.5, 0.8], [0.8, 0.8, 0.8], [0.0, 0.0, 0.0]])
        pi = compose_pi(p, [1.0, 0.7, 0.5])
        # Δp = (0.2, 0.3, 0.3) → 0.2 + 0.21 + 0.15 = 0.56
        self.assertAlmostEqual(pi[0].item(), 0.56, places=5)
        # Δp = (0.8, 0, 0) → 0.8
        self.assertAlmostEqual(pi[1].item(), 0.8, places=5)
        self.assertAlmostEqual(pi[2].item(), 0.0, places=5)
        equal = compose_pi(p[:1], [1.0, 1.0, 1.0])
        self.assertAlmostEqual(equal[0].item(), 0.8, places=5)

    def test_victim_key_pi_then_size_not_lru(self):
        low_pi = SimpleNamespace(
            mlp_net_value=0.0, mlp_pi=0.1, value=[0] * 2, last_access_time=99.0
        )
        high_pi = SimpleNamespace(
            mlp_net_value=0.0, mlp_pi=0.4, value=[0] * 2, last_access_time=1.0
        )
        self.assertLess(mlp_victim_sort_key(low_pi), mlp_victim_sort_key(high_pi))
        big = SimpleNamespace(
            mlp_net_value=0.0, mlp_pi=0.1, value=[0] * 10, last_access_time=1.0
        )
        small = SimpleNamespace(
            mlp_net_value=0.0, mlp_pi=0.1, value=[0] * 2, last_access_time=99.0
        )
        self.assertLess(mlp_victim_sort_key(big), mlp_victim_sort_key(small))

    def test_evict_rescores_remaining_leaves(self):
        class CountingScorer(AliveScorer):
            def __init__(self):
                self.calls = 0
                self.batch_sizes = []

            def score(self, x):
                self.calls += 1
                self.batch_sizes.append(int(x.shape[0]))
                return super().score(x)

        cache = _make_cache()
        cache.mlp_enabled = True
        cache.mlp_shadow_only = False
        scorer = CountingScorer()
        cache.mlp_scorer = scorer
        cache.mlp_hold_lambda = 0.0
        cache.mlp_delta_alpha = [1.0, 0.7, 0.5]
        cache.mlp_sessions = {
            "alive": _SessionSide(hops=2, traffic_class="glm", ended=False),
            "dead": _SessionSide(hops=1, traffic_class="request", ended=True),
        }
        keys = [
            RadixKey(array("q", [1, 2])),
            RadixKey(array("q", [3, 4])),
            RadixKey(array("q", [5, 6])),
        ]
        for i, key in enumerate(keys):
            cache.insert(InsertParams(key=key, value=torch.tensor([10 + i, 20 + i])))
            node = cache.root_node.children[key.child_key(1)]
            node.mlp_last_session_id = "dead" if i < 2 else "alive"

        result = cache.evict(EvictParams(num_tokens=4))
        self.assertEqual(result.num_tokens_evicted, 4)
        # After each victim the remaining leaves are rescored, including one
        # extra pass after the quota is already met (same loop as LRU).
        self.assertEqual(scorer.calls, 3)
        self.assertEqual(scorer.batch_sizes, [3, 2, 1])

    def test_evict_promoted_parent_instead_of_live_sibling(self):
        cache = _make_cache()
        cache.mlp_enabled = True
        cache.mlp_shadow_only = False
        cache.mlp_scorer = AliveScorer()
        cache.mlp_hold_lambda = 0.0
        cache.mlp_delta_alpha = [1.0, 0.7, 0.5]
        cache.mlp_sessions = {
            "alive": _SessionSide(hops=2, traffic_class="glm", ended=False),
            "dead": _SessionSide(hops=1, traffic_class="request", ended=True),
        }

        live_key = RadixKey(array("q", [1, 2]))
        prefix_key = RadixKey(array("q", [3, 4]))
        ext_key = RadixKey(array("q", [3, 4, 5, 6]))
        cache.insert(InsertParams(key=live_key, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=prefix_key, value=torch.tensor([30, 40])))
        cache.insert(InsertParams(key=ext_key, value=torch.tensor([30, 40, 50, 60])))

        live = cache.root_node.children[live_key.child_key(1)]
        parent = cache.root_node.children[prefix_key.child_key(1)]
        child = next(iter(parent.children.values()))
        live.mlp_last_session_id = "alive"
        parent.mlp_last_session_id = "dead"
        child.mlp_last_session_id = "dead"

        result = cache.evict(EvictParams(num_tokens=4))
        self.assertEqual(result.num_tokens_evicted, 4)
        self.assertIn(live_key.child_key(1), cache.root_node.children)
        self.assertNotIn(prefix_key.child_key(1), cache.root_node.children)

    def test_swa_sort_key_low_pi_then_closer_to_root(self):
        low = SimpleNamespace(
            mlp_pi=0.1,
            mlp_prefix_depth=3,
            mlp_net_value=0.0,
            value=[0] * 2,
        )
        high = SimpleNamespace(
            mlp_pi=0.4,
            mlp_prefix_depth=1,
            mlp_net_value=0.0,
            value=[0] * 2,
        )
        self.assertLess(mlp_swa_victim_sort_key(low), mlp_swa_victim_sort_key(high))
        parent = SimpleNamespace(
            mlp_pi=0.1,
            mlp_prefix_depth=1,
            mlp_net_value=0.5,
            value=[0] * 8,
        )
        child = SimpleNamespace(
            mlp_pi=0.1,
            mlp_prefix_depth=2,
            mlp_net_value=0.1,
            value=[0] * 2,
        )
        self.assertLess(mlp_swa_victim_sort_key(parent), mlp_swa_victim_sort_key(child))

    def _enable_alive_mlp(self, cache):
        cache.mlp_enabled = True
        cache.mlp_shadow_only = False
        cache.mlp_scorer = AliveScorer()
        cache.mlp_hold_lambda = 0.0
        cache.mlp_delta_alpha = [1.0, 0.7, 0.5]
        cache.mlp_sessions = {
            "alive": _SessionSide(hops=2, traffic_class="glm", ended=False),
            "dead": _SessionSide(hops=1, traffic_class="request", ended=True),
        }

    def test_swa_evicts_dead_path_before_live(self):
        cache = _make_cache()
        self._enable_alive_mlp(cache)

        live_prefix = RadixKey(array("q", [1, 2]))
        live_ext = RadixKey(array("q", [1, 2, 3, 4]))
        dead_prefix = RadixKey(array("q", [5, 6]))
        dead_ext = RadixKey(array("q", [5, 6, 7, 8]))
        cache.insert(InsertParams(key=live_prefix, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=live_ext, value=torch.tensor([10, 20, 30, 40])))
        cache.insert(InsertParams(key=dead_prefix, value=torch.tensor([50, 60])))
        cache.insert(InsertParams(key=dead_ext, value=torch.tensor([50, 60, 70, 80])))

        live_parent = cache.root_node.children[live_prefix.child_key(1)]
        live_child = next(iter(live_parent.children.values()))
        dead_parent = cache.root_node.children[dead_prefix.child_key(1)]
        dead_child = next(iter(dead_parent.children.values()))
        live_parent.mlp_last_session_id = "alive"
        live_child.mlp_last_session_id = "alive"
        dead_parent.mlp_last_session_id = "dead"
        dead_child.mlp_last_session_id = "dead"

        result = cache.evict(EvictParams(num_tokens=0, swa_num_tokens=2))
        self.assertEqual(result.swa_num_tokens_evicted, 2)
        self.assertTrue(dead_parent.swa_tombstone)
        self.assertFalse(live_parent.swa_tombstone)
        self.assertFalse(live_child.swa_tombstone)
        self.assertIn(live_prefix.child_key(1), cache.root_node.children)

    def test_swa_same_pi_tombstones_parent_before_child(self):
        cache = _make_cache()
        self._enable_alive_mlp(cache)

        prefix = RadixKey(array("q", [1, 2]))
        ext = RadixKey(array("q", [1, 2, 3, 4]))
        cache.insert(InsertParams(key=prefix, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=ext, value=torch.tensor([10, 20, 30, 40])))
        parent = cache.root_node.children[prefix.child_key(1)]
        child = next(iter(parent.children.values()))
        parent.mlp_last_session_id = "dead"
        child.mlp_last_session_id = "dead"

        result = cache.evict(EvictParams(num_tokens=0, swa_num_tokens=2))
        self.assertEqual(result.swa_num_tokens_evicted, 2)
        self.assertTrue(parent.swa_tombstone)
        self.assertFalse(child.swa_tombstone)
        self.assertIn(prefix.child_key(1), cache.root_node.children)

    def test_swa_internal_pi_uses_max_descendant_leaf(self):
        cache = _make_cache()
        self._enable_alive_mlp(cache)

        prefix = RadixKey(array("q", [1, 2]))
        live_ext = RadixKey(array("q", [1, 2, 3, 4]))
        dead_ext = RadixKey(array("q", [1, 2, 5, 6]))
        cache.insert(InsertParams(key=prefix, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=live_ext, value=torch.tensor([10, 20, 30, 40])))
        cache.insert(InsertParams(key=dead_ext, value=torch.tensor([10, 20, 50, 60])))

        parent = cache.root_node.children[prefix.child_key(1)]
        children = list(parent.children.values())
        self.assertEqual(len(children), 2)
        for child in children:
            toks = list(child.key.token_ids)
            child.mlp_last_session_id = "alive" if toks == [3, 4] else "dead"
        parent.mlp_last_session_id = "alive"

        result = cache.evict(EvictParams(num_tokens=0, swa_num_tokens=2))
        self.assertEqual(result.swa_num_tokens_evicted, 2)
        self.assertFalse(parent.swa_tombstone)
        dead_still = [
            c for c in parent.children.values() if c.mlp_last_session_id == "dead"
        ]
        self.assertEqual(dead_still, [])
        live_still = [
            c for c in parent.children.values() if c.mlp_last_session_id == "alive"
        ]
        self.assertEqual(len(live_still), 1)
        self.assertFalse(live_still[0].swa_tombstone)

    def test_mlp_evict_records_phase_time(self):
        cache = _make_cache()
        self._enable_alive_mlp(cache)
        live_key = RadixKey(array("q", [1, 2]))
        dead_key = RadixKey(array("q", [3, 4]))
        cache.insert(InsertParams(key=live_key, value=torch.tensor([10, 20])))
        cache.insert(InsertParams(key=dead_key, value=torch.tensor([30, 40])))
        cache.root_node.children[live_key.child_key(1)].mlp_last_session_id = "alive"
        cache.root_node.children[dead_key.child_key(1)].mlp_last_session_id = "dead"
        cache.evict(EvictParams(num_tokens=2))
        self.assertGreaterEqual(cache._mlp_evict_n, 1)
        self.assertGreater(cache._mlp_phase_s_total, 0.0)
        self.assertGreater(cache._mlp_evict_s_total, 0.0)
        self.assertLessEqual(cache._mlp_phase_s_total, cache._mlp_evict_s_total + 1e-6)


if __name__ == "__main__":
    unittest.main()
