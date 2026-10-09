"""Execute changing Agent budgets without changing native cache legality.

This is an execution contract, not a partition ratio controller. The caller
supplies hard budgets and serializes observation, eviction and admission on the
scheduler thread. ``ensure_capacity`` must succeed before new allocation, and
``enforce`` must run again after insertion/completion/unlock. Physical allocator
capacity remains unchanged. Soft boundaries alone never force a free.

All quantities are token slots in their respective physical pools, including
active KV outside the radix tree. Protection revocation is not physical free.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PoolTokens:
    full: int = 0
    swa: int = 0

    def __post_init__(self):
        for value in (self.full, self.swa):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Pool quantities must be nonnegative integer token slots")

    def as_dict(self):
        return {"full": self.full, "swa": self.swa}

    @property
    def any(self):
        return self.full > 0 or self.swa > 0


ZERO = PoolTokens()


def _add(a, b):
    return PoolTokens(a.full + b.full, a.swa + b.swa)


def _remaining(a, b):
    return PoolTokens(max(0, a.full - b.full), max(0, a.swa - b.swa))


def _maximum(a, b):
    return PoolTokens(max(a.full, b.full), max(a.swa, b.swa))


def _minimum(a, b):
    return PoolTokens(min(a.full, b.full), min(a.swa, b.swa))


@dataclass(frozen=True)
class BudgetObservation:
    resident: PoolTokens
    locked: PoolTokens
    evictable: PoolTokens
    legal_candidates: PoolTokens

    def __post_init__(self):
        for pool in ("full", "swa"):
            resident = getattr(self.resident, pool)
            locked, evictable = getattr(self.locked, pool), getattr(self.evictable, pool)
            if locked > resident or evictable > resident or locked + evictable > resident:
                raise ValueError("Locked/evictable observations exceed actual resident KV")

    def as_dict(self):
        return {name: getattr(self, name).as_dict() for name in (
            "resident", "locked", "evictable", "legal_candidates")}


class ResizableAgentBudget:
    """Execute externally selected budgets and account only physical releases.

    ``evict(requested, scope)`` delegates to native eviction and returns its
    reported PoolTokens (or None if unavailable). ``observe`` is authoritative;
    discrepancies are retained in ``accounting_ok`` rather than counted as free.
    A restricted scope must be enforced by that callback, never ignored.

    Explicit ``release`` arguments are new return obligations. Unfulfilled
    obligations persist across later ``enforce()`` calls and are reduced by any
    real free, including a native eviction's cross-pool cascade. Reserve is only
    for this admission attempt and does not manufacture a lasting return debt.
    ``locked_shortfall`` is the lower bound from locked/active slots plus reserve
    exceeding the hard budget; it does not attribute every explicit return debt
    to locks. A larger debt under a roomy hard budget may therefore report zero.
    """

    def __init__(self, observe: Callable[[], BudgetObservation], evict,
                 initial_budget: PoolTokens, frontier=None,
                 protection_cap: PoolTokens | None = None, max_eviction_calls=64):
        if not isinstance(initial_budget, PoolTokens):
            raise TypeError("initial_budget must be PoolTokens")
        if not isinstance(max_eviction_calls, int) or max_eviction_calls < 1:
            raise ValueError("max_eviction_calls must be positive")
        self.observe, self.evict = observe, evict
        self.hard_budget, self.soft_boundary = initial_budget, None
        self.frontier = frontier
        self.protection_cap = protection_cap
        if self._protects:
            original_cap = PoolTokens(int(frontier.full_budget), int(frontier.swa_budget))
            self.protection_cap = original_cap if self.protection_cap is None else _minimum(
                original_cap, self.protection_cap)
        self.version = -1
        self.pending_release = ZERO
        self.pending_scope = None
        self.max_eviction_calls = max_eviction_calls
        self._trim_protection()

    @property
    def _protects(self):
        return self.frontier is not None and bool(getattr(self.frontier, "enabled", False))

    def _trim_protection(self):
        if not self._protects:
            return {"enabled": False, "units": 0, "dependency_tokens": ZERO.as_dict(),
                    "limits": ZERO.as_dict()}
        limits = _minimum(self.protection_cap, self.hard_budget)
        # v1 requires positive limits during construction, but its existing
        # trim loop correctly revokes every nonempty unit at a zero limit.
        self.frontier.full_budget, self.frontier.swa_budget = limits.full, limits.swa
        self.frontier.trim_budget()
        return {"enabled": True, "units": len(self.frontier.units),
                "dependency_tokens": PoolTokens(int(self.frontier.full_tokens),
                                                int(self.frontier.swa_tokens)).as_dict(),
                "limits": limits.as_dict()}

    def _advance_version(self, version):
        if isinstance(version, bool) or not isinstance(version, int) or version <= self.version:
            raise ValueError("Budget versions must strictly increase")
        self.version = version

    def update_budget(self, full, swa, version, soft_boundary=None, scope=None, enforce=True):
        new_budget = PoolTokens(full, swa)
        if soft_boundary is not None and not isinstance(soft_boundary, PoolTokens):
            raise TypeError("soft_boundary must be PoolTokens")
        if self.pending_release.any and scope is not None and scope != self.pending_scope:
            raise ValueError("Outstanding return obligation must keep its eviction scope")
        previous = self.hard_budget
        self._advance_version(version)
        self.hard_budget = new_budget
        if soft_boundary is not None:
            self.soft_boundary = soft_boundary
        protection = self._trim_protection()
        result = self.enforce(scope=scope) if enforce else self._status_without_free()
        result.update({"event_type": "hard_budget_update", "previous_hard_budget": previous.as_dict(),
                       "protection_after_budget_trim": protection})
        return result

    def update_soft_boundary(self, full, swa, version):
        boundary = PoolTokens(full, swa)
        self._advance_version(version)
        self.soft_boundary = boundary
        result = self._status_without_free()
        result["event_type"] = "soft_boundary_update"
        return result

    def _base_result(self, before, after, reserve, requested, released, calls, audits,
                     stop_reason, protection):
        capacity_shortfall = _remaining(_add(after.resident, reserve), self.hard_budget)
        shortfall = _maximum(capacity_shortfall, self.pending_release)
        locked_shortfall = _minimum(shortfall,
                                    _remaining(_add(after.locked, reserve), self.hard_budget))
        return {"schema": "agentkv.resizable_agent_budget.v1", "budget_version": self.version,
                "hard_budget": self.hard_budget.as_dict(),
                "soft_boundary": self.soft_boundary.as_dict() if self.soft_boundary else None,
                "before": before.as_dict(), "after": after.as_dict(),
                "reserve": reserve.as_dict(), "requested_release": requested.as_dict(),
                "released": released.as_dict(), "capacity_shortfall": capacity_shortfall.as_dict(),
                "pending_return": self.pending_release.as_dict(), "shortfall": shortfall.as_dict(),
                "locked_shortfall": locked_shortfall.as_dict(), "complete": not shortfall.any,
                "eviction_calls": calls, "eviction_audit": audits,
                "accounting_ok": all(a["reported_matches_observed"] is not False for a in audits),
                "stop_reason": stop_reason, "protection": protection}

    def _status_without_free(self):
        state = self.observe()
        return self._base_result(state, state, ZERO, ZERO, ZERO, 0, [], "not_enforced",
                                 self._trim_protection())

    def enforce(self, reserve=ZERO, release=ZERO, scope=None):
        if not isinstance(reserve, PoolTokens) or not isinstance(release, PoolTokens):
            raise TypeError("reserve and release must be PoolTokens")
        if self.pending_release.any:
            if scope is None:
                scope = self.pending_scope
            elif scope != self.pending_scope:
                raise ValueError("Outstanding return obligation must keep its eviction scope")
        elif release.any:
            self.pending_scope = scope
        protection = self._trim_protection()
        before = state = self.observe()
        self.pending_release = _add(self.pending_release, release)
        requested = _maximum(_remaining(_add(state.resident, reserve), self.hard_budget),
                             self.pending_release)
        audits, total = [], ZERO
        stop_reason = "complete"
        for _ in range(self.max_eviction_calls):
            needed = _maximum(_remaining(_add(state.resident, reserve), self.hard_budget),
                              self.pending_release)
            if not needed.any:
                break
            reported = self.evict(needed, scope)
            after = self.observe()
            if after.resident.full > state.resident.full or after.resident.swa > state.resident.swa:
                raise RuntimeError("Resident KV grew during eviction; serialize budget execution")
            actual = _remaining(state.resident, after.resident)
            if reported is not None and not isinstance(reported, PoolTokens):
                raise TypeError("Native evict must report PoolTokens or None")
            audits.append({"requested": needed.as_dict(), "observed_release": actual.as_dict(),
                           "reported_release": reported.as_dict() if reported is not None else None,
                           "reported_matches_observed": reported == actual if reported is not None else None})
            total = _add(total, actual)
            self.pending_release = _remaining(self.pending_release, actual)
            state = after
            if not actual.any:
                stop_reason = "native_no_progress"
                break
        else:
            stop_reason = "call_limit"
        remaining = _maximum(_remaining(_add(state.resident, reserve), self.hard_budget),
                             self.pending_release)
        if not remaining.any:
            stop_reason = "complete"
        if not self.pending_release.any:
            self.pending_scope = None
        if remaining.any and _remaining(_add(state.locked, reserve), self.hard_budget).any:
            stop_reason = "locked_or_active"
        elif remaining.any and all(getattr(state.legal_candidates, pool) == 0
                 for pool in ("full", "swa") if getattr(remaining, pool)):
            stop_reason = "no_legal_candidates"
        result = self._base_result(before, state, reserve, requested, total, len(audits), audits,
                                   stop_reason, self._trim_protection())
        result["event_type"] = "enforce"
        result["protection_before_eviction"] = protection
        return result

    def ensure_capacity(self, full_needed, swa_needed, scope=None):
        reserve = PoolTokens(full_needed, swa_needed)
        if reserve.full > self.hard_budget.full or reserve.swa > self.hard_budget.swa:
            state = self.observe()
            return self._base_result(state, state, reserve, ZERO, ZERO, 0, [],
                                     "reserve_exceeds_budget", self._trim_protection())
        return self.enforce(reserve=reserve, scope=scope)


def from_unified_cache(cache, initial_budget, frontier=None, protection_cap=None,
                       evict_params_factory=None):
    """Agent-only device Full/SWA adapter using official allocator and evict.

    Mixed partitions require their own attributed occupancy and scoped evict
    callbacks. This adapter explicitly rejects a restricted scope and HiCache.
    Allocator occupancy includes in-flight KV not yet represented by tree nodes;
    such KV is non-reclaimable until the native scheduler makes it evictable.
    Call outside native allocator free groups, so reported frees have become
    available slots before the after-observation is taken.
    """
    components = {getattr(ct, "name", "").lower(): ct for ct in cache.tree_components}
    if set(components) != {"full", "swa"} or getattr(cache, "cache_controller", None) is not None:
        raise ValueError("Default adapter requires device-only Full/SWA Agent-only cache")
    allocator = cache.token_to_kv_pool_allocator
    if evict_params_factory is None:
        from sglang.srt.mem_cache.base_prefix_cache import EvictParams
        evict_params_factory = EvictParams

    def observe():
        if any(not getattr(pool, "is_not_in_free_group", True) for pool in (
            allocator, getattr(allocator, "full_attn_allocator", None),
            getattr(allocator, "swa_attn_allocator", None))):
            raise RuntimeError("Budget execution must run outside native allocator free groups")
        resident = PoolTokens(int(allocator.size_full - allocator.full_available_size()),
                              int(allocator.size_swa - allocator.swa_available_size()))
        evictable = PoolTokens(int(cache.full_evictable_size()), int(cache.swa_evictable_size()))
        tree_locked = PoolTokens(int(cache.full_protected_size()), int(cache.swa_protected_size()))
        tree = _add(tree_locked, evictable)
        # Allocation outside tree is held by active requests or pending insertion.
        active = _remaining(resident, tree)
        locked = _add(tree_locked, active)
        swa_ct = components["swa"]
        swa_candidates = sum(1 for node in cache.lru_lists[swa_ct].cache.values()
                             if node.component_data[swa_ct].value is not None
                             and node.component_data[swa_ct].lock_ref == 0)
        candidates = PoolTokens(len(cache.evictable_device_leaves), swa_candidates)
        return BudgetObservation(resident, locked, evictable, candidates)

    def evict(requested, scope):
        if scope not in (None, "all"):
            raise ValueError("Default Agent-only adapter cannot enforce a restricted eviction scope")
        result = cache.evict(evict_params_factory(num_tokens=requested.full,
                                                  swa_num_tokens=requested.swa))
        return PoolTokens(int(result.num_tokens_evicted), int(result.swa_num_tokens_evicted))

    return ResizableAgentBudget(observe, evict, initial_budget, frontier=frontier,
                                protection_cap=protection_cap)
