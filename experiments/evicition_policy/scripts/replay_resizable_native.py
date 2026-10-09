#!/usr/bin/env python3
"""Replay actual token inputs through official CPU radix and physical page indices.

This is a serial cache-state experiment, not a serving or latency benchmark.
The unmodified official UnifiedRadixCache, Full/SWA components, request index
pool and page allocators execute matches, inserts, reference locks and frees.
Only K/V tensor payloads and model computation are absent. The frozen v1 guard
is attached at the same instance call sites as its previously tested overlay.
"""

import argparse
from array import array
from collections import Counter
import datetime
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bounded_frontier import BoundedFrontier
from resizable_agent_budget import PoolTokens, from_unified_cache


def digest_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_record(stream, record):
    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


_NATIVE = None


def load_native():
    """Import the intact official package, refusing previously imported forks."""
    global _NATIVE
    if _NATIVE is not None:
        return _NATIVE
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    lock = json.loads((ROOT / "configs/environment.lock.json").read_text())
    package_root = ROOT / "runtime/frontier_pristine_20261008_v1"
    package = package_root / "sglang"
    if digest_file(ROOT / lock["engine"]["wheel"]) != lock["engine"]["wheel_sha256"]:
        raise ValueError("Official wheel hash mismatch")
    for relative, expected in lock["engine"]["source_hashes"].items():
        if digest_file(package / relative) != expected:
            raise ValueError("Pristine package source mismatch: " + relative)
    if "sglang" in sys.modules:
        imported = Path(sys.modules["sglang"].__file__).resolve()
        if not imported.is_relative_to(package):
            raise ValueError("Another SGLang package was imported before the pristine package")
    sys.path.insert(0, str(package_root))
    import torch
    from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
    from sglang.srt.mem_cache.base_prefix_cache import EvictParams, MatchPrefixParams
    from sglang.srt.mem_cache.base_swa_memory_pool import BaseSWAKVPool
    from sglang.srt.mem_cache.cache_init_params import CacheInitParams
    from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
    from sglang.srt.mem_cache.radix_cache import RadixKey
    from sglang.srt.mem_cache.unified_cache_components import ComponentType
    from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
    for cls in (UnifiedRadixCache, SWATokenToKVPoolAllocator, ReqToTokenPool):
        if not Path(inspect.getfile(cls)).resolve().is_relative_to(package):
            raise ValueError("CPU experiment imported a non-pristine native class")
    torch.set_num_threads(1)

    class CPUIndexPool(BaseSWAKVPool):
        """CPU backing for real allocator indices; never supplies fake KV data."""

        def __init__(self):
            self.full_kv_pool = self.swa_kv_pool = None
            self.full_to_swa_index_mapping = None

        def register_mapping(self, mapping):
            self.full_to_swa_index_mapping = mapping

        def translate_loc_from_full_to_swa(self, indices):
            return self.full_to_swa_index_mapping[indices]

        def get_state_buf_infos(self):
            return [], [], []

        def get_key_buffer(self, *args, **kwargs):
            raise RuntimeError("CPU index replay contains no K/V payload")

        get_value_buffer = get_key_buffer
        get_kv_buffer = get_key_buffer
        set_kv_buffer = get_key_buffer

    _NATIVE = SimpleNamespace(torch=torch, Cache=UnifiedRadixCache,
                             Allocator=SWATokenToKVPoolAllocator, IndexPool=CPUIndexPool,
                             ReqPool=ReqToTokenPool, InitParams=CacheInitParams,
                             MatchParams=MatchPrefixParams, EvictParams=EvictParams,
                             Key=RadixKey, CT=ComponentType, lock=lock,
                             package_root=package_root)
    return _NATIVE


class HistoryPrefixIndex:
    """Infinite metadata for precisely the input pages this replay materializes."""

    def __init__(self, page_size):
        self.page_size = page_size
        self.namespaces = {}
        self.nodes = 0

    def match(self, values, namespace=None):
        node = self.namespaces.get(namespace, {})
        matched = 0
        for start in range(0, len(values) - self.page_size + 1, self.page_size):
            page = tuple(values[start:start + self.page_size])
            node = node.get(page)
            if node is None:
                break
            matched += self.page_size
        return matched

    def insert(self, values, namespace=None):
        node = self.namespaces.setdefault(namespace, {})
        for start in range(0, len(values) - self.page_size + 1, self.page_size):
            page = tuple(values[start:start + self.page_size])
            if page not in node:
                node[page] = {}
                self.nodes += 1
            node = node[page]


