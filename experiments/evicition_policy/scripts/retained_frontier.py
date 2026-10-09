"""Bounded admission that retains complete resident Full/SWA boundaries.

The frozen v1 driver, native candidate ordering, locks and frees are inherited.
Only admission changes: a new or advancing boundary must fit alongside the
other protected units, otherwise its qualification is rejected and existing
units stay in place. Pressure/resize still revoke oldest units for progress.
Request indices and reuse counts below are diagnostics, never policy inputs.
"""

from bounded_frontier import BoundedFrontier


class RetainedFrontier(BoundedFrontier):
    def __init__(self, cache, settings=None, component_types=None):
        super().__init__(cache, settings, component_types)
        self.admission = self.settings.get("admission_policy", "replace_oldest")
        if self.admission not in {"replace_oldest", "retain_existing"}:
            raise ValueError("Unknown admission policy")
        self.event_sink = None
        self.event_index = 0
        self.request_index = -1
        self.phase = "initial"

    def log(self, kind, **fields):
        if self.event_sink is None:
            return
        self.event_index += 1
        self.event_sink({"schema": "agentkv.retained_frontier_event.v2",
                         "event_seq": self.event_index, "request_index": self.request_index,
                         "phase": self.phase, "event_type": kind, **fields})

    def unit_fields(self, unit):
        full, swa = unit["dependencies"]
        return {"unit_id": unit["tick"], "anchor_node_id": int(unit["anchor"].id),
                "boundary_tokens": sum(len(n.key) for n in full),
                "full_dependency_tokens": sum(len(n.component_data[self.full_ct].value)
                                              for n in full if n.component_data[self.full_ct].value is not None),
                "swa_dependency_tokens": sum(len(n.component_data[self.swa_ct].value)
                                             for n in swa if n.component_data[self.swa_ct].value is not None),
                "admitted_at": unit.get("admitted_at", -1),
                "observed_reuses": unit.get("observed_reuses", 0)}

    def drop(self, anchor_id, reason):
        unit = self.units[anchor_id]
        self.log("revoke", reason=reason, **self.unit_fields(unit))
        return super().drop(anchor_id, reason)

    def observe_match(self, anchor, matched_tokens):
        """Call only for the initial lookup, excluding this request's inserts."""
        if not self.enabled or matched_tokens <= 0:
            return
        self.refresh()
        path = self.path(anchor)
        if path is None:
            return
        ancestors = set(path)
        for unit in self.units.values():
            if unit["anchor"] in ancestors:
                unit["observed_reuses"] += 1
                self.counts["observed_unit_reuses"] += 1
                self.log("reuse", matched_tokens=int(matched_tokens), **self.unit_fields(unit))

    def register(self, anchor, request_id=None):
        if not self.enabled:
            return
        self.refresh()
        dependencies = self.dependencies(anchor)
        if dependencies is None:
            self.counts["register_unavailable"] += 1
            self.log("admission_reject", reason="unavailable", anchor_node_id=int(anchor.id))
            return
        new_full = dependencies[0]
        related = [anchor_id for anchor_id, unit in self.units.items()
                   if unit["anchor"] in new_full or anchor in unit["dependencies"][0]]
        full, swa = set(new_full), set(dependencies[1])
        for anchor_id, unit in self.units.items():
            if anchor_id not in related:
                full.update(unit["dependencies"][0])
                swa.update(unit["dependencies"][1])
        full_cost = sum(len(n.component_data[self.full_ct].value) for n in full)
        swa_cost = sum(len(n.component_data[self.swa_ct].value) for n in swa)
        proposed_units = len(self.units) - len(related) + 1
        if self.admission == "retain_existing" and (
                proposed_units > self.max_units or full_cost > self.full_budget
                or swa_cost > self.swa_budget):
            reason = "continuation_budget" if related else "new_boundary_budget"
            self.counts["admission_rejected_" + reason] += 1
            self.log("admission_reject", reason=reason, request_id=request_id,
                     anchor_node_id=int(anchor.id),
                     boundary_tokens=sum(len(n.key) for n in new_full),
                     retained_unit_ids=[u["tick"] for u in self.units.values()],
                     proposed_full_tokens=full_cost, proposed_swa_tokens=swa_cost,
                     proposed_units=proposed_units,
                     limits={"full": self.full_budget, "swa": self.swa_budget,
                             "units": self.max_units})
            return
        prior_units = [self.units[anchor_id]["tick"] for anchor_id in related]
        for anchor_id in related:
            self.drop(anchor_id, "replaced_boundary")
        self.tick += 1
        unit = {"anchor": anchor, "dependencies": dependencies, "tick": self.tick,
                "admitted_at": self.request_index, "observed_reuses": 0}
        self.units[anchor.id] = unit
        self.counts["registered"] += 1
        self.log("admit", request_id=request_id, predecessor_unit_ids=prior_units,
                 **self.unit_fields(unit))
        self.trim_budget()

    def log_final(self):
        if not self.enabled:
            return
        self.refresh()
        for unit in self.units.values():
            self.log("final_resident", **self.unit_fields(unit))
