#!/usr/bin/env python3
"""Create a separate official-wheel copy with observation-only hooks."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source anchor: {old[:100]!r}; found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_unified(text):
    edits = [
        ('from sglang.srt.mem_cache.utils import (\n',
         'from sglang.srt.mem_cache.mechanism_observer import MechanismObserver\nfrom sglang.srt.mem_cache.utils import (\n'),
        ('        self.reset()\n        logger.info(f"Init Unified RadixTree with components {self.tree_components}")',
         '        self.agentkv_observer = MechanismObserver(self)\n        self.reset()\n        logger.info(f"Init Unified RadixTree with components {self.tree_components}")'),
        ('        self.root_node = UnifiedTreeNode(self.tree_components)\n',
         '        self.agentkv_observer.flush()\n        self.root_node = UnifiedTreeNode(self.tree_components)\n'),
        ('        return self._match_post_processor(\n            params,\n            value,\n            best_match_node,\n            best_match_device_node,\n            best_match_device_value_len,\n        )\n',
         '        result = self._match_post_processor(\n            params,\n            value,\n            best_match_node,\n            best_match_device_node,\n            best_match_device_value_len,\n        )\n        self.agentkv_observer.matched(key, params, result)\n        return result\n'),
        ('        result = self._insert_helper(self.root_node, key, value, params)\n        return result',
         '        result = self._insert_helper(self.root_node, key, value, params)\n        self.agentkv_observer.inserted(key, params, result)\n        return result'),
        ('        tracker = {ct: 0 for ct in self.tree_components}\n\n        for component in self._components_tuple:',
         '        tracker = {ct: 0 for ct in self.tree_components}\n        self.agentkv_observer.begin_reclaim(params)\n\n        for component in self._components_tuple:'),
        ('        self.update_eviction_metrics(sum(tracker.values()), start_time)\n',
         '        self.agentkv_observer.end_reclaim(tracker)\n        self.update_eviction_metrics(sum(tracker.values()), start_time)\n'),
        ('        self._update_evictable_leaf_sets(node)\n        return result\n\n    def dec_lock_ref(',
         '        self._update_evictable_leaf_sets(node)\n        self.agentkv_observer.lock(node, "lock")\n        return result\n\n    def dec_lock_ref('),
        ('        self._update_evictable_leaf_sets(node)\n        # TODO: delta is not aggregated from components; no caller uses it yet.',
         '        self._update_evictable_leaf_sets(node)\n        self.agentkv_observer.lock(node, "unlock")\n        # TODO: delta is not aggregated from components; no caller uses it yet.'),
        ('            result = self.insert(insert_params)\n\n            # Free unaligned tail',
         '            result = self.insert(insert_params)\n            self.agentkv_observer.commit(req, kv_committed_len, page_aligned_len, True)\n\n            # Free unaligned tail'),
        ('        result = self.insert(insert_params)\n\n        # Match prefix',
         '        result = self.insert(insert_params)\n        self.agentkv_observer.commit(req, len(token_ids), page_aligned_len, False)\n\n        # Match prefix'),
        ('        self._update_evictable_leaf_sets(new_node)\n        self._update_evictable_leaf_sets(child)\n        return new_node',
         '        self._update_evictable_leaf_sets(new_node)\n        self._update_evictable_leaf_sets(child)\n        self.agentkv_observer.split(new_node, child)\n        return new_node'),
    ]
    for old, new in edits:
        text = replace(text, old, new)
    return text


def patch_full(text):
    text = replace(text, '        return freed, host_freed\n',
                   '        self.cache.agentkv_observer.freed(node, "full", freed)\n        return freed, host_freed\n')
    text = replace(text,
                   '        ct = self.component_type\n        while tracker[ct] < request and heap:',
                   '        ct = self.component_type\n        self.cache.agentkv_observer.begin_drive("full", request, tracker, heap)\n        while tracker[ct] < request and heap:')
    text = replace(text, '            self.cache._evict_device_leaf(x, tracker)\n',
                   '            observation_before = self.cache.agentkv_observer.before_step(x, tracker)\n            self.cache._evict_device_leaf(x, tracker)\n            self.cache.agentkv_observer.after_step(observation_before, tracker)\n')
    text = replace(text, '\n    def drive_host_eviction(',
                   '        self.cache.agentkv_observer.end_drive("full", request, tracker)\n\n    def drive_host_eviction(')
    return text


def patch_swa(text):
    text = replace(text, '        return freed, host_freed\n',
                   '        self.cache.agentkv_observer.freed(node, "swa", freed)\n        return freed, host_freed\n')
    text = replace(text,
                   '        x = lru.get_lru_no_lock()\n        while tracker[ct] < request and x is not None and lru.in_list(x):',
                   '        x = lru.get_lru_no_lock()\n        self.cache.agentkv_observer.begin_drive("swa", request, tracker, None)\n        while tracker[ct] < request and x is not None and lru.in_list(x):')
    text = replace(text, '            assert x.component_data[ct].value is not None\n',
                   '            observation_before = self.cache.agentkv_observer.before_step(x, tracker)\n            assert x.component_data[ct].value is not None\n')
    text = replace(text, '                x = x_next\n\n    def acquire_component_lock(',
                   '                x = x_next\n            self.cache.agentkv_observer.after_step(observation_before, tracker)\n        self.cache.agentkv_observer.end_drive("swa", request, tracker)\n\n    def acquire_component_lock(')
    return text


def prepare(destination):
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / "runtime"):
        raise ValueError("Overlay must stay inside the experiment runtime directory")
    lock = json.loads((ROOT / "configs/environment.lock.json").read_text())
    wheel = ROOT / lock["engine"]["wheel"]
    if digest(wheel) != lock["engine"]["wheel_sha256"]:
        raise ValueError("Official wheel SHA256 mismatch")
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(wheel) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.startswith("sglang/")]
        for entry in entries:
            if '..' in Path(entry.filename).parts:
                raise ValueError("Unsafe wheel path")
            archive.extract(entry, destination)
    changes = {}
    for relative, patcher in (
        ("srt/mem_cache/unified_radix_cache.py", patch_unified),
        ("srt/mem_cache/unified_cache_components/full_component.py", patch_full),
        ("srt/mem_cache/unified_cache_components/swa_component.py", patch_swa),
    ):
        target = destination / "sglang" / relative
        pristine = digest(target)
        if pristine != lock["engine"]["source_hashes"][relative]:
            raise ValueError(f"Pristine source mismatch: {relative}")
        patched = patcher(target.read_text())
        ast.parse(patched)
        target.write_text(patched)
        changes[relative] = {"pristine_sha256": pristine, "observed_sha256": digest(target)}
    module = ROOT / "scripts/mechanism_observer.py"
    installed = destination / "sglang/srt/mem_cache/mechanism_observer.py"
    shutil.copyfile(module, installed)
    report = {"schema": "agentkv.mechanism_overlay.v1", "overlay": str(destination.relative_to(ROOT)),
              "official_wheel_sha256": digest(wheel), "observer_sha256": digest(module),
              "files": changes, "native_decision_rules_unchanged": True,
              "prior_venv_unchanged": True, "rank_zero_only": True}
    (destination / "observation.lock.json").write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output), indent=2))