def round_robin_requests(workload):
    """Freeze ordering without looking at any cache results or future reuse."""
    sessions = []
    for entry in workload["sessions"]:
        path = (ROOT / entry["path"]).resolve()
        if not path.is_relative_to(ROOT) or digest_file(path) != entry["sha256"]:
            raise ValueError("Encoded session path/hash mismatch")
        with gzip.open(path, "rt") as stream:
            rows = [json.loads(line) for line in stream]
        if len(rows) != entry["requests"] or entry["replay_requests"] != len(rows):
            raise ValueError("CPU experiment requires complete frozen sessions")
        for turn, row in enumerate(rows):
            if row["turn_index"] != turn or row["session_id"] != entry["session_id"]:
                raise ValueError("Session identity or ordering mismatch")
            if canonical_digest(row["input_ids"]) != row["input_ids_sha256"]:
                raise ValueError("Frozen input token hash mismatch")
            if len(row["input_ids"]) != row["prompt_tokens"]:
                raise ValueError("Frozen input length mismatch")
            row["input_ids"] = array("q", row["input_ids"])
        sessions.append(rows)
    ordered = []
    for turn in range(max(map(len, sessions))):
        ordered.extend(rows[turn] for rows in sessions if turn < len(rows))
    if len(ordered) != workload["requests"]:
        raise ValueError("Frozen workload total mismatch")
    return ordered


