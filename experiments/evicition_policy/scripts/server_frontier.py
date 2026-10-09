#!/usr/bin/env python3
"""Verify and launch the isolated bounded-frontier experiment engine."""

import argparse
import json
import os
from pathlib import Path
import sys

from prepare_frontier_overlay import ROOT, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--policy', choices=['lru'], required=True)
    args = parser.parse_args()
    if os.environ.get('AGENTKV_EXPOSURE_BARRIER') or os.environ.get('AGENTKV_MECHANISM_OVERLAY'):
        raise ValueError('Frontier experiment must not combine other overlays')
    overlay = Path(os.environ['AGENTKV_FRONTIER_OVERLAY']).resolve()
    if not overlay.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Overlay outside experiment runtime')
    lock = json.loads((overlay / 'frontier.lock.json').read_text())
    for relative, expected in lock['files'].items():
        if digest(overlay / 'sglang' / relative) != expected['patched_sha256']:
            raise ValueError(f'Installed source changed: {relative}')
    if digest(overlay / 'sglang/srt/mem_cache/bounded_frontier.py') != lock['frontier_sha256']:
        raise ValueError('Installed frontier module changed')
    settings = json.loads(Path(os.environ['AGENTKV_FRONTIER_SETTINGS']).read_text())
    if bool(settings.get('enabled')) == bool(settings.get('split_only')):
        raise ValueError('Choose one active frontier mode')
    sys.path.insert(0, str(overlay))
    import sglang
    from server_command import build_command
    if not Path(sglang.__file__).resolve().is_relative_to(overlay):
        raise ValueError('Wrong SGLang import origin')
    config = json.loads(args.config.read_text())
    command = build_command(config, args.policy)
    print(json.dumps({'sglang_origin': sglang.__file__, 'frontier_settings': settings,
                      'overlay_lock_sha256': digest(overlay / 'frontier.lock.json'),
                      'command': command}), flush=True)
    os.environ['PYTHONPATH'] = str(overlay)
    os.execv(sys.executable, command)


if __name__ == '__main__':
    main()
