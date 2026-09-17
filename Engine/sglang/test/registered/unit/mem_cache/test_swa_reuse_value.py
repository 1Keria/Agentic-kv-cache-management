"""Unit tests for reuse_value eviction on SWARadixCache (V4Flash path)."""

from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=6, suite="base-a-test-cpu")
register_cpu_ci(est_time=7, suite="base-b-test-cpu")

import unittest
from array import array

import torch

from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import (
    EvictParams,
    InsertParams,
    MatchPrefixParams,
)
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
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


def _make_cache(**kwargs):
    return SWARadixCache(
        CacheInitParams(
            disable=False,
            req_to_token_pool=None,
            token_to_kv_pool_allocator=FakeSWAAllocator(kwargs.get("size", 100)),
            page_size=1,
            sliding_window_size=8,
            eviction_policy=kwargs.get("eviction_policy", "reuse_value"),
            reuse_value_turnover_kappa=kwargs.get("kappa", float("inf")),
            reuse_value_base_cold_strength=kwargs.get("cold", 1.0),
        )
    )


class TestSWAReuseValue(unittest.TestCase):
    def test_evicts_lower_value_leaf_instead_of_lru(self):
        cache = _make_cache()
        hot_key = RadixKey(array("q", [1, 2]))
        cold_key = RadixKey(array("q", [3, 4]))
        cache.insert(InsertParams(key=hot_key, value=torch.tensor([10, 20])))
        cache.match_prefix(MatchPrefixParams(key=hot_key))
        cache.match_prefix(MatchPrefixParams(key=hot_key))
        cache.insert(InsertParams(key=cold_key, value=torch.tensor([30, 40])))

        result = cache.evict(EvictParams(num_tokens=2))
        self.assertEqual(result.num_tokens_evicted, 2)
        self.assertEqual(
            len(
                cache.match_prefix(
                    MatchPrefixParams(key=cold_key, update_reuse_strength=False)
                ).device_indices
            ),
            0,
        )
        self.assertEqual(
            len(
                cache.match_prefix(
                    MatchPrefixParams(key=hot_key, update_reuse_strength=False)
                ).device_indices
            ),
            2,
        )

    def test_terminal_inheritance(self):
        cache = _make_cache(cold=0.5)
        parent_key = RadixKey(array("q", [1, 2]))
        cache.insert(
            InsertParams(
                key=parent_key,
                value=torch.tensor([10, 20]),
                is_terminal=True,
            )
        )
        parent = cache.root_node.children[parent_key.child_key(1)]
        self.assertEqual(parent.reuse_strength, 0.5)
        self.assertEqual(parent.terminal_count, 1)

        cache.match_prefix(MatchPrefixParams(key=parent_key))
        self.assertEqual(parent.reuse_strength, 1.5)

        cache.insert(
            InsertParams(
                key=RadixKey(array("q", [1, 2, 3, 4])),
                value=torch.tensor([10, 20, 30, 40]),
                is_terminal=True,
            )
        )
        child = parent.children[RadixKey(array("q", [3, 4])).child_key(1)]
        self.assertEqual(child.reuse_strength, parent.reuse_strength)
        self.assertEqual(child.terminal_count, 1)


if __name__ == "__main__":
    unittest.main()
