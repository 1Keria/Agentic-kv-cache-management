#!/usr/bin/env python3
"""Read-only legal shallow-boundary census on the frozen v2 cache path."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

import run_retained_frontier as runner
import replay_resizable_native as replay
from retained_frontier import RetainedFrontier

ROOT = replay.ROOT


class ProbeFrontier(RetainedFrontier):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.probe_sink = None

    def shallow(self, anchor):
        path = self.path(anchor) or []
        result = []
        for node in path[1:]:
            dependency = self.dependencies(node)
            if dependency is None:
                continue
            full, swa = dependency
            full_cost = sum(len(n.component_data[self.full_ct].value) for n in full)
            swa_cost = sum(len(n.component_data[self.swa_ct].value) for n in swa)
            result.append({"node_id": int(node.id), "full": full_cost, "swa": swa_cost,
                           "fits_protection_limits": full_cost <= self.full_budget and swa_cost <= self.swa_budget})
        return result

    def relax(self, component, candidates):
        candidates = list(candidates)
        if self.probe_sink is not None:
            units = []
            for unit in self.units.values():
                full, swa = unit["dependencies"]
                required = full if component == self.full_ct else swa
                implicated = any(n in required or (n in self.cache.evictable_device_leaves
                                  and (n in full or n in swa)) for n in candidates)
                if implicated:
                    units.append({**self.unit_fields(unit), "legal_shallow": self.shallow(unit["anchor"])})
            self.probe_sink({"event_type": "before_pressure_relax", "index": self.request_index,
                             "phase": self.phase, "pool": component.name.lower(), "units": units})
        return super().relax(component, candidates)


def run(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "results"):
        raise ValueError("Probe output must stay under experiment results")
    output.mkdir(parents=True, exist_ok=False)
    proto_path = ROOT / "configs/retained_frontier_probe_v2.json"
    protocol = json.loads(proto_path.read_text())
    ordered = replay.round_robin_requests(json.loads((ROOT / protocol["workload"]).read_text()))
    settings = json.loads((ROOT / protocol["settings"]["v2"]["path"]).read_text())
    baseline = ROOT / "results/retained_frontier/20261009_v2/shrink_restore_v2"
    old = [json.loads(line) for line in (baseline / "requests.jsonl").read_text().splitlines()]
    original = runner.RetainedFrontier
    runner.RetainedFrontier = ProbeFrontier
    try:
        engine = runner.ObservedInputReplay(589824, 52224, policy="frontier", max_prompt=136192,
                                           frontier_settings=settings)
    finally:
        runner.RetainedFrontier = original
    snapshot = output / "executed_sources"
    snapshot.mkdir()
    sources = ["probe_shallow_frontier.py", *runner.SOURCES]
    for name in sources:
        shutil.copy2(ROOT / "scripts" / name, snapshot / name)
    census, pressure, stages = [], [], Counter()
    original_insert = engine.cache.insert
    def insert(params):
        result = original_insert(params)
        # No lookups or splits: inspect the exact resident nodes just inserted.
        req = engine.current_req
        if req is not None:
            node = req.last_node
            key, root = params.key, engine.cache.root_node
            node = root
            while len(key):
                child = node.children.get(key.child_key(engine.page_size))
                if child is None:
                    break
                count = child.key.match(key, page_size=engine.page_size)
                if count != len(child.key):
                    break
                node, key = child, key[count:]
            if node is not root:
                shallow = engine.frontier.shallow(node)
                census.append({"event_type": "insert_census", "index": engine.frontier.request_index,
                               "phase": engine.frontier.phase, "computed_len": req.computed_len,
                               "legal_shallow": shallow})
        return result
    engine.cache.insert = insert
    engine.frontier.probe_sink = pressure.append
    with (output / "requests.jsonl").open("x") as stream:
        for index, row in enumerate(ordered):
            phase = runner.PHASES[sum(index >= b for b in (301, 603, 904))]
            engine.frontier.request_index, engine.frontier.phase = index, phase
            for version, event in enumerate(protocol["profile_events"]["shrink_restore"]):
                if event["before_request_index"] == index:
                    receipt = engine.update_budget(event["full"], event["swa"], version)
                    assert receipt["complete"] and receipt["accounting_ok"]
            record = engine.request(row, index)
            for key in ("matched_tokens", "full_resident_match_tokens", "real_eviction_release"):
                assert record[key] == old[index][key], (index, key)
            replay.write_record(stream, record)
            stages[phase] += 1
            if (index + 1) % 200 == 0:
                print(json.dumps({"probe_requests": index + 1}), flush=True)
    for name, events in (("insert_census.jsonl", census), ("pressure_census.jsonl", pressure)):
        with (output / name).open("x") as stream:
            for event in events:
                replay.write_record(stream, event)
    summary = {"schema": "agentkv.shallow_probe.v1", "requests": len(ordered),
               "v2_reproduced_request_matches_and_frees": True,
               "source_sha256": {name: replay.digest_file(snapshot / name) for name in sources},
               "baseline_requests_sha256": replay.digest_file(baseline / "requests.jsonl"), "phases": {}}
    for phase in runner.PHASES:
        p = [e for e in pressure if e["phase"] == phase]
        units = [u for e in p for u in e["units"]]
        c = [e for e in census if e["phase"] == phase]
        summary["phases"][phase] = {
            "pressure_relax_calls": len(p), "implicated_units": len(units),
            "units_with_any_legal_shallow": sum(bool(u["legal_shallow"]) for u in units),
            "units_with_shallow_fitting_limits": sum(any(a["fits_protection_limits"] for a in u["legal_shallow"]) for u in units),
            "insert_observations": len(c),
            "insert_observations_with_legal_shallow": sum(bool(e["legal_shallow"]) for e in c),
            "requests_with_legal_shallow_on_insert": len({e["index"] for e in c if e["legal_shallow"]}),
            "minimum_legal_shallow_full": min((a["full"] for e in c for a in e["legal_shallow"]), default=None)}
    summary["outputs_sha256"] = {n: replay.digest_file(output / n) for n in (
        "requests.jsonl", "insert_census.jsonl", "pressure_census.jsonl")}
    replay.save_json(output / "summary.json", summary)
    print(json.dumps(summary["phases"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
