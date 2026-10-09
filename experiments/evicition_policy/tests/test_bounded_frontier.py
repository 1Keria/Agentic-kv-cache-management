"""Budget, legal reclamation, and official split/lock compatibility on CPU."""

import ast
from collections import defaultdict
from enum import IntEnum, Flag, auto
from functools import partial
import importlib.util
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bounded_frontier import BoundedFrontier
from prepare_frontier_overlay import patch_component, patch_unified


class CT(IntEnum):
    FULL = 0
    SWA = 1


class Layer(Flag):
    DEVICE = auto()
    HOST = auto()
    ALL = DEVICE | HOST


class Values(list):
    def __getitem__(self, item):
        value = super().__getitem__(item)
        return Values(value) if isinstance(item, slice) else value

    def clone(self):
        return Values(self)


class Key:
    def __init__(self, values, namespace=None):
        self.values, self.extra_key = list(values), namespace

    def __len__(self):
        return len(self.values)

    def __getitem__(self, item):
        return Key(self.values[item], self.extra_key)

    def child_key(self, page_size):
        return self.extra_key, tuple(self.values[:page_size])

    def match(self, other, page_size):
        if self.extra_key != other.extra_key:
            return 0
        count = 0
        for a, b in zip(self.values, other.values):
            if a != b:
                break
            count += 1
        return count // page_size * page_size


def component_data():
    return SimpleNamespace(value=None, host_value=None, lock_ref=0, host_lock_ref=0, metadata={})


lock = json.loads((ROOT / 'configs/environment.lock.json').read_text())
with zipfile.ZipFile(ROOT / lock['engine']['wheel']) as archive:
    sources = {name: archive.read('sglang/srt/mem_cache/' + name).decode() for name in (
        'unified_radix_cache.py', 'unified_cache_components/full_component.py',
        'unified_cache_components/swa_component.py')}


def extract(source, names, class_name=None):
    nodes = ast.parse(source).body
    if class_name:
        nodes = next(node for node in nodes if isinstance(node, ast.ClassDef) and node.name == class_name).body
    return ast.Module(body=[node for node in nodes if getattr(node, 'name', '') in names], type_ignores=[])


clock = itertools.count()
namespace = {'ComponentType': CT, 'ComponentData': component_data, 'defaultdict': defaultdict,
             'partial': partial, '_NUM_COMPONENT_TYPES': 2,
             'get_and_increase_time_counter': lambda: next(clock),
             'split_node_hash_value': lambda values, split, page: (None, None),
             'next_component_uuid': lambda: next(clock)}


def execute_ast(tree):
    code = 'from __future__ import annotations\n' + ast.unparse(tree)
    exec(compile(code, '<official-wheel-cpu-fixture>', 'exec'), namespace)


execute_ast(extract(sources['unified_radix_cache.py'], {'UnifiedTreeNode', 'UnifiedLRUList'}))
Node, LRU = namespace['UnifiedTreeNode'], namespace['UnifiedLRUList']
execute_ast(extract(sources['unified_radix_cache.py'], {'_split_node'}, 'UnifiedRadixCache'))
official_split = namespace['_split_node']
methods = {}
for component, class_name in ((CT.FULL, 'FullComponent'), (CT.SWA, 'SWAComponent')):
    execute_ast(extract(sources['unified_cache_components/' + class_name.replace('Component', '').lower() + '_component.py'],
                        {'redistribute_on_node_split', 'acquire_component_lock', 'release_component_lock'}, class_name))
    methods[component] = {name: namespace[name] for name in (
        'redistribute_on_node_split', 'acquire_component_lock', 'release_component_lock')}


