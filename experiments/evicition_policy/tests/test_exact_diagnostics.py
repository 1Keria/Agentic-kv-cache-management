import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_exact_plan_has_required_behaviors_and_page_alignment():
    replay = load_script("replay_exact_continuation.py")
    plan = replay.build_plan(129280)
    assert set(plan["sessions"]) == {"chain_a", "chain_b", "chain_c", "chain_d"}
    assert plan["sessions"]["chain_b"]["behavior"] == "stops_early"
    assert plan["sessions"]["chain_d"]["behavior"].startswith("fork")
    assert len(plan["schedule"]) == 27
    assert all(len(tokens) == 4096 for tokens in plan["initial_input_ids"].values())
    assert all(len(tokens) % replay.PAGE_SIZE == 0 for tokens in plan["initial_input_ids"].values())
    assert plan["generated_tokens_per_turn"] + plan["tool_tokens_per_turn"] == replay.PAGE_SIZE


def test_client_and_runtime_prefix_digest_are_identical():
    replay = load_script("replay_exact_continuation.py")
    runtime = load_script("sglang_agentkv_diagnostics.py")
    tokens = replay.token_block(42, 1024, 129280)
    assert replay.prefix_digest(tokens) == runtime._token_digest(tokens)


def test_captured_trace_validation_preserves_exact_continuations(tmp_path):
    replay = load_script("replay_exact_continuation.py")
    plan = replay.build_plan(129280)
    state = {
        name: {"input": list(tokens), "history": {}, "previous": None}
        for name, tokens in plan["initial_input_ids"].items()
    }
    rows = []
    for request_seq, scheduled in enumerate(plan["schedule"], start=1):
        name = scheduled["session_id"]
        turn = scheduled["turn_index"]
        lifecycle = "first" if turn == 0 else "continuation"
        branch_from_turn = None
        if name == "chain_d" and turn == 4:
            lifecycle = "branch"
            branch_from_turn = plan["sessions"][name]["branch_from_turn"]
            source = state[name]["history"][branch_from_turn]
            state[name]["input"] = source["input_ids"] + source["output_ids"] + replay.token_block(99000 + turn, 224, 129280)
        output_ids = replay.token_block(100000 + request_seq, 32, 129280)
        tool_ids = replay.token_block(50000 + request_seq * 131, 224, 129280)
        row = {
            "request_seq": request_seq,
            "session_id": name,
            "turn_index": turn,
            "lifecycle_state": lifecycle,
            "branch_from_turn": branch_from_turn,
            "input_ids": list(state[name]["input"]),
            "output_ids": output_ids,
            "tool_ids": tool_ids,
        }
        rows.append(row)
        state[name]["history"][turn] = row
        state[name]["input"] = row["input_ids"] + output_ids + tool_ids
    trace = tmp_path / "trace.jsonl"
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert len(replay.load_frozen_trace(trace, plan)) == 27


def test_diagnostics_patch_lock_matches_installed_files():
    lock = json.loads((ROOT / "configs/environment.diagnostics.lock.json").read_text())
    package = ROOT / "runtime/venv/lib/python3.12/site-packages/sglang/srt/mem_cache"
    import hashlib

    for relative, details in lock["files"].items():
        target = package / relative
        assert target.is_file()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == details["patched_sha256"] if "patched_sha256" in details else details["installed_sha256"]


def test_server_configs_keep_trace_feasible_and_pressure_full_pool():
    control = json.loads((ROOT / "configs/diagnostic_control_server.json").read_text())
    pressure = json.loads((ROOT / "configs/diagnostic_pressure_server.json").read_text())
    assert control["max_total_tokens"] > pressure["max_total_tokens"]
    assert pressure["max_total_tokens"] >= 2 * 5888
    assert control["swa_full_tokens_ratio"] == pressure["swa_full_tokens_ratio"] == 0.5
    assert control["page_size"] == pressure["page_size"] == 256


def test_exposure_barrier_configs_isolate_full_and_swa_pressure():
    control = json.loads((ROOT / "configs/exposure_control_server.json").read_text())
    full = json.loads((ROOT / "configs/exposure_full_only_server.json").read_text())
    swa = json.loads((ROOT / "configs/exposure_swa_only_server.json").read_text())
    joint = json.loads((ROOT / "configs/exposure_joint_server.json").read_text())
    assert control["expected_pool_tokens"] == {"full": 32768, "swa": 16384}
    assert full["expected_pool_tokens"] == {"full": 16384, "swa": 16384}
    assert swa["expected_pool_tokens"] == {"full": 32768, "swa": 8192}
    assert joint["expected_pool_tokens"] == {"full": 16384, "swa": 8192}
    assert {config["page_size"] for config in (control, full, swa, joint)} == {256}


def test_exposure_suite_has_complete_three_strategy_matrix():
    runner = load_script("run_exposure_barrier_suite.py")
    cases = runner.build_cases(123)
    assert len(cases) == 10
    assert cases[0]["regime"] == "control"
    for regime in ("full_only", "swa_only", "joint"):
        selected = [case for case in cases if case["regime"] == regime]
        assert {case["strategy"] for case in selected} == {
            "lru",
            "slru",
            "exposure_barrier",
        }
        barrier = next(case for case in selected if case["strategy"] == "exposure_barrier")
        assert barrier["policy"] == "lru"
        assert barrier["exposure_barrier"] is True


