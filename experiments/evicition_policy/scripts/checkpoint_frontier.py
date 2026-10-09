"""Protect real prefill checkpoints and downgrade only to resident ancestors.

v1/v2 drivers, locks, physical allocator and Full/SWA dependency guards remain
unchanged. No future input, session, time, or fabricated SWA data is consulted.
"""

from collections import OrderedDict

from retained_frontier import RetainedFrontier


class CheckpointFrontier(RetainedFrontier):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partial_checkpoints = bool(self.settings.get("partial_checkpoints", False))
        self.downgrade = bool(self.settings.get("resident_downgrade", False))

    def committed(self, req, key, finished):
        if not self.partial_checkpoints:
            return super().committed(req, key, finished)
        if not self.active:
            return
        input_target = len(req.origin_input_ids) // self.cache.page_size * self.cache.page_size
        target = min(input_target, len(key) // self.cache.page_size * self.cache.page_size)
        if target <= 0 or target == getattr(req, "agentkv_checkpoint_last_target", None):
            return
        anchor = self.input_anchor(key, target)
        if anchor is None:
            self.counts["input_boundary_absent"] += 1
            return
        req.agentkv_checkpoint_last_target = target
        self.counts["partial_checkpoint_stages" if target < input_target else "complete_checkpoint_stages"] += 1
        self.register(anchor, str(req.rid))

    def alternatives(self, unit):
        path = self.path(unit["anchor"]) or []
        for anchor in path[1:]:
            # A different protected branch may already have downgraded to
            # this shared ancestor. Never overwrite that live unit identity.
            if anchor.id in self.units:
                continue
            dependency = self.dependencies(anchor)
            if dependency is not None:
                yield anchor, dependency

    def union_cost(self, anchor_id, dependency):
        full, swa = set(dependency[0]), set(dependency[1])
        for identity, unit in self.units.items():
            if identity != anchor_id:
                full.update(unit["dependencies"][0])
                swa.update(unit["dependencies"][1])
        return (sum(len(n.component_data[self.full_ct].value) for n in full),
                sum(len(n.component_data[self.swa_ct].value) for n in swa), full, swa)

    def move_to_ancestor(self, anchor_id, anchor, dependency, reason):
        old = self.units[anchor_id]
        old_order = list(self.units)
        predecessor = old["tick"]
        admitted_at, reuses = old["admitted_at"], old["observed_reuses"]
        self.drop(anchor_id, "downgrade_" + reason)
        self.tick += 1
        unit = {"anchor": anchor, "dependencies": dependency, "tick": self.tick,
                "admitted_at": self.request_index, "observed_reuses": 0}
        # Keep its previous retention order. Native budget execution may still
        # revoke it immediately if no legal physical release can make progress.
        self.units[anchor.id] = unit
        self.units = OrderedDict((anchor.id if identity == anchor_id else identity,
                                  unit if identity == anchor_id else self.units[identity])
                                 for identity in old_order)
        self.counts["registered"] += 1
        self.counts["resident_downgrades_" + reason] += 1
        self.log("admit", request_id=None, predecessor_unit_ids=[predecessor],
                 downgrade_reason=reason, predecessor_admitted_at=admitted_at,
                 predecessor_reuses=reuses, **self.unit_fields(unit))
        self.refresh()

    def trim_budget(self):
        self.refresh()
        while self.units and (len(self.units) > self.max_units or self.full_tokens > self.full_budget
                              or self.swa_tokens > self.swa_budget):
            anchor_id = next(iter(self.units))
            choice = None
            if self.downgrade and len(self.units) <= self.max_units:
                old_over = (max(0, self.full_tokens - self.full_budget),
                            max(0, self.swa_tokens - self.swa_budget))
                for anchor, dependency in self.alternatives(self.units[anchor_id]):
                    full, swa, _, _ = self.union_cost(anchor_id, dependency)
                    new_over = (max(0, full - self.full_budget), max(0, swa - self.swa_budget))
                    if all(a <= b for a, b in zip(new_over, old_over)) and new_over != old_over:
                        choice = anchor, dependency
                        break
            if choice is None:
                self.drop(anchor_id, "budget")
                self.refresh()
            else:
                self.move_to_ancestor(anchor_id, *choice, "budget")

    def relax(self, component, candidates):
        candidates = list(candidates)
        if self.downgrade:
            for anchor_id, unit in list(self.units.items()):
                for anchor, dependency in self.alternatives(unit):
                    full_cost, swa_cost, full, swa = self.union_cost(anchor_id, dependency)
                    if full_cost > self.full_budget or swa_cost > self.swa_budget:
                        continue
                    required = full if component == self.full_ct else swa
                    if any(n not in required and (n not in self.cache.evictable_device_leaves
                           or (n not in full and n not in swa)) for n in candidates):
                        self.move_to_ancestor(anchor_id, anchor, dependency,
                                              "pressure_" + component.name.lower())
                        return True
        return super().relax(component, candidates)
