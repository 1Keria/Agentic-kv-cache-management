#!/usr/bin/env python3
"""Run frozen v2/partial/v3 comparisons on real native cache checkpoints."""

import argparse
import datetime
import json
from pathlib import Path
import shutil

import replay_resizable_native as replay
from checkpoint_frontier import CheckpointFrontier
RetainedFrontier = CheckpointFrontier

ROOT = replay.ROOT
SOURCES = ("bounded_frontier.py", "replay_resizable_native.py",
           "resizable_agent_budget.py", "retained_frontier.py", "checkpoint_frontier.py",
           "run_checkpoint_frontier.py")
PHASES = ("initial", "half", "quarter", "restored")


class ObservedInputReplay(replay.NativeInputReplay):
    def __init__(self, *args, **kwargs):
        original = replay.BoundedFrontier
        replay.BoundedFrontier = RetainedFrontier
        try:
            super().__init__(*args, **kwargs)
        finally:
            replay.BoundedFrontier = original
        self.initial_lookup = False
        native_match = self.cache.match_prefix

        def match(params):
            result = native_match(params)
            if self.initial_lookup:
                self.initial_lookup = False
                self.frontier.observe_match(result.last_device_node, len(result.device_indices))
            return result

        self.cache.match_prefix = match

    def request(self, row, index):
        self.initial_lookup = True
        return super().request(row, index)


