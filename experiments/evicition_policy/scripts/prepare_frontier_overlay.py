#!/usr/bin/env python3
"""Install bounded frontier hooks into a new copy of the locked official wheel."""

import argparse
import ast
import json
from pathlib import Path
import shutil
import zipfile

from prepare_mechanism_observer import ROOT, digest, replace


def patch_unified(text):
    edits = [
        ('from sglang.srt.mem_cache.utils import (\n',
         'from sglang.srt.mem_cache.bounded_frontier import BoundedFrontier\nfrom sglang.srt.mem_cache.utils import (\n'),
        ('        self.reset()\n        logger.info(f"Init Unified RadixTree with components {self.tree_components}")',
         '        self.agentkv_frontier = BoundedFrontier(self)\n        self.reset()\n        logger.info(f"Init Unified RadixTree with components {self.tree_components}")'),
        ('        self.root_node = UnifiedTreeNode(self.tree_components)\n',
         '        self.agentkv_frontier.reset()\n        self.root_node = UnifiedTreeNode(self.tree_components)\n'),
        ('            result = self.insert(insert_params)\n\n            # Free unaligned tail',
         '            result = self.insert(insert_params)\n            self.agentkv_frontier.committed(req, radix_key, True)\n\n            # Free unaligned tail'),
        ('        result = self.insert(insert_params)\n\n        # Match prefix',
         '        result = self.insert(insert_params)\n        self.agentkv_frontier.committed(req, radix_key, False)\n\n        # Match prefix'),
    ]
    for old, new in edits:
        text = replace(text, old, new)
    return text


def patch_component(text):
    text = replace(text, '        return freed, host_freed\n',
                   '        self.cache.agentkv_frontier.freed(node, self.component_type, freed)\n        return freed, host_freed\n')
    anchor = '    def drive_eviction(\n        self, params: EvictParams, tracker: dict[ComponentType, int]\n    ) -> None:\n'
    return replace(text, anchor, anchor + '        if self.cache.agentkv_frontier.enabled:\n            return self.cache.agentkv_frontier.drive(self, params, tracker)\n')


def prepare(destination):
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Overlay must be inside experiment runtime')
    lock = json.loads((ROOT / 'configs/environment.lock.json').read_text())
    wheel = ROOT / lock['engine']['wheel']
    if digest(wheel) != lock['engine']['wheel_sha256']:
        raise ValueError('Official wheel SHA256 mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.filename.startswith('sglang/'):
                if '..' in Path(entry.filename).parts:
                    raise ValueError('Unsafe wheel path')
                archive.extract(entry, destination)
    changes = {}
    for relative, patcher in (
        ('srt/mem_cache/unified_radix_cache.py', patch_unified),
        ('srt/mem_cache/unified_cache_components/full_component.py', patch_component),
        ('srt/mem_cache/unified_cache_components/swa_component.py', patch_component),
    ):
        path = destination / 'sglang' / relative
        original = digest(path)
        if original != lock['engine']['source_hashes'][relative]:
            raise ValueError(f'Pristine source mismatch: {relative}')
        source = patcher(path.read_text())
        ast.parse(source)
        path.write_text(source)
        changes[relative] = {'pristine_sha256': original, 'patched_sha256': digest(path)}
    module = ROOT / 'scripts/bounded_frontier.py'
    ast.parse(module.read_text())
    shutil.copyfile(module, destination / 'sglang/srt/mem_cache/bounded_frontier.py')
    report = {'schema': 'agentkv.frontier_overlay.v1', 'overlay': str(destination.relative_to(ROOT)),
              'official_wheel_sha256': digest(wheel), 'frontier_sha256': digest(module),
              'files': changes, 'shared_full_swa_rule': True, 'prior_venv_unchanged': True,
              'native_reference_locks_unchanged': True, 'inactive_falls_through_to_official': True}
    (destination / 'frontier.lock.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output), indent=2))