class Cache:
    tree_components = (CT.FULL, CT.SWA)
    cache_controller = None
    page_size = 2
    sliding_window_size = 2
    _split_node = official_split

    def __init__(self):
        self.root_node = Node(self.tree_components)
        self.root_node.key = Key([])
        self.evictable_device_leaves = set()
        self.lru_lists = {ct: LRU(ct, self.tree_components) for ct in self.tree_components}
        self.host_lru_lists = {ct: LRU(ct, self.tree_components) for ct in self.tree_components}
        self.component_evictable_size_ = defaultdict(int)
        self.component_protected_size_ = defaultdict(int)
        self.components = {}
        for ct in self.tree_components:
            component = SimpleNamespace(component_type=ct, cache=self, sliding_window_size=self.sliding_window_size)
            for name, function in methods[ct].items():
                setattr(component, name, partial(function, component))
            self.components[ct] = component
        self._components_tuple = tuple(self.components.values())
        self.eviction_strategy = SimpleNamespace(get_priority=lambda node: node.last_access_time)
        self.victims = []

    def add(self, values, parent=None, namespace=None, locked=False):
        parent = parent or self.root_node
        node = Node(self.tree_components)
        node.key, node.parent = Key(values, namespace), parent
        parent.children[node.key.child_key(self.page_size)] = node
        for ct in self.tree_components:
            node.component_data[ct].value = Values(values)
            node.component_data[ct].lock_ref = int(locked)
            self.lru_lists[ct].insert_mru(node)
            (self.component_protected_size_ if locked else self.component_evictable_size_)[ct] += len(values)
        self._update_evictable_leaf_sets(node)
        self._update_evictable_leaf_sets(parent)
        return node

    def _update_evictable_leaf_sets(self, node):
        if node is self.root_node:
            return
        self.evictable_device_leaves.discard(node)
        if not node.children and node.component_data[CT.FULL].value is not None and not any(cd.lock_ref for cd in node.component_data):
            self.evictable_device_leaves.add(node)

    def _for_each_component_lru(self, node, method, skip_existing=False):
        for ct, lru in self.lru_lists.items():
            if node.component_data[ct].value is not None and (not skip_existing or not lru.in_list(node)):
                method(lru, node)

    def free(self, node, ct, tracker):
        cd = node.component_data[ct]
        if cd.value is not None:
            assert cd.lock_ref == 0
            freed = len(cd.value)
            tracker[ct] += freed
            self.component_evictable_size_[ct] -= freed
            cd.value = None
            self.frontier.freed(node, ct, freed)
        if self.lru_lists[ct].in_list(node):
            self.lru_lists[ct].remove_node(node)

    def _evict_device_leaf(self, node, tracker):
        assert node in self.evictable_device_leaves
        self.victims.append(('atomic', node.id))
        for ct in self.tree_components:
            self.free(node, ct, tracker)
        self.evictable_device_leaves.discard(node)
        del node.parent.children[node.key.child_key(self.page_size)]
        self._update_evictable_leaf_sets(node.parent)

    def _evict_component_and_detach_lru(self, node, component, target, tracker):
        self.victims.append(('swa', node.id))
        self.free(node, component.component_type, tracker)

    def _cascade_evict(self, node, component, tracker):
        self._update_evictable_leaf_sets(node)


def fixture(**settings):
    cache = Cache()
    cache.frontier = BoundedFrontier(cache, {'enabled': True, 'max_units': 8,
                                           'full_budget_tokens': 100, 'swa_budget_tokens': 100,
                                           **settings}, component_types=cache.tree_components)
    return cache, cache.frontier


