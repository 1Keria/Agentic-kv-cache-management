#!/usr/bin/env python3
"""Launch a completely original official package from the locked wheel."""

import argparse
import json
import os
from pathlib import Path
import sys

from prepare_pristine_overlay import ROOT, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--policy', choices=['lru', 'lfu', 'slru'], required=True)
    args = parser.parse_args()
    overlay = Path(os.environ['AGENTKV_PRISTINE_OVERLAY']).resolve()
    if not overlay.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Engine outside experiment runtime')
    lock = json.loads((overlay / 'engine.lock.json').read_text())
    for relative, expected in lock['files'].items():
        if digest(overlay / relative) != expected:
            raise ValueError('Original package changed: ' + relative)
    if any(os.environ.get(name) for name in ('AGENTKV_EXPOSURE_BARRIER', 'AGENTKV_MECHANISM_OVERLAY',
                                             'AGENTKV_FRONTIER_OVERLAY')):
        raise ValueError('Pristine baseline must not inherit any policy overlay')
    sys.path.insert(0, str(overlay))
    import sglang
    from server_command import build_command
    if not Path(sglang.__file__).resolve().is_relative_to(overlay):
        raise ValueError('Wrong SGLang origin')
    command = build_command(json.loads(args.config.read_text()), args.policy)
    print(json.dumps({'sglang_origin': sglang.__file__, 'source_unmodified': True,
                      'engine_lock_sha256': digest(overlay / 'engine.lock.json'), 'command': command}), flush=True)
    os.environ['PYTHONPATH'] = str(overlay)
    os.execv(sys.executable, command)


if __name__ == '__main__':
    main()
