"""Bounded reuse units over the official Full/SWA radix tree.

One unit contains an input boundary, its resident Full ancestors, and the SWA
window needed to match there. Both drivers apply the same dependency guard and
the same oldest-unit fallback. No session labels, clocks, or return forecasts
are used. Native reference locks, allocations, and atomic leaf frees remain in
charge of physical legality.
"""

from collections import Counter, OrderedDict
import heapq
import json
import os
from pathlib import Path


class BoundedFrontier:
    def __init__(self, cache, settings=None, component_types=None):
        if settings is None:
            source = os.environ.get("AGENTKV_FRONTIER_SETTINGS")
            settings = json.loads(Path(source).read_text()) if source else {"enabled": False}
        self.cache, self.settings = cache, dict(settings)
        self.enabled = bool(settings.get("enabled", False))
        self.split_only = bool(settings.get("split_only", False))
        if self.enabled and self.split_only:
            raise ValueError("Choose protection or structural ablation, not both")
        self.active = self.enabled or self.split_only
        self.max_units = int(settings.get("max_units", 8))
        self.full_budget = int(settings.get("full_budget_tokens", 262144))
        self.swa_budget = int(settings.get("swa_budget_tokens", 4096))
        if self.active and min(self.max_units, self.full_budget, self.swa_budget) <= 0:
            raise ValueError("Frontier limits must be positive")
        self.units = OrderedDict()
        self.required = {}
        self.counts = Counter()
        self.seq = self.tick = 0
        self.full_tokens = self.swa_tokens = 0
        self.stream = None
        if self.active:
            if component_types is None:
                from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType
                component_types = ComponentType.FULL, ComponentType.SWA
            self.full_ct, self.swa_ct = component_types
            if set(cache.tree_components) != set(component_types) or cache.cache_controller is not None:
                raise ValueError("Frontier prototype requires device-only Full/SWA cache")
            self.required = {self.full_ct: set(), self.swa_ct: set()}
        destination = os.environ.get("AGENTKV_FRONTIER_METRICS_DIR")
        if destination and self.active:
            import torch
            rank = torch.distributed.get_rank() if torch.distributed.is_initialized() else 0
            if rank == 0:
                Path(destination).mkdir(parents=True, exist_ok=True)
                self.stream = (Path(destination) / f"frontier.rank0.pid{os.getpid()}.jsonl").open("x", buffering=65536)
                self.emit("start", settings=self.settings)

    def emit(self, kind, **fields):
        if self.stream is None:
            return
        self.seq += 1
        self.stream.write(json.dumps({"schema": "agentkv.bounded_frontier.v1", "event_seq": self.seq,
                                      "event_type": kind, "units": len(self.units),
                                      "full_dependency_tokens": self.full_tokens,
                                      "swa_dependency_tokens": self.swa_tokens,
                                      "counters": dict(self.counts), **fields}, separators=(",", ":")) + "\n")
        self.stream.flush()

    def reset(self):
        if not self.active:
            return
        self.emit("flush_previous")
        self.units.clear()
        self.required = {self.full_ct: set(), self.swa_ct: set()}
        self.counts.clear()
        self.full_tokens = self.swa_tokens = self.tick = 0
        self.emit("flush")

    def path(self, anchor):
        nodes = []
        root, node = self.cache.root_node, anchor
        while node is not root:
            if node.parent is None or node.component_data[self.full_ct].value is None:
                return None
            if node.parent.children.get(node.key.child_key(self.cache.page_size)) is not node:
                return None
            nodes.append(node)
            node = node.parent
        return nodes

    def dependencies(self, anchor):
        full = self.path(anchor)
        if not full:
            return None
        swa, covered = [], 0
        for node in full:
            value = node.component_data[self.swa_ct].value
            if value is None:
                return None
            swa.append(node)
            covered += len(value)
            if covered >= self.cache.sliding_window_size:
                return set(full), set(swa)
        # The native validator starts at +inf at the root, allowing a prefix
        # shorter than one window if the entire available path is present.
        return set(full), set(swa)

    def drop(self, anchor_id, reason):
        unit = self.units.pop(anchor_id)
        self.counts["drop_" + reason] += 1
        return unit

    def refresh(self):
        required = {self.full_ct: set(), self.swa_ct: set()}
        for anchor_id, unit in list(self.units.items()):
            dependencies = self.dependencies(unit["anchor"])
            if dependencies is None:
                self.drop(anchor_id, "invalid")
                continue
            unit["dependencies"] = dependencies
            required[self.full_ct].update(dependencies[0])
            required[self.swa_ct].update(dependencies[1])
        self.required = required
        self.full_tokens = sum(len(node.component_data[self.full_ct].value) for node in required[self.full_ct])
        self.swa_tokens = sum(len(node.component_data[self.swa_ct].value) for node in required[self.swa_ct])

    def trim_budget(self):
        self.refresh()
        while self.units and (len(self.units) > self.max_units or self.full_tokens > self.full_budget
                              or self.swa_tokens > self.swa_budget):
            self.drop(next(iter(self.units)), "budget")
            self.refresh()

    def register(self, anchor, request_id=None):
        if not self.enabled:
            return
        self.refresh()
        dependencies = self.dependencies(anchor)
        if dependencies is None:
            self.counts["register_unavailable"] += 1
            return
        new_full = dependencies[0]
        # Exact tree ancestry, including namespace, defines continuation. A
        # divergent branch remains a separate unit; no semantic session guess.
        for anchor_id, unit in list(self.units.items()):
            old_anchor = unit["anchor"]
            if old_anchor in new_full or anchor in unit["dependencies"][0]:
                self.drop(anchor_id, "replaced_boundary")
        self.tick += 1
        self.units[anchor.id] = {"anchor": anchor, "dependencies": dependencies, "tick": self.tick}
        self.counts["registered"] += 1
        self.trim_budget()
        self.emit("register", request_id=request_id, anchor_node_id=int(anchor.id),
                  input_boundary_tokens=sum(len(node.key) for node in new_full))

    def input_anchor(self, key, target):
        root = self.cache.root_node
        node, rest, depth = root, key[:target], 0
        while len(rest):
            child = node.children.get(rest.child_key(self.cache.page_size))
            if child is None or child.component_data[self.full_ct].value is None:
                return None
            count = child.key.match(rest, page_size=self.cache.page_size)
            if count <= 0:
                return None
            if count < len(child.key):
                child = self.cache._split_node(child.key, child, count)
                self.counts["input_boundary_splits"] += 1
            depth += count
            node, rest = child, rest[count:]
        if depth != target or node is root:
            return None
        # Isolate only the needed page-aligned tail, rather than protecting an
        # entire compressed node of unrelated old SWA history.
        tail = ((self.cache.sliding_window_size + self.cache.page_size - 1)
                // self.cache.page_size * self.cache.page_size)
        if len(node.key) > tail:
            self.cache._split_node(node.key, node, len(node.key) - tail)
            self.counts["window_tail_splits"] += 1
        return node

    def committed(self, req, key, finished):
        if not self.active or getattr(req, "agentkv_frontier_staged", False):
            return
        target = len(req.origin_input_ids) // self.cache.page_size * self.cache.page_size
        if target <= 0 or len(key) < target:
            return
        anchor = self.input_anchor(key, target)
        if anchor is None:
            self.counts["input_boundary_absent"] += 1
            return
        req.agentkv_frontier_staged = True
        self.counts["input_staged_finished" if finished else "input_staged_prefill"] += 1
        self.register(anchor, str(req.rid))
        if self.split_only:
            self.emit("stage", request_id=str(req.rid), finished=bool(finished))

    def blocks(self, node, component, atomic=False):
        if not self.enabled:
            return False
        if node in self.required[component]:
            return True
        return atomic and any(node in required for required in self.required.values())

    def relax(self, component, candidates):
        candidates = list(candidates)
        for anchor_id, unit in list(self.units.items()):
            full, swa = unit["dependencies"]
            for node in candidates:
                required = full if component == self.full_ct else swa
                atomic = node in self.cache.evictable_device_leaves
                if node in required or (atomic and (node in full or node in swa)):
                    self.drop(anchor_id, "pressure_" + component.name.lower() if hasattr(component, "name") else "pressure_" + str(component))
                    self.refresh()
                    return True
        return False

    def freed(self, node, component, freed_tokens):
        if not self.enabled or freed_tokens <= 0:
            return
        label = "full" if component == self.full_ct else "swa"
        self.counts["freed_" + label + "_tokens"] += freed_tokens
        for anchor_id, unit in list(self.units.items()):
            dependency = unit["dependencies"][0 if component == self.full_ct else 1]
            if node in dependency:
                self.drop(anchor_id, "dependency_free")
        # Called inside native free before Full is tombstoned. Removed units
        # prevent retention of stale references even at that intermediate point.
        self.refresh()

    def drive(self, component, params, tracker):
        self.trim_budget()
        ct = component.component_type
        before = dict(tracker)
        label = "full" if ct == self.full_ct else "swa"
        self.counts["drive_" + label] += 1
        if ct == self.full_ct:
            self.drive_full(params.num_tokens, tracker)
        elif ct == self.swa_ct:
            self.drive_swa(component, params.swa_num_tokens, tracker)
        else:
            raise ValueError("Unexpected frontier component")
        self.refresh()
        self.emit("drive", pool=ct.name.lower() if hasattr(ct, "name") else str(ct),
                  requested_tokens=int(params.num_tokens if ct == self.full_ct else params.swa_num_tokens),
                  released_delta={"full": int(tracker[self.full_ct] - before[self.full_ct]),
                                  "swa": int(tracker[self.swa_ct] - before[self.swa_ct])},
                  released_cumulative={"full": int(tracker[self.full_ct]), "swa": int(tracker[self.swa_ct])})

    def drive_full(self, requested, tracker):
        cache, ct = self.cache, self.full_ct
        heap = [(cache.eviction_strategy.get_priority(node), node) for node in cache.evictable_device_leaves]
        heapq.heapify(heap)
        deferred = []
        while tracker[ct] < requested and (heap or deferred):
            if not heap:
                deferred = [item for item in deferred if item[1] in cache.evictable_device_leaves]
                if not deferred or not self.relax(ct, (node for _, node in deferred)):
                    break
                heap, deferred = deferred, []
                heapq.heapify(heap)
            score, node = heapq.heappop(heap)
            if node not in cache.evictable_device_leaves:
                continue
            if self.blocks(node, ct, atomic=True):
                deferred.append((score, node))
                self.counts["deferred_full"] += 1
                continue
            cache._evict_device_leaf(node, tracker)
            self.counts["selected_full"] += 1
            if node.parent is not None and node.parent in cache.evictable_device_leaves:
                heapq.heappush(heap, (cache.eviction_strategy.get_priority(node.parent), node.parent))

    def drive_swa(self, component, requested, tracker):
        from sglang.srt.mem_cache.unified_cache_components.tree_component import EvictLayer
        cache, ct = self.cache, self.swa_ct
        lru = cache.lru_lists[ct]
        node = lru.get_lru_no_lock()
        deferred = []
        while tracker[ct] < requested:
            if node is None:
                deferred = [candidate for candidate in deferred if lru.in_list(candidate)
                            and candidate.component_data[ct].lock_ref == 0]
                if not deferred or not self.relax(ct, deferred):
                    break
                node, deferred = lru.get_lru_no_lock(), []
                if node is None:
                    break
            if not lru.in_list(node):
                break
            atomic = node in cache.evictable_device_leaves
            if self.blocks(node, ct, atomic):
                deferred.append(node)
                self.counts["deferred_swa"] += 1
                node = lru.get_prev_no_lock(node)
                continue
            next_node = lru.get_prev_no_lock(node)
            if atomic:
                cache._evict_device_leaf(node, tracker)
                if not lru.in_list(next_node):
                    next_node = lru.get_lru_no_lock()
            else:
                cache._evict_component_and_detach_lru(node, component, target=EvictLayer.DEVICE, tracker=tracker)
                cache._cascade_evict(node, component, tracker)
            self.counts["selected_swa"] += 1
            node = next_node