class NativeInputReplay:
    """One uninterrupted official cache instance for one comparison condition."""

    def __init__(self, full_capacity, swa_capacity, page_size=256, window=128,
                 chunk=8192, policy="lru", max_prompt=262144,
                 frontier_settings=None):
        if policy not in {"lru", "frontier"}:
            raise ValueError("Unknown CPU policy")
        if min(full_capacity, swa_capacity, page_size, window, chunk) <= 0:
            raise ValueError("Capacities and geometry must be positive")
        if full_capacity % page_size or swa_capacity % page_size or chunk % page_size:
            raise ValueError("Capacities and chunk must be page-aligned")
        self.native = native = load_native()
        self.page_size, self.chunk, self.policy = page_size, chunk, policy
        self.current_req, self.committing_finished = None, False
        self.eviction_free = Counter()
        self.eviction_records = []
        self.receipts = []
        backing = native.IndexPool()
        allocator = native.Allocator(full_capacity, swa_capacity, page_size,
                                     native.torch.float16, "cpu", backing, False)
        allocator.full_attn_allocator.debug_mode = True
        allocator.swa_attn_allocator.debug_mode = True
        req_pool = native.ReqPool(1, max_prompt + page_size, "cpu", False)
        params = native.InitParams(disable=False, req_to_token_pool=req_pool,
                                  token_to_kv_pool_allocator=allocator, page_size=page_size,
                                  eviction_policy="lru", sliding_window_size=window,
                                  tree_components=(native.CT.FULL, native.CT.SWA))
        self.cache = cache = native.Cache(params)
        settings = dict(frontier_settings or json.loads(
            (ROOT / "configs/bounded_frontier_v1.json").read_text()))
        settings["enabled"] = policy == "frontier"
        # Disable environment-directed v1 logging; output ownership is explicit.
        old_metrics = os.environ.pop("AGENTKV_FRONTIER_METRICS_DIR", None)
        try:
            self.frontier = frontier = BoundedFrontier(cache, settings,
                                                       component_types=cache.tree_components)
        finally:
            if old_metrics is not None:
                os.environ["AGENTKV_FRONTIER_METRICS_DIR"] = old_metrics
        cache.agentkv_frontier = frontier
        for component in cache._components_tuple:
            original_free = component.evict_component

            def on_free(node, target=None, *, _free=original_free,
                        _component=component):
                if target is None:
                    freed, host_freed = _free(node)
                else:
                    freed, host_freed = _free(node, target)
                pool = _component.component_type.name.lower()
                if freed:
                    self.eviction_free[pool] += freed
                    self.eviction_records.append({"pool": pool, "node_id": int(node.id),
                                                  "tokens": int(freed)})
                if frontier.enabled:
                    frontier.freed(node, _component.component_type, freed)
                return freed, host_freed

            component.evict_component = on_free
            if frontier.enabled:
                original_drive = component.drive_eviction

                def on_drive(params, tracker, *, _component=component, _drive=original_drive):
                    if frontier.enabled:
                        return frontier.drive(_component, params, tracker)
                    return _drive(params, tracker)

                component.drive_eviction = on_drive
        if frontier.enabled:
            original_insert = cache.insert

            def on_insert(params):
                result = original_insert(params)
                if self.current_req is not None:
                    frontier.committed(self.current_req, params.key, self.committing_finished)
                return result

            cache.insert = on_insert
        self.controller = from_unified_cache(
            cache, PoolTokens(full_capacity, swa_capacity), frontier=frontier,
            evict_params_factory=native.EvictParams)
        self.history = HistoryPrefixIndex(page_size)

    def state(self):
        result = self.controller.observe().as_dict()
        if self.frontier.enabled:
            self.frontier.refresh()
        result["frontier"] = {"units": len(self.frontier.units),
                              "full_dependency_tokens": int(self.frontier.full_tokens),
                              "swa_dependency_tokens": int(self.frontier.swa_tokens),
                              "full_protection_limit": int(self.frontier.full_budget),
                              "swa_protection_limit": int(self.frontier.swa_budget),
                              "counters": dict(self.frontier.counts)}
        return result

    def record_receipt(self, receipt):
        if not receipt["accounting_ok"]:
            raise RuntimeError("Native reported frees differ from real allocator page releases")
        self.receipts.append(receipt)
        return receipt

    def update_budget(self, full, swa, version):
        return self.record_receipt(self.controller.update_budget(full, swa, version))

    def full_resident_match(self, key):
        """Read-only Full reachability; ignores auxiliary-window validators."""
        ct, root = self.native.CT.FULL, self.cache.root_node
        node, matched = root, 0
        while len(key):
            child = node.children.get(key.child_key(self.page_size))
            if child is None or child.component_data[ct].value is None:
                break
            count = child.key.match(key, self.page_size)
            matched += count
            if count < len(child.key):
                break
            node, key = child, key[count:]
        return matched

    def assert_integrity(self):
        """Check official invariants and exact page ownership at request quiescence."""
        self.cache.sanity_check()
        allocator = self.cache.token_to_kv_pool_allocator
        for ct, physical in ((self.native.CT.FULL, allocator.full_attn_allocator),
                             (self.native.CT.SWA, allocator.swa_attn_allocator)):
            values = [node.component_data[ct].value for node in self.cache._collect_all_nodes()
                      if node is not self.cache.root_node and node.component_data[ct].value is not None]
            indices = self.native.torch.cat(values) if values else self.native.torch.empty(0, dtype=self.native.torch.int64)
            if len(indices) != len(self.native.torch.unique(indices)):
                raise RuntimeError("Multiple nodes own the same physical token slot")
            if len(indices) != physical.size - physical.available_size():
                raise RuntimeError("Quiescent allocator occupancy differs from real tree ownership")
            owned = set((indices // self.page_size).tolist())
            free = set(physical.free_pages.tolist())
            if owned & free or len(owned) + len(free) != physical.num_pages:
                raise RuntimeError("Physical page partition is incomplete or duplicated")
        if self.cache.full_protected_size() or self.cache.swa_protected_size():
            raise RuntimeError("Request completion left a native reference lock")

    def request(self, row, request_index):
        native, cache, allocator = self.native, self.cache, self.cache.token_to_kv_pool_allocator
        tokens = list(row["input_ids"])
        before = self.state()
        previous_frees = dict(self.eviction_free)
        first_receipt = len(self.receipts)
        first_free_record = len(self.eviction_records)
        key = native.Key(tokens[:-1], None).page_aligned(self.page_size)
        history_match = self.history.match(tokens[:-1])
        match = cache.match_prefix(native.MatchParams(key=key))
        matched = len(match.device_indices)
        full_available_match = self.full_resident_match(key)
        if not matched <= full_available_match <= history_match:
            raise RuntimeError("Joint/Full/history match ordering is inconsistent")
        lock_result = cache.inc_lock_ref(match.last_device_node)
        req = SimpleNamespace(rid=f"cpu-{request_index}", origin_input_ids=tokens,
                              output_ids=[], extra_key=None, session=None,
                              req_pool_idx=1, cache_protected_len=matched,
                              last_node=match.last_device_node,
                              swa_uuid_for_lock=lock_result.swa_uuid_for_lock,
                              prefix_indices=match.device_indices,
                              swa_evicted_seqlen=0, priority=0, computed_len=matched)
        req.get_fill_ids = lambda: tokens[:req.computed_len]
        req.pop_committed_kv_cache = lambda: len(tokens)
        cache.req_to_token_pool.req_to_token[1].zero_()
        cache.req_to_token_pool.write((1, slice(0, matched)), match.device_indices)
        self.current_req, self.committing_finished = req, False
        chunks = 0
        while req.computed_len < len(tokens):
            start = req.computed_len
            end = min(len(tokens), start + self.chunk)
            need = (end - start + self.page_size - 1) // self.page_size * self.page_size
            receipt = self.record_receipt(self.controller.ensure_capacity(need, need))
            if not receipt["complete"]:
                raise RuntimeError("Input working set cannot fit the preregistered logical budget: "
                                   + json.dumps(receipt["shortfall"]))
            full = allocator.full_attn_allocator.alloc(need)
            swa = allocator.swa_attn_allocator.alloc(need)
            if full is None or swa is None:
                raise RuntimeError("Physical pool exhausted despite successful logical admission")
            allocator.set_full_to_swa_mapping(full, swa)
            cache.req_to_token_pool.write((1, slice(start, end)), full[:end - start])
            req.computed_len = end
            cache.cache_unfinished_req(req, chunked=end < len(tokens))
            chunks += 1
        self.committing_finished = True
        cache.cache_finished_req(req)
        self.current_req = None
        self.history.insert(tokens)
        receipt = self.record_receipt(self.controller.enforce())
        if not receipt["complete"]:
            raise RuntimeError("Completion did not discharge logical budget obligations")
        self.assert_integrity()
        after = self.state()
        receipts = self.receipts[first_receipt:]
        return {"schema": "agentkv.resizable_native_request.v1", "request_index": request_index,
                "session_id": row.get("session_id"), "task_id": row.get("task_id"),
                "turn_index": row.get("turn_index"), "input_ids_sha256": row.get("input_ids_sha256"),
                "prompt_tokens": len(tokens), "matched_tokens": matched,
                "history_match_tokens": history_match,
                "capacity_loss_tokens": history_match - matched,
                "unavoidable_new_input_tokens": len(tokens) - history_match,
                "missed_input_tokens": len(tokens) - matched,
                "full_resident_match_tokens": full_available_match,
                "full_resident_but_joint_unavailable_tokens": full_available_match - matched,
                "hard_budget": self.controller.hard_budget.as_dict(),
                "budget_version": self.controller.version, "before": before, "after": after,
                "prefill_chunks": chunks, "eviction_calls": sum(r["eviction_calls"] for r in receipts),
                "real_eviction_release": {pool: self.eviction_free[pool] - previous_frees.get(pool, 0)
                                          for pool in ("full", "swa")},
                "native_free_events": self.eviction_records[first_free_record:],
                "admission_and_completion_checks": len(receipts),
                "budget_checks_complete": all(r["complete"] for r in receipts),
                "physical_accounting_ok": all(r["accounting_ok"] for r in receipts),
                "integrity_passed": True}


def budget_for_profile(profile, index, full, swa, page, change_indices):
    if profile not in {"constant", "shrink_restore"}:
        raise ValueError("Unknown capacity profile")
    phase = sum(index >= event for event in change_indices)
    divisor = (1, 2, 4, 1)[phase] if profile == "shrink_restore" else 1
    return full // divisor // page * page, swa // divisor // page * page, phase


def validate_protocol(args, workload):
    if args.protocol is None:
        return None
    protocol = json.loads(args.protocol.read_text())
    if protocol.get("schema") != "agentkv.resizable_native_protocol.v1":
        raise ValueError("Unknown preregistered protocol schema")
    comparisons = ((str(args.workload.resolve().relative_to(ROOT)), protocol["workload"]),
                   (digest_file(args.workload), protocol["workload_sha256"]),
                   (args.full_capacity, protocol["physical_capacity"]["full"]),
                   (args.swa_capacity, protocol["physical_capacity"]["swa"]),
                   (args.page_size, protocol["page_size"]),
                   (args.window, protocol["sliding_window_size"]),
                   (args.chunk, protocol["chunked_prefill_tokens"]),
                   (args.profiles, protocol["profiles"]), (args.policies, protocol["policies"]),
                   (workload["requests"], protocol["requests"]),
                   (len(workload["sessions"]), protocol["complete_sessions"]))
    if any(actual != expected for actual, expected in comparisons):
        raise ValueError("Runtime parameters differ from preregistered protocol")
    indices = [event["before_request_index"] for event in protocol["profile_events"]["shrink_restore"]]
    if indices != [0, *args.change_indices]:
        raise ValueError("Runtime budget event indices differ from protocol")
    settings = json.loads((ROOT / "configs/bounded_frontier_v1.json").read_text())
    if any(settings[key] != value for key, value in protocol["frontier_upper_limits"].items()):
        raise ValueError("Frozen frontier upper limits differ from protocol")
    source = [{key: entry[key] for key in ("session_id", "path", "sha256", "requests")}
              for entry in workload["sessions"]]
    if source != protocol["source_session_files"]:
        raise ValueError("Frozen input session manifest differs from protocol")
    for profile in args.profiles:
        expected_indices = [0] if profile == "constant" else [0, *args.change_indices]
        events = protocol["profile_events"][profile]
        if [event["before_request_index"] for event in events] != expected_indices:
            raise ValueError("Unexpected protocol capacity events")
        for event in events:
            full, swa, _ = budget_for_profile(profile, event["before_request_index"],
                                               args.full_capacity, args.swa_capacity,
                                               args.page_size, args.change_indices)
            if (event["full"], event["swa"]) != (full, swa):
                raise ValueError("Protocol capacity differs from page-aligned profile")
    return protocol


def run(args):
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "results"):
        raise ValueError("All replay outputs must stay under experiment results")
    workload = json.loads(args.workload.read_text())
    if not workload.get("frozen"):
        raise ValueError("Workload must be frozen")
    protocol = validate_protocol(args, workload)
    ordered = round_robin_requests(workload)
    if len(args.change_indices) != 3 or sorted(set(args.change_indices)) != args.change_indices:
        raise ValueError("Provide three increasing preregistered change indices")
    if not 0 < args.change_indices[0] < args.change_indices[-1] < len(ordered):
        raise ValueError("Capacity changes must be inside the complete trace")
    min_full = args.full_capacity // 4 // args.page_size * args.page_size
    max_working_set = max((len(r["input_ids"]) + args.page_size - 1) // args.page_size * args.page_size
                          for r in ordered)
    if "shrink_restore" in args.profiles and max_working_set > min_full:
        raise ValueError("Complete input working set exceeds the smallest logical Full budget")
    if args.swa_capacity // 4 // args.page_size * args.page_size < args.chunk + args.page_size:
        raise ValueError("Smallest SWA budget must admit a chunk and its active window")
    native = load_native()
    output.mkdir(parents=True, exist_ok=False)
    order = [{name: row[name] for name in ("session_id", "task_id", "turn_index", "input_ids_sha256")}
             for row in ordered]
    suite = {"schema": "agentkv.resizable_native_suite.v1", "status": "running",
             "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "workload": str(args.workload.resolve().relative_to(ROOT)),
             "workload_sha256": digest_file(args.workload), "requests": len(ordered),
             "sessions": len(workload["sessions"]), "order": "session_round_robin",
             "order_sha256": canonical_digest(order), "profiles": args.profiles, "policies": args.policies,
             "initial_physical_capacity": {"full": args.full_capacity, "swa": args.swa_capacity},
             "page_size": args.page_size, "sliding_window_size": args.window, "prefill_chunk": args.chunk,
             "change_request_indices": [0, *args.change_indices], "profile_divisors": [1, 2, 4, 1],
             "minimum_full_budget": min_full, "maximum_input_working_set": max_working_set,
             "physical_capacity_selection_reason": "smallest budget must fit every complete input; not tuned to policy gains",
             "official_package": str(native.package_root.relative_to(ROOT)),
             "official_wheel_sha256": native.lock["engine"]["wheel_sha256"],
             "official_source_hashes": native.lock["engine"]["source_hashes"],
             "protocol": str(args.protocol.resolve().relative_to(ROOT)) if args.protocol else None,
             "protocol_sha256": digest_file(args.protocol) if args.protocol else None,
             "implementation_hashes": {name: digest_file(ROOT / "scripts" / name) for name in (
                 "replay_resizable_native.py", "resizable_agent_budget.py", "bounded_frontier.py")},
             "limitations": ["CPU index pools contain no model K/V payload or GPU computation",
                             "serial fixed input-only replay; no decode, real tools, source waits or TTFT",
                             "external frozen budget profile, not feedback-driven mixed-traffic partitioning",
                             "history index retains only actual input pages materialized by this protocol"],
             "conditions": []}
    save_json(output / "order.json", order)
    save_json(output / "suite.json", suite)
    try:
        for profile in args.profiles:
            for policy in args.policies:
                name = profile + "_" + policy
                destination = output / name
                destination.mkdir()
                engine = NativeInputReplay(args.full_capacity, args.swa_capacity, args.page_size,
                                           args.window, args.chunk, policy,
                                           max_prompt=max_working_set)
                records = []
                with (destination / "requests.jsonl").open("x") as stream, \
                     (destination / "budget_events.jsonl").open("x") as budget_stream:
                    for index, row in enumerate(ordered):
                        event_indices = (0,) if profile == "constant" else (0, *args.change_indices)
                        if index in event_indices:
                            full, swa, phase = budget_for_profile(profile, index, args.full_capacity,
                                                                  args.swa_capacity, args.page_size,
                                                                  args.change_indices)
                            receipt = engine.update_budget(full, swa, phase)
                            write_record(budget_stream, {"request_index": index, "profile": profile,
                                                         "policy": policy, **receipt})
                        record = engine.request(row, index)
                        record.update({"profile": profile, "policy": policy})
                        records.append(record)
                        write_record(stream, record)
                        if (index + 1) % 200 == 0:
                            stream.flush()
                            print(json.dumps({"condition": name, "completed": index + 1}), flush=True)
                totals = {key: sum(r[key] for r in records) for key in (
                    "prompt_tokens", "matched_tokens", "history_match_tokens", "capacity_loss_tokens",
                    "missed_input_tokens", "full_resident_but_joint_unavailable_tokens", "eviction_calls")}
                summary = {"schema": "agentkv.resizable_native_summary.v1", "condition": name,
                           "completed_requests": len(records), "totals": totals,
                           "token_hit_ratio": totals["matched_tokens"] / totals["prompt_tokens"],
                           "integrity_passed": all(r["integrity_passed"] for r in records),
                           "budget_checks_complete": all(r["budget_checks_complete"] for r in records),
                           "physical_accounting_ok": all(r["physical_accounting_ok"] for r in records),
                           "final_state": engine.state(), "frontier_counts": dict(engine.frontier.counts),
                           "native_eviction_tokens": dict(engine.eviction_free),
                           "history_unique_pages": engine.history.nodes,
                           "requests_sha256": digest_file(destination / "requests.jsonl"),
                           "budget_events_sha256": digest_file(destination / "budget_events.jsonl")}
                save_json(destination / "summary.json", summary)
                suite["conditions"].append(summary)
                save_json(output / "suite.json", suite)
                print(json.dumps({"condition": name, "completed": len(records),
                                  "hit_ratio": summary["token_hit_ratio"]}), flush=True)
                del engine
        suite["status"] = "complete"
    except BaseException as error:
        suite["status"], suite["error"] = "failed", repr(error)
        raise
    finally:
        suite["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(output / "suite.json", suite)
    return suite


def parser():
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--workload", type=Path, default=ROOT / "data/workloads/exploration_1h_v4/evaluation.json")
    argument_parser.add_argument("--output", type=Path, required=True)
    argument_parser.add_argument("--protocol", type=Path)
    argument_parser.add_argument("--profiles", nargs="+", choices=("constant", "shrink_restore"), default=["constant", "shrink_restore"])
    argument_parser.add_argument("--policies", nargs="+", choices=("lru", "frontier"), default=["lru", "frontier"])
    argument_parser.add_argument("--full-capacity", type=int, default=589824)
    argument_parser.add_argument("--swa-capacity", type=int, default=52224)
    argument_parser.add_argument("--page-size", type=int, default=256)
    argument_parser.add_argument("--window", type=int, default=128)
    argument_parser.add_argument("--chunk", type=int, default=8192)
    argument_parser.add_argument("--change-indices", nargs=3, type=int, default=[301, 603, 904])
    return argument_parser


if __name__ == "__main__":
    run(parser().parse_args())