class FrontierTests(unittest.TestCase):
    def test_disabled_needs_no_tree_or_engine_import(self):
        frontier = BoundedFrontier(None, {'enabled': False})
        frontier.reset()
        frontier.committed(None, None, False)
        self.assertFalse(frontier.units)

    def test_shared_dependencies_are_counted_once_and_branches_coexist(self):
        cache, frontier = fixture(full_budget_tokens=8, swa_budget_tokens=4)
        common = cache.add([1, 2, 3, 4])
        left = cache.add([5, 6], common)
        right = cache.add([7, 8], common)
        frontier.register(left)
        frontier.register(right)
        self.assertEqual((len(frontier.units), frontier.full_tokens, frontier.swa_tokens), (2, 8, 4))
        self.assertTrue(frontier.blocks(common, CT.FULL))
        self.assertFalse(frontier.blocks(common, CT.SWA))

    def test_continuation_replaces_boundary_but_namespaces_do_not(self):
        cache, frontier = fixture()
        first = cache.add([1, 2], namespace='a')
        second = cache.add([3, 4], first, namespace='a')
        other = cache.add([1, 2], namespace='b')
        frontier.register(first)
        frontier.register(second)
        frontier.register(other)
        self.assertEqual(set(frontier.units), {second.id, other.id})

    def test_budget_revokes_oldest_and_oversized_unit_is_not_pinned(self):
        cache, frontier = fixture(full_budget_tokens=4)
        a, b = cache.add([1, 2, 3, 4]), cache.add([5, 6, 7, 8])
        frontier.register(a)
        frontier.register(b)
        self.assertEqual(list(frontier.units), [b.id])
        long = cache.add(list(range(10, 16)))
        frontier.register(long)
        self.assertFalse(frontier.units)
        self.assertEqual(frontier.full_tokens, 0)

    def test_window_requires_contiguous_swa_and_detached_full_is_invalid(self):
        cache, frontier = fixture()
        a, b = cache.add([1, 2]), None
        b = cache.add([3, 4], a)
        frontier.register(b)
        a.component_data[CT.SWA].value = None
        frontier.refresh()
        self.assertEqual(len(frontier.units), 1)
        del a.children[b.key.child_key(2)]
        frontier.refresh()
        self.assertFalse(frontier.units)

    def test_official_split_preserves_values_and_lock_uuid_release(self):
        cache, frontier = fixture()
        original = cache.add(list(range(1, 9)), locked=True)
        original.component_data[CT.SWA].metadata['uuid'] = 99
        req = SimpleNamespace(rid='r', origin_input_ids=list(range(1, 7)))
        frontier.committed(req, Key(list(range(1, 9))), False)
        frontier.committed(req, Key(list(range(1, 9))), True)
        anchor = next(iter(frontier.units.values()))['anchor']
        self.assertEqual((frontier.full_tokens, frontier.swa_tokens, len(anchor.key)), (6, 2, 2))
        self.assertEqual(frontier.counts['registered'], 1)
        params = SimpleNamespace(skip_lock_node_ids={}, swa_uuid_for_lock=99)
        for component in cache._components_tuple:
            component.release_component_lock(original, params)
        cur, lengths = original, []
        while cur is not cache.root_node:
            self.assertTrue(all(cd.lock_ref == 0 for cd in cur.component_data))
            lengths.append(len(cur.component_data[CT.FULL].value))
            cur = cur.parent
        self.assertEqual(sum(lengths), 8)
        self.assertEqual(dict(cache.component_protected_size_), {CT.FULL: 0, CT.SWA: 0})

    def test_full_driver_skips_protected_then_revokes_for_progress(self):
        cache, frontier = fixture()
        old, newer, locked = cache.add([1, 2]), cache.add([3, 4]), cache.add([5, 6], locked=True)
        frontier.register(old)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        frontier.drive_full(4, tracker)
        self.assertEqual(cache.victims, [('atomic', newer.id), ('atomic', old.id)])
        self.assertEqual(tracker, {CT.FULL: 4, CT.SWA: 4})
        self.assertEqual(len(locked.component_data[CT.FULL].value), 2)
        self.assertEqual(frontier.counts['drop_pressure_full'], 1)

    def test_swa_internal_history_can_be_freed_while_unit_survives(self):
        cache, frontier = fixture()
        history = cache.add([1, 2])
        tail = cache.add([3, 4], history)
        tail.component_data[CT.SWA].lock_ref = 1
        cache._update_evictable_leaf_sets(tail)
        frontier.register(tail)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        mock_module = SimpleNamespace(EvictLayer=Layer)
        with patch.dict(sys.modules, {'sglang.srt.mem_cache.unified_cache_components.tree_component': mock_module}):
            frontier.drive_swa(cache.components[CT.SWA], 2, tracker)
        self.assertEqual(cache.victims, [('swa', history.id)])
        self.assertEqual(tracker, {CT.FULL: 0, CT.SWA: 2})
        self.assertEqual(len(frontier.units), 1)

    def test_swa_driver_atomic_free_checks_shared_unit_and_falls_back(self):
        cache, frontier = fixture()
        old, other = cache.add([1, 2]), cache.add([3, 4])
        frontier.register(old)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        with patch.dict(sys.modules, {'sglang.srt.mem_cache.unified_cache_components.tree_component': SimpleNamespace(EvictLayer=Layer)}):
            frontier.drive_swa(cache.components[CT.SWA], 4, tracker)
        self.assertEqual(cache.victims, [('atomic', other.id), ('atomic', old.id)])
        self.assertEqual(tracker, {CT.FULL: 4, CT.SWA: 4})
        self.assertFalse(frontier.units)

    def test_structural_ablation_does_not_protect(self):
        cache, frontier = fixture(enabled=False, split_only=True)
        cache.add(list(range(8)))
        frontier.committed(SimpleNamespace(rid='r', origin_input_ids=list(range(6))), Key(list(range(8))), True)
        self.assertEqual(frontier.counts['window_tail_splits'], 1)
        self.assertFalse(frontier.units)

    def test_removing_inactive_hooks_restores_official_asts(self):
        class Strip(ast.NodeTransformer):
            def visit_ImportFrom(self, node):
                return None if node.module and node.module.endswith('bounded_frontier') else node

            def visit_Assign(self, node):
                return None if 'agentkv_frontier' in ast.unparse(node) else self.generic_visit(node)

            def visit_Expr(self, node):
                return None if 'agentkv_frontier' in ast.unparse(node) else self.generic_visit(node)

            def visit_If(self, node):
                return None if 'agentkv_frontier' in ast.unparse(node.test) else self.generic_visit(node)

        for name, source in sources.items():
            with self.subTest(file=name):
                patched = (patch_unified if name == 'unified_radix_cache.py' else patch_component)(source)
                self.assertEqual(ast.dump(ast.parse(source)), ast.dump(Strip().visit(ast.parse(patched))))


if __name__ == '__main__':
    unittest.main()
