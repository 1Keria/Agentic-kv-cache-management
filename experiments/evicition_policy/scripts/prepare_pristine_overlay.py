#!/usr/bin/env python3
"""Extract an untouched official package without changing the existing venv."""

import argparse
import json
from pathlib import Path
import zipfile

from prepare_mechanism_observer import ROOT, digest


def prepare(destination):
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Pristine engine must be inside experiment runtime')
    lock = json.loads((ROOT / 'configs/environment.lock.json').read_text())
    wheel = ROOT / lock['engine']['wheel']
    if digest(wheel) != lock['engine']['wheel_sha256']:
        raise ValueError('Official wheel mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.filename.startswith('sglang/'):
                if '..' in Path(entry.filename).parts:
                    raise ValueError('Unsafe wheel path')
                archive.extract(entry, destination)
                if not entry.is_dir():
                    files[entry.filename] = digest(destination / entry.filename)
    for relative, expected in lock['engine']['source_hashes'].items():
        if files['sglang/' + relative] != expected:
            raise ValueError('Pristine source mismatch: ' + relative)
    result = {'schema': 'agentkv.pristine_engine.v1', 'official_wheel_sha256': digest(wheel),
              'overlay': str(destination.relative_to(ROOT)), 'files': files,
              'source_unmodified': True, 'prior_venv_unchanged': True}
    (destination / 'engine.lock.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    report = prepare(parser.parse_args().output)
    print(json.dumps({name: value for name, value in report.items() if name != 'files'}))