def run(args):
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "results"):
        raise ValueError("Outputs must stay in experiment results")
    protocol = json.loads(args.protocol.read_text())
    if protocol["schema"] != "agentkv.checkpoint_frontier_protocol.v3":
        raise ValueError("Unknown protocol")
    for name, expected in protocol["implementation_sha256"].items():
        if replay.digest_file(ROOT / "scripts" / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    workload_path = ROOT / protocol["workload"]
    if replay.digest_file(workload_path) != protocol["workload_sha256"]:
        raise ValueError("Workload changed")
    for name, record in protocol["settings"].items():
        if replay.digest_file(ROOT / record["path"]) != record["sha256"]:
            raise ValueError("Settings changed: " + name)
    original_protocol = json.loads((ROOT / protocol["original_protocol"]).read_text())
    if replay.digest_file(ROOT / protocol["original_protocol"]) != protocol["original_protocol_sha256"]:
        raise ValueError("Original protocol changed")
    workload = json.loads(workload_path.read_text())
    original_args = replay.parser().parse_args([
        "--output", str(output), "--protocol", str(ROOT / protocol["original_protocol"])])
    replay.validate_protocol(original_args, workload)
    for key in ("workload", "workload_sha256", "physical_capacity", "page_size",
                "sliding_window_size", "chunked_prefill_tokens", "profile_events",
                "requests", "complete_sessions", "source_session_files"):
        if protocol[key] != original_protocol[key]:
            raise ValueError("Experiment geometry/order differs from v1: " + key)
    ordered = replay.round_robin_requests(workload)
    if len(ordered) != protocol["requests"] or not workload["frozen"]:
        raise ValueError("Incomplete workload")
    replay.load_native()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "executed_sources"
    snapshot.mkdir()
    for name in SOURCES:
        shutil.copy2(ROOT / "scripts" / name, snapshot / name)
    shutil.copy2(args.protocol, snapshot / args.protocol.name)
    for record in protocol["settings"].values():
        path = ROOT / record["path"]
        shutil.copy2(path, snapshot / path.name)
    replay.save_json(snapshot / "manifest.json", {
        path.name: replay.digest_file(path) for path in snapshot.iterdir()})
    order = [{key: row[key] for key in ("session_id", "task_id", "turn_index", "input_ids_sha256")}
             for row in ordered]
    replay.save_json(output / "order.json", order)
    suite = {"schema": "agentkv.checkpoint_frontier_suite.v3", "status": "running",
             "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "protocol": str(args.protocol.resolve().relative_to(ROOT)),
             "protocol_sha256": replay.digest_file(args.protocol),
             "order_sha256": replay.canonical_digest(order), "requests_per_condition": len(ordered),
             "implementation_sha256": protocol["implementation_sha256"], "conditions": []}
    replay.save_json(output / "suite.json", suite)
    try:
        for profile in protocol["profiles"]:
            for variant in protocol["variants"]:
                for name, expected in protocol["implementation_sha256"].items():
                    if replay.digest_file(ROOT / "scripts" / name) != expected:
                        raise ValueError("Frozen source changed during run: " + name)
                folder = output / (profile + "_" + variant)
                folder.mkdir()
                settings_record = protocol["settings"][variant]
                settings = json.loads((ROOT / settings_record["path"]).read_text())
                engine = ObservedInputReplay(
                    protocol["physical_capacity"]["full"], protocol["physical_capacity"]["swa"],
                    page_size=protocol["page_size"], window=protocol["sliding_window_size"],
                    chunk=protocol["chunked_prefill_tokens"],
                    policy="lru" if variant == "lru" else "frontier",
                    max_prompt=max(len(row["input_ids"]) for row in ordered) + protocol["page_size"],
                    frontier_settings=settings)
                events = protocol["profile_events"][profile]
                records = []
                with (folder / "requests.jsonl").open("x") as requests, \
                     (folder / "budget_events.jsonl").open("x") as budgets, \
                     (folder / "unit_events.jsonl").open("x") as units:
                    engine.frontier.event_sink = lambda event: replay.write_record(units, event)
                    for index, row in enumerate(ordered):
                        phase = PHASES[sum(index >= boundary for boundary in (301, 603, 904))]
                        engine.frontier.request_index = index
                        engine.frontier.phase = phase
                        for version, event in enumerate(events):
                            if event["before_request_index"] == index:
                                receipt = engine.update_budget(event["full"], event["swa"], version)
                                replay.write_record(budgets, {"request_index": index, "phase": phase, **receipt})
                        record = engine.request(row, index)
                        record.update({"profile": profile, "variant": variant, "phase": phase})
                        records.append(record)
                        replay.write_record(requests, record)
                        if (index + 1) % 200 == 0:
                            requests.flush()
                            units.flush()
                            print(json.dumps({"condition": folder.name, "completed": index + 1}), flush=True)
                    engine.frontier.log_final()
                totals = {key: sum(row[key] for row in records) for key in (
                    "prompt_tokens", "matched_tokens", "history_match_tokens", "capacity_loss_tokens",
                    "full_resident_but_joint_unavailable_tokens")}
                result = {"condition": folder.name, "profile": profile, "variant": variant,
                          "completed_requests": len(records), "totals": totals,
                          "hit_rate": totals["matched_tokens"] / totals["prompt_tokens"],
                          "frontier_counts": dict(engine.frontier.counts),
                          "final_state": engine.state(),
                          "checks_passed": all(all(row[key] for key in (
                              "integrity_passed", "budget_checks_complete", "physical_accounting_ok"))
                                               for row in records),
                          "evidence_sha256": {name: replay.digest_file(folder / name) for name in (
                              "requests.jsonl", "budget_events.jsonl", "unit_events.jsonl")}}
                replay.save_json(folder / "summary.json", result)
                suite["conditions"].append(result)
                replay.save_json(output / "suite.json", suite)
                print(json.dumps({"condition": folder.name, "complete": len(records),
                                  "hit_rate": result["hit_rate"],
                                  "checks_passed": result["checks_passed"]}), flush=True)
                del engine
        suite["status"] = "complete"
        suite["total_executed_requests"] = sum(c["completed_requests"] for c in suite["conditions"])
    except BaseException as error:
        suite["status"], suite["error"] = "failed", repr(error)
        raise
    finally:
        suite["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        replay.save_json(output / "suite.json", suite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
