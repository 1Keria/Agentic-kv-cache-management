#!/usr/bin/env python3
"""Print compact local progress without exposing request tokens or outputs."""

import argparse
import json
from pathlib import Path


def tail_record(path):
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            pass
    return {}


def inspect(folder):
    result = []
    for path in sorted(folder.glob('*/state.json')):
        state = json.loads(path.read_text())
        row = {'run': path.parent.name, 'status': state['status']}
        requests = path.parent / 'measurement/requests.jsonl'
        if requests.exists():
            count, failed = 0, 0
            for line in requests.open():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                count += record['status'] == 'completed'
                failed += record['status'] != 'completed'
            row.update(completed_requests=count, failed_requests=failed)
        for events in (path.parent / 'frontier_events').glob('*.jsonl'):
            record = tail_record(events)
            row['frontier_counters'] = record.get('counters', {})
            row['protected_units'] = record.get('units')
        if 'error' in state:
            row['error'] = state['error']
        result.append(row)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', type=Path)
    print(json.dumps(inspect(parser.parse_args().suite), ensure_ascii=False))
