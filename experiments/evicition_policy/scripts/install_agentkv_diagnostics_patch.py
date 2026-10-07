#!/usr/bin/env python3
"""Install the read-only AgentKV diagnostics into the isolated SGLang wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime/venv/lib/python3.12/site-packages/sglang/srt/mem_cache"
BACKUP = ROOT / "runtime/diagnostics_pristine"
EXPECTED = {
    "unified_radix_cache.py": "3bce5c884efa7c8d2cab680cf18fcb1574bb96431b99f396c4b3fd6a1de1efc7",
    "unified_cache_components/full_component.py": "339cdb3ce23bb949d169ae2088326cc86f8fd35fc7746657c0e042719189330b",
    "unified_cache_components/swa_component.py": "2c85298a769db52be3e4438265ad8a483f12ee94a5930b488ad31d958769b624",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_unified(text: str) -> str:
    text = replace_once(
        text,
        "from sglang.srt.mem_cache.utils import (\n",
        "from sglang.srt.mem_cache.agentkv_diagnostics import get_diagnostics\nfrom sglang.srt.mem_cache.utils import (\n",
        "unified import",
    )
    text = replace_once(
        text,
        "        self.reset()\n        logger.info(f\"Init Unified RadixTree with components {self.tree_components}\")\n",
        "        self.agentkv_diagnostics = get_diagnostics(self)\n        self.reset()\n        logger.info(f\"Init Unified RadixTree with components {self.tree_components}\")\n",
        "diagnostics init",
    )
    text = replace_once(
        text,
        "    def _reset_full(self) -> None:\n        \"\"\"Full reset: destroy entire tree and all state.\"\"\"\n        self.root_node = UnifiedTreeNode(self.tree_components)\n",
        "    def _reset_full(self) -> None:\n        \"\"\"Full reset: destroy entire tree and all state.\"\"\"\n        self.agentkv_diagnostics.log_flush(self)\n        self.root_node = UnifiedTreeNode(self.tree_components)\n",
        "flush hook",
    )
    text = replace_once(
        text,
        "        return self._match_post_processor(\n            params,\n            value,\n            best_match_node,\n            best_match_device_node,\n            best_match_device_value_len,\n        )\n",
        "        result = self._match_post_processor(\n            params,\n            value,\n            best_match_node,\n            best_match_device_node,\n            best_match_device_value_len,\n        )\n        self.agentkv_diagnostics.log_demand(self, params, result, key)\n        return result\n",
        "demand hook",
    )
    text = replace_once(
        text,
        "        self._update_evictable_leaf_sets(node)\n        return result\n\n    def dec_lock_ref(\n",
        "        self._update_evictable_leaf_sets(node)\n        self.agentkv_diagnostics.log_lock(self, node, \"lock\")\n        return result\n\n    def dec_lock_ref(\n",
        "lock hook",
    )
    text = replace_once(
        text,
        "        self._update_evictable_leaf_sets(node)\n        # TODO: delta is not aggregated from components; no caller uses it yet.\n        return DecLockRefResult()\n",
        "        self._update_evictable_leaf_sets(node)\n        self.agentkv_diagnostics.log_lock(self, node, \"unlock\")\n        # TODO: delta is not aggregated from components; no caller uses it yet.\n        return DecLockRefResult()\n",
        "unlock hook",
    )
    text = replace_once(
        text,
        "            result = self.insert(insert_params)\n\n            # Free unaligned tail\n",
        "            result = self.insert(insert_params)\n            self.agentkv_diagnostics.log_commit(\n                self, req, kv_committed_len, page_aligned_len, result, True\n            )\n\n            # Free unaligned tail\n",
        "finished commit hook",
    )
    text = replace_once(
        text,
        "        result = self.insert(insert_params)\n\n        # Match prefix\n",
        "        result = self.insert(insert_params)\n        self.agentkv_diagnostics.log_commit(\n            self, req, len(token_ids), page_aligned_len, result, False\n        )\n\n        # Match prefix\n",
        "unfinished commit hook",
    )
    text = replace_once(
        text,
        "    ) -> UnifiedTreeNode:\n        new_node = UnifiedTreeNode(self.tree_components, priority=child.priority)\n",
        "    ) -> UnifiedTreeNode:\n        old_child_id = child.id\n        new_node = UnifiedTreeNode(self.tree_components, priority=child.priority)\n",
        "split capture",
    )
    text = replace_once(
        text,
        "        self._update_evictable_leaf_sets(new_node)\n        self._update_evictable_leaf_sets(child)\n        return new_node\n",
        "        self._update_evictable_leaf_sets(new_node)\n        self._update_evictable_leaf_sets(child)\n        self.agentkv_diagnostics.log_split(self, old_child_id, new_node, child)\n        return new_node\n",
        "split hook",
    )
    text = replace_once(
        text,
        "        self._record_store_event(new_node)\n        return new_node\n",
        "        self._record_store_event(new_node)\n        self.agentkv_diagnostics.log_store(self, new_node)\n        return new_node\n",
        "store hook",
    )
    return text


def patch_full(text: str) -> str:
    old = '''    def drive_eviction(
        self, params: EvictParams, tracker: dict[ComponentType, int]
    ) -> None:
        request = params.num_tokens
        heap = [
            (self.cache.eviction_strategy.get_priority(n), n)
            for n in self.cache.evictable_device_leaves
        ]
        heapq.heapify(heap)
        ct = self.component_type
        while tracker[ct] < request and heap:
            _, x = heapq.heappop(heap)
            if x not in self.cache.evictable_device_leaves:
                continue
            self.cache._evict_device_leaf(x, tracker)
            if x.parent is not None and x.parent in self.cache.evictable_device_leaves:
                heapq.heappush(
                    heap,
                    (self.cache.eviction_strategy.get_priority(x.parent), x.parent),
                )
'''
    new = '''    def drive_eviction(
        self, params: EvictParams, tracker: dict[ComponentType, int]
    ) -> None:
        request = params.num_tokens
        exposure_barrier = os.environ.get("AGENTKV_EXPOSURE_BARRIER") == "1"
        diagnostics = getattr(self.cache, "agentkv_diagnostics", None)
        if diagnostics is not None and not diagnostics.enabled:
            diagnostics = None
        if not exposure_barrier and diagnostics is None:
            heap = [
                (self.cache.eviction_strategy.get_priority(n), n)
                for n in self.cache.evictable_device_leaves
            ]
            heapq.heapify(heap)
            ct = self.component_type
            while tracker[ct] < request and heap:
                _, x = heapq.heappop(heap)
                if x not in self.cache.evictable_device_leaves:
                    continue
                self.cache._evict_device_leaf(x, tracker)
                if x.parent is not None and x.parent in self.cache.evictable_device_leaves:
                    heapq.heappush(
                        heap,
                        (self.cache.eviction_strategy.get_priority(x.parent), x.parent),
                    )
            return
        initial_candidates = list(self.cache.evictable_device_leaves)
        eviction_id = None
        if diagnostics is not None:
            eviction_id = diagnostics.begin_eviction(
                self.cache, "full", request, initial_candidates
            )
        heap = [
            (self.cache.eviction_strategy.get_priority(n), n)
            for n in initial_candidates
        ]
        heapq.heapify(heap)
        deferred_exposed = []
        ct = self.component_type
        step_seq = 0
        while tracker[ct] < request and (heap or deferred_exposed):
            if heap:
                _, x = heapq.heappop(heap)
                selection_stage = "initial"
            else:
                _, x = heapq.heappop(deferred_exposed)
                selection_stage = "deferred_exposed"
            if x not in self.cache.evictable_device_leaves:
                continue
            step_seq += 1
            victim_before = (
                diagnostics.snapshot_node(self.cache, x, "full")
                if diagnostics is not None
                else None
            )
            parent = x.parent
            before = tracker[ct]
            self.cache._evict_device_leaf(x, tracker)
            parent_exposed = (
                parent is not None and parent in self.cache.evictable_device_leaves
            )
            if diagnostics is not None:
                diagnostics.eviction_step(
                    self.cache,
                    eviction_id,
                    "full",
                    step_seq,
                    victim_before,
                    tracker[ct] - before,
                    parent_after=parent,
                    parent_exposed=parent_exposed,
                    step_kind="full_leaf",
                    selection_stage=selection_stage,
                )
            if parent_exposed:
                target_heap = deferred_exposed if exposure_barrier else heap
                heapq.heappush(
                    target_heap,
                    (self.cache.eviction_strategy.get_priority(parent), parent),
                )
        if diagnostics is not None:
            diagnostics.end_eviction(eviction_id, "full", request, tracker[ct], step_seq)
'''
    text = replace_once(text, old, new, "full drive_eviction")
    return replace_once(
        text,
        "import heapq\n",
        "import heapq\nimport os\n",
        "full os import",
    )


def patch_swa(text: str) -> str:
    old = '''    def drive_eviction(
        self, params: EvictParams, tracker: dict[ComponentType, int]
    ) -> None:
        request = params.swa_num_tokens
        ct = self.component_type
        lru = self.cache.lru_lists[ct]
        x = lru.get_lru_no_lock()
        while tracker[ct] < request and x is not None and lru.in_list(x):
            assert x.component_data[ct].value is not None
            if x in self.cache.evictable_device_leaves:
                # D-leaf: atomic eviction of all components
                x_next = lru.get_prev_no_lock(x)
                self.cache._evict_device_leaf(x, tracker)
                if not lru.in_list(x_next):
                    x_next = lru.get_lru_no_lock()
                x = x_next
            else:
                # Internal: tombstone SWA + cascade
                x_next = lru.get_prev_no_lock(x)
                self.cache._evict_component_and_detach_lru(
                    x, self, target=EvictLayer.DEVICE, tracker=tracker
                )
                self.cache._cascade_evict(x, self, tracker)
                x = x_next
'''
    new = '''    def drive_eviction(
        self, params: EvictParams, tracker: dict[ComponentType, int]
    ) -> None:
        request = params.swa_num_tokens
        ct = self.component_type
        lru = self.cache.lru_lists[ct]
        exposure_barrier = os.environ.get("AGENTKV_EXPOSURE_BARRIER") == "1"
        diagnostics = getattr(self.cache, "agentkv_diagnostics", None)
        if diagnostics is not None and not diagnostics.enabled:
            diagnostics = None
        if not exposure_barrier and diagnostics is None:
            x = lru.get_lru_no_lock()
            while tracker[ct] < request and x is not None and lru.in_list(x):
                assert x.component_data[ct].value is not None
                if x in self.cache.evictable_device_leaves:
                    # D-leaf: atomic eviction of all components
                    x_next = lru.get_prev_no_lock(x)
                    self.cache._evict_device_leaf(x, tracker)
                    if not lru.in_list(x_next):
                        x_next = lru.get_lru_no_lock()
                    x = x_next
                else:
                    # Internal: tombstone SWA + cascade
                    x_next = lru.get_prev_no_lock(x)
                    self.cache._evict_component_and_detach_lru(
                        x, self, target=EvictLayer.DEVICE, tracker=tracker
                    )
                    self.cache._cascade_evict(x, self, tracker)
                    x = x_next
            return
        initial_candidates = []
        candidate = lru.get_lru_no_lock()
        while candidate is not None and lru.in_list(candidate):
            initial_candidates.append(candidate)
            candidate = lru.get_prev_no_lock(candidate)
        candidate_paths = {}
        for candidate in initial_candidates:
            path = set()
            current = candidate
            while current is not None:
                path.add(id(current))
                current = current.parent
            candidate_paths[id(candidate)] = path
        eviction_id = None
        if diagnostics is not None:
            eviction_id = diagnostics.begin_eviction(
                self.cache, "swa", request, initial_candidates
            )
        step_seq = 0
        selected_ids = []
        deferred_same_chain = []
        primary_index = 0
        deferred_index = 0
        while tracker[ct] < request:
            x = None
            selection_stage = "initial"
            while primary_index < len(initial_candidates):
                candidate = initial_candidates[primary_index]
                primary_index += 1
                if not lru.in_list(candidate):
                    continue
                candidate_id = id(candidate)
                candidate_path = candidate_paths[candidate_id]
                same_chain = any(
                    selected_id in candidate_path
                    or candidate_id in candidate_paths[selected_id]
                    for selected_id in selected_ids
                )
                if exposure_barrier and same_chain:
                    deferred_same_chain.append(candidate)
                    continue
                x = candidate
                break
            if x is None:
                selection_stage = "deferred_same_chain"
                while deferred_index < len(deferred_same_chain):
                    candidate = deferred_same_chain[deferred_index]
                    deferred_index += 1
                    if lru.in_list(candidate):
                        x = candidate
                        break
            if x is None:
                break
            assert x.component_data[ct].value is not None
            selected_ids.append(id(x))
            step_seq += 1
            victim_before = (
                diagnostics.snapshot_node(self.cache, x, "swa")
                if diagnostics is not None
                else None
            )
            before = tracker[ct]
            if x in self.cache.evictable_device_leaves:
                # D-leaf: atomic eviction of all components
                self.cache._evict_device_leaf(x, tracker)
                step_kind = "full_leaf_cascade"
            else:
                # Internal: tombstone SWA + cascade
                self.cache._evict_component_and_detach_lru(
                    x, self, target=EvictLayer.DEVICE, tracker=tracker
                )
                self.cache._cascade_evict(x, self, tracker)
                step_kind = "swa_internal_tombstone"
            if diagnostics is not None:
                diagnostics.eviction_step(
                    self.cache,
                    eviction_id,
                    "swa",
                    step_seq,
                    victim_before,
                    tracker[ct] - before,
                    step_kind=step_kind,
                    selection_stage=selection_stage,
                )
        if diagnostics is not None:
            diagnostics.end_eviction(eviction_id, "swa", request, tracker[ct], step_seq)
'''
    text = replace_once(text, old, new, "swa drive_eviction")
    return replace_once(
        text,
        "from __future__ import annotations\n\n",
        "from __future__ import annotations\n\nimport os\n",
        "swa os import",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    module_source = ROOT / "scripts/sglang_agentkv_diagnostics.py"
    module_target = PACKAGE / "agentkv_diagnostics.py"
    previous_report_path = ROOT / "configs/environment.diagnostics.lock.json"
    previous_report = (
        json.loads(previous_report_path.read_text())
        if previous_report_path.exists()
        else {"files": {}}
    )
    report = {
        "schema": 2,
        "engine_version": "0.5.13.post1",
        "features": {
            "exposure_barrier_env": "AGENTKV_EXPOSURE_BARRIER=1",
            "full": "defer parents exposed during the current reclaim round",
            "swa": "defer same-chain candidates while independent frontier candidates remain",
        },
        "files": {},
    }
    patchers = {
        "unified_radix_cache.py": patch_unified,
        "unified_cache_components/full_component.py": patch_full,
        "unified_cache_components/swa_component.py": patch_swa,
    }
    BACKUP.mkdir(parents=True, exist_ok=True)
    for relative, patcher in patchers.items():
        target = PACKAGE / relative
        original_hash = digest(target)
        backup = BACKUP / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        patched = patcher((backup if backup.exists() else target).read_text()) if backup.exists() else None
        expected_patched = hashlib.sha256(patched.encode()).hexdigest() if patched is not None else None
        previous_patched = previous_report.get("files", {}).get(relative, {}).get("patched_sha256")
        if original_hash == EXPECTED[relative]:
            shutil.copy2(target, backup)
            patched = patcher(target.read_text())
            expected_patched = hashlib.sha256(patched.encode()).hexdigest()
            if not args.verify_only:
                target.write_text(patched)
        elif backup.exists() and digest(backup) == EXPECTED[relative]:
            patched = patcher(backup.read_text())
            expected_patched = hashlib.sha256(patched.encode()).hexdigest()
            if original_hash not in {expected_patched, previous_patched}:
                raise RuntimeError(f"Unexpected already-modified file: {target}")
            if not args.verify_only and original_hash != expected_patched:
                target.write_text(patched)
        else:
            raise RuntimeError(f"Pristine hash mismatch for {target}: {original_hash}")
        report["files"][relative] = {
            "pristine_sha256": EXPECTED[relative],
            "patched_sha256": expected_patched,
        }
    if not args.verify_only:
        shutil.copy2(module_source, module_target)
    report["files"]["agentkv_diagnostics.py"] = {
        "source_sha256": digest(module_source),
        "installed_sha256": digest(module_target) if module_target.exists() else None,
    }
    destination = ROOT / "configs/environment.diagnostics.lock.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
