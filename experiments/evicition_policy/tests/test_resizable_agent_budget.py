"""Physical return, unlock retry and shared protection tests on CPU."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from resizable_agent_budget import (
    BudgetObservation, PoolTokens, ResizableAgentBudget, from_unified_cache,
)
from test_bounded_frontier import CT, fixture


class PhysicalFixture:
    """Finite resident objects: atomic frees, reference locks and partial native returns."""

    def __init__(self, nodes, max_per_call=None):
        self.nodes = [dict(full=full, swa=swa, locked=locked) for full, swa, locked in nodes]
        self.calls = []
        self.max_per_call = max_per_call

    def observe(self):
        resident = PoolTokens(sum(n["full"] for n in self.nodes), sum(n["swa"] for n in self.nodes))
        locked = PoolTokens(sum(n["full"] for n in self.nodes if n["locked"]),
                            sum(n["swa"] for n in self.nodes if n["locked"]))
        evictable = PoolTokens(resident.full - locked.full, resident.swa - locked.swa)
        count = sum(not n["locked"] for n in self.nodes)
        return BudgetObservation(resident, locked, evictable, PoolTokens(count, count))

    def evict(self, requested, scope):
        self.calls.append((requested, scope))
        freed_full = freed_swa = count = 0
        for node in list(self.nodes):
            if freed_full >= requested.full and freed_swa >= requested.swa:
                break
            if node["locked"]:
                continue
            if self.max_per_call is not None and count >= self.max_per_call:
                break
            # Native atomic free also releases the other pool, counted once.
            self.nodes.remove(node)
            freed_full += node["full"]
            freed_swa += node["swa"]
            count += 1
        return PoolTokens(freed_full, freed_swa)


def physical_controller(state, **kwargs):
    return ResizableAgentBudget(state.observe, state.evict, PoolTokens(100, 100), **kwargs)


def frontier_controller(cache, frontier, initial=PoolTokens(100, 100)):
    def observe():
        locked = PoolTokens(cache.component_protected_size_[CT.FULL],
                            cache.component_protected_size_[CT.SWA])
        evictable = PoolTokens(cache.component_evictable_size_[CT.FULL],
                              cache.component_evictable_size_[CT.SWA])
        resident = PoolTokens(locked.full + evictable.full, locked.swa + evictable.swa)
        candidates = PoolTokens(len(cache.evictable_device_leaves),
                               sum(cd.component_data[CT.SWA].lock_ref == 0
                                   for cd in cache.lru_lists[CT.SWA].cache.values()))
        return BudgetObservation(resident, locked, evictable, candidates)

    def evict(requested, scope):
        tracker = {CT.FULL: 0, CT.SWA: 0}
        frontier.drive_full(requested.full, tracker)
        if tracker[CT.SWA] < requested.swa:
            frontier.drive_swa(cache.components[CT.SWA], requested.swa, tracker)
        return PoolTokens(tracker[CT.FULL], tracker[CT.SWA])

    return ResizableAgentBudget(observe, evict, initial, frontier=frontier)


class ResizableBudgetTests(unittest.TestCase):
    def test_shared_dependency_zero_budget_revokes_but_expansion_does_not_resurrect(self):
        cache, frontier = fixture(full_budget_tokens=8, swa_budget_tokens=4)
        common = cache.add([1, 2, 3, 4])
        left, right = cache.add([5, 6], common), cache.add([7, 8], common)
        frontier.register(left)
        frontier.register(right)
        controller = frontier_controller(cache, frontier)
        self.assertEqual((frontier.full_tokens, frontier.swa_tokens), (8, 4))
        zero = controller.update_budget(0, 0, 0, enforce=False)
        self.assertEqual(zero["released"], {"full": 0, "swa": 0})
        self.assertEqual(zero["after"]["resident"], {"full": 8, "swa": 8})
        self.assertEqual((frontier.full_budget, frontier.swa_budget, len(frontier.units)), (0, 0, 0))
        expanded = controller.update_budget(100, 100, 1)
        self.assertTrue(expanded["complete"])
        self.assertEqual((frontier.full_budget, frontier.swa_budget), (8, 4))
        self.assertFalse(frontier.units)
        frontier.register(right)
        self.assertEqual(list(frontier.units), [right.id])

    def test_oversized_single_unit_loses_qualification_and_real_free_meets_budget(self):
        cache, frontier = fixture(full_budget_tokens=20, swa_budget_tokens=10)
        large = cache.add([1, 2, 3, 4, 5, 6])
        frontier.register(large)
        controller = frontier_controller(cache, frontier)
        result = controller.update_budget(4, 100, 0)
        self.assertFalse(frontier.units)
        self.assertEqual(result["protection_after_budget_trim"]["units"], 0)
        self.assertEqual(result["released"], {"full": 6, "swa": 6})
        self.assertTrue(result["accounting_ok"])
        self.assertTrue(result["complete"])

    def test_locked_shortfall_survives_then_unlock_retry_returns_capacity(self):
        state = PhysicalFixture([(8, 4, True), (4, 2, False)])
        controller = physical_controller(state)
        first = controller.update_budget(4, 2, 0)
        self.assertFalse(first["complete"])
        self.assertEqual(first["released"], {"full": 4, "swa": 2})
        self.assertEqual(first["shortfall"], {"full": 4, "swa": 2})
        self.assertEqual(first["locked_shortfall"], first["shortfall"])
        self.assertEqual(first["stop_reason"], "locked_or_active")
        self.assertEqual(len(state.nodes), 1)
        state.nodes[0]["locked"] = False
        second = controller.enforce()
        self.assertTrue(second["complete"])
        self.assertEqual(second["released"], {"full": 8, "swa": 4})

    def test_partial_native_free_retries_actual_residency_until_complete(self):
        state = PhysicalFixture([(4, 2, False)] * 3, max_per_call=1)
        controller = physical_controller(state)
        result = controller.update_budget(4, 2, 0)
        self.assertEqual(result["eviction_calls"], 2)
        self.assertEqual([entry[0] for entry in state.calls], [PoolTokens(8, 4), PoolTokens(4, 2)])
        self.assertEqual(result["released"], {"full": 8, "swa": 4})
        self.assertTrue(result["complete"])

    def test_false_callback_report_does_not_manufacture_physical_release(self):
        state = PhysicalFixture([(8, 4, False)])
        controller = ResizableAgentBudget(state.observe, lambda requested, scope: requested,
                                          PoolTokens(4, 2))
        result = controller.enforce()
        self.assertEqual(result["eviction_calls"], 1)
        self.assertEqual(result["released"], {"full": 0, "swa": 0})
        self.assertFalse(result["accounting_ok"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["shortfall"], {"full": 4, "swa": 2})

    def test_cross_pool_cascade_is_not_requested_or_counted_twice(self):
        state = PhysicalFixture([(8, 4, False), (4, 2, False)])
        controller = physical_controller(state)
        result = controller.update_budget(4, 2, 0)
        self.assertEqual(len(state.calls), 1)
        self.assertEqual(result["released"], {"full": 8, "swa": 4})
        self.assertEqual(result["after"]["resident"], {"full": 4, "swa": 2})

    def test_soft_boundary_decline_does_not_free_or_change_protection_cap(self):
        cache, frontier = fixture(full_budget_tokens=8, swa_budget_tokens=4)
        anchor = cache.add([1, 2, 3, 4])
        frontier.register(anchor)
        controller = frontier_controller(cache, frontier)
        result = controller.update_soft_boundary(0, 0, 0)
        self.assertEqual(result["eviction_calls"], 0)
        self.assertEqual(result["released"], {"full": 0, "swa": 0})
        self.assertEqual((frontier.full_budget, frontier.swa_budget), (8, 4))
        self.assertEqual(list(frontier.units), [anchor.id])

    def test_admission_reserves_actual_new_slots_before_allocation(self):
        state = PhysicalFixture([(8, 4, False), (4, 2, False)])
        controller = physical_controller(state)
        controller.update_budget(12, 6, 0)
        result = controller.ensure_capacity(4, 2)
        self.assertTrue(result["complete"])
        self.assertEqual(result["reserve"], {"full": 4, "swa": 2})
        self.assertEqual(result["after"]["resident"], {"full": 4, "swa": 2})
        state.nodes.append({"full": 4, "swa": 2, "locked": True})
        self.assertTrue(controller.enforce()["complete"])

    def test_request_larger_than_budget_is_rejected_without_destroying_cache(self):
        state = PhysicalFixture([(4, 2, False)])
        controller = physical_controller(state)
        controller.update_budget(4, 2, 0)
        result = controller.ensure_capacity(6, 3)
        self.assertFalse(result["complete"])
        self.assertEqual(result["shortfall"], {"full": 6, "swa": 3})
        self.assertEqual(result["stop_reason"], "reserve_exceeds_budget")
        self.assertEqual(result["eviction_calls"], 0)
        self.assertEqual(len(state.nodes), 1)

    def test_return_debt_is_real_free_and_survives_unrelated_budget_expansion(self):
        state = PhysicalFixture([(8, 4, True)])
        controller = physical_controller(state)
        first = controller.enforce(release=PoolTokens(6, 3))
        self.assertEqual(first["pending_return"], {"full": 6, "swa": 3})
        controller.update_budget(200, 200, 0)
        self.assertEqual(controller.pending_release, PoolTokens(6, 3))
        state.nodes[0]["locked"] = False
        retried = controller.enforce()
        self.assertTrue(retried["complete"])
        self.assertEqual(retried["pending_return"], {"full": 0, "swa": 0})

    def test_stale_version_rejected_before_mutating_or_freeing(self):
        state = PhysicalFixture([(8, 4, False)])
        controller = physical_controller(state)
        controller.update_budget(16, 8, 2)
        with self.assertRaises(ValueError):
            controller.update_budget(0, 0, 1)
        self.assertEqual(controller.hard_budget, PoolTokens(16, 8))
        self.assertFalse(state.calls)

    def test_scoped_return_debt_does_not_silently_expand_on_unlock_retry(self):
        state = PhysicalFixture([(8, 4, True)])
        controller = physical_controller(state)
        controller.enforce(release=PoolTokens(4, 2), scope="borrowed-only")
        with self.assertRaisesRegex(ValueError, "scope"):
            controller.enforce(scope="all")
        state.nodes[0]["locked"] = False
        retried = controller.enforce()
        self.assertTrue(retried["complete"])
        self.assertEqual([scope for _, scope in state.calls], ["borrowed-only", "borrowed-only"])

    def test_swa_limit_alone_applies_same_release_and_cascade_rule(self):
        state = PhysicalFixture([(8, 4, False), (4, 2, False)])
        controller = physical_controller(state)
        result = controller.update_budget(100, 2, 0)
        self.assertEqual(result["requested_release"], {"full": 0, "swa": 4})
        self.assertEqual(result["released"], {"full": 8, "swa": 4})
        self.assertTrue(result["complete"])

    def test_lru_without_frontier_uses_identical_capacity_execution(self):
        state = PhysicalFixture([(8, 4, False), (4, 2, False)])
        controller = physical_controller(state)
        result = controller.update_budget(4, 2, 0)
        self.assertTrue(result["complete"])
        self.assertFalse(result["protection"]["enabled"])

    def test_partial_returns_hit_call_limit_without_claiming_compliance(self):
        state = PhysicalFixture([(4, 2, False)] * 4, max_per_call=1)
        controller = physical_controller(state, max_eviction_calls=1)
        result = controller.update_budget(0, 0, 0)
        self.assertFalse(result["complete"])
        self.assertEqual(result["stop_reason"], "call_limit")
        self.assertEqual(result["released"], {"full": 4, "swa": 2})

    def test_adapter_observes_active_allocator_slots_and_rejects_scope(self):
        allocator = SimpleNamespace(size_full=20, size_swa=10,
                                    full_available_size=lambda: 8, swa_available_size=lambda: 4)
        cache = SimpleNamespace(tree_components=(CT.FULL, CT.SWA), cache_controller=None,
                                token_to_kv_pool_allocator=allocator,
                                full_evictable_size=lambda: 4, swa_evictable_size=lambda: 2,
                                full_protected_size=lambda: 4, swa_protected_size=lambda: 2,
                                evictable_device_leaves={1},
                                lru_lists={CT.SWA: SimpleNamespace(cache={})})
        controller = from_unified_cache(cache, PoolTokens(20, 10),
                                        evict_params_factory=SimpleNamespace)
        observed = controller.observe()
        self.assertEqual(observed.resident, PoolTokens(12, 6))
        self.assertEqual(observed.locked, PoolTokens(8, 4))
        with self.assertRaisesRegex(ValueError, "restricted"):
            controller.enforce(release=PoolTokens(1, 1), scope="borrowed-only")

    def test_invalid_observation_and_negative_budgets_fail_early(self):
        with self.assertRaises(ValueError):
            PoolTokens(-1, 0)
        with self.assertRaises(ValueError):
            BudgetObservation(PoolTokens(1, 1), PoolTokens(1, 1), PoolTokens(1, 0), PoolTokens(1, 1))


if __name__ == "__main__":
    unittest.main()