def test_exposure_barrier_defers_newly_exposed_parent(monkeypatch):
    from sglang.srt.mem_cache.unified_cache_components.full_component import FullComponent
    from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType

    class Node:
        def __init__(self, node_id, priority, parent=None, exposable=True):
            self.id = node_id
            self.priority = priority
            self.parent = parent
            self.exposable = exposable

        def __lt__(self, other):
            return self.id < other.id

    class Strategy:
        @staticmethod
        def get_priority(node):
            return node.priority

    class Cache:
        def __init__(self, expose_parent=True):
            self.eviction_strategy = Strategy()
            self.agentkv_diagnostics = None
            self.order = []
            self.parent = Node(3, 1, exposable=expose_parent)
            self.first = Node(1, 0, self.parent)
            self.second = Node(2, 10)
            self.evictable_device_leaves = {self.first, self.second}

        def _evict_device_leaf(self, node, tracker):
            self.order.append(node.id)
            self.evictable_device_leaves.discard(node)
            tracker[ComponentType.FULL] += 1
            if node.parent is not None and node.parent.exposable:
                self.evictable_device_leaves.add(node.parent)

    def run(request, enabled, expose_parent=True):
        cache = Cache(expose_parent=expose_parent)
        component = FullComponent.__new__(FullComponent)
        component.cache = cache
        monkeypatch.setenv("AGENTKV_EXPOSURE_BARRIER", "1" if enabled else "0")
        tracker = {ComponentType.FULL: 0}
        params = type("Params", (), {"num_tokens": request})()
        component.drive_eviction(params, tracker)
        return cache.order, tracker[ComponentType.FULL]

    assert run(2, False) == ([1, 3], 2)
    assert run(2, True) == ([1, 2], 2)
    assert run(3, True) == ([1, 2, 3], 3)
    assert run(3, True, expose_parent=False) == ([1, 2], 2)


def test_swa_exposure_barrier_spreads_reclaim_across_chains(monkeypatch):
    from sglang.srt.mem_cache.unified_cache_components.swa_component import SWAComponent
    from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType

    class ComponentData:
        def __init__(self):
            self.value = [0]
            self.lock_ref = 0

    class Node:
        def __init__(self, node_id, parent=None):
            self.id = node_id
            self.parent = parent
            self.component_data = {ComponentType.SWA: ComponentData()}

    class LRU:
        def __init__(self, nodes):
            self.nodes = list(nodes)

        def in_list(self, node):
            return node in self.nodes

        def get_lru_no_lock(self):
            return self.nodes[0] if self.nodes else None

        def get_prev_no_lock(self, node):
            index = self.nodes.index(node)
            return self.nodes[index + 1] if index + 1 < len(self.nodes) else None

        def remove_node(self, node):
            self.nodes.remove(node)

    class Cache:
        def __init__(self):
            self.root = Node(0)
            self.a_parent = Node(2, self.root)
            self.a_leaf = Node(1, self.a_parent)
            self.b_parent = Node(4, self.root)
            self.b_leaf = Node(3, self.b_parent)
            self.lru = LRU(
                [self.a_leaf, self.a_parent, self.b_leaf, self.b_parent]
            )
            self.lru_lists = {ComponentType.SWA: self.lru}
            self.evictable_device_leaves = {self.a_leaf, self.b_leaf}
            self.agentkv_diagnostics = None
            self.order = []

        def _evict_device_leaf(self, node, tracker):
            self.order.append(node.id)
            self.evictable_device_leaves.discard(node)
            self.lru.remove_node(node)
            tracker[ComponentType.SWA] += 1
            if node.parent is not self.root:
                self.evictable_device_leaves.add(node.parent)

        def _evict_component_and_detach_lru(self, node, component, target, tracker):
            self.order.append(node.id)
            self.lru.remove_node(node)
            tracker[ComponentType.SWA] += 1

        def _cascade_evict(self, node, component, tracker):
            return None

    def run(request, enabled):
        cache = Cache()
        component = SWAComponent.__new__(SWAComponent)
        component.cache = cache
        monkeypatch.setenv("AGENTKV_EXPOSURE_BARRIER", "1" if enabled else "0")
        tracker = {ComponentType.SWA: 0}
        params = type("Params", (), {"swa_num_tokens": request})()
        component.drive_eviction(params, tracker)
        return cache.order, tracker[ComponentType.SWA]

    assert run(2, False) == ([1, 2], 2)
    assert run(2, True) == ([1, 3], 2)
    assert run(3, True) == ([1, 3, 2], 3)


def test_large_unified_barrier_matrix_and_frozen_inputs():
    runner = load_script("run_large_unified_barrier.py")
    assert runner.CASES == (
        {"strategy": "lru", "policy": "lru", "exposure_barrier": False},
        {"strategy": "slru", "policy": "slru", "exposure_barrier": False},
        {
            "strategy": "unified_exposure_barrier",
            "policy": "lru",
            "exposure_barrier": True,
        },
    )
    prepared = ROOT / "data/workloads/exploration_1h_v4"
    config = ROOT / "configs/large_unified_barrier_server.json"
    verified = runner.verify_inputs(prepared, config)
    assert verified["sessions"] == 20
    assert verified["requests"] == 1206
    resolved = json.loads(config.read_text())
    assert resolved["max_total_tokens"] == 524288
    assert resolved["swa_full_tokens_ratio"] == 0.1
