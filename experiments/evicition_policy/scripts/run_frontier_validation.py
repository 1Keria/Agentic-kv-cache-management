#!/usr/bin/env python3
"""Validate shared Full/SWA frontier protection on all frozen Agent sessions."""

import argparse
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import uuid

from analyze_results import audit_run
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from replay_agent import validate_workload
from run_suite import run_once


def read(path):
    return json.loads(path.read_text())


def audit_frontier(run, settings):
    files = list((run / 'frontier_events').glob('*.jsonl'))
    if len(files) != 1:
        raise ValueError('Expected exactly one TP rank-zero frontier event stream')
    rows = [json.loads(line) for line in files[0].read_text().splitlines()]
    if [row['event_seq'] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('Frontier event sequence is incomplete')
    flush = [i for i, row in enumerate(rows) if row['event_type'] == 'flush']
    if not flush:
        raise ValueError('No frontier flush boundary')
    # run_once flushes once immediately before the measured replay and does
    # not flush after it. Exclude protocol and both shape-warmup passes.
    measured = rows[flush[-1] + 1:]
    if not measured:
        raise ValueError('No measured frontier activity')
    if any(row['units'] > settings['max_units']
           or row['full_dependency_tokens'] > settings['full_budget_tokens']
           or row['swa_dependency_tokens'] > settings['swa_budget_tokens'] for row in measured):
        raise ValueError('Frontier budget violated')
    return {'event_file': str(files[0].relative_to(run)), 'sha256': digest_file(files[0]),
            'sequence_continuous': True, 'budget_respected': True,
            'measurement_events': len(measured),
            'max_units': max(row['units'] for row in measured),
            'max_full_dependency_tokens': max(row['full_dependency_tokens'] for row in measured),
            'max_swa_dependency_tokens': max(row['swa_dependency_tokens'] for row in measured),
            'final_observed_counters': measured[-1]['counters'],
            'note': 'Counters are the final emitted checkpoint, not a shutdown snapshot.'}


async def execute(args, output):
    source = args.source_batch.resolve()
    prior = read(source / 'batch.json')
    if prior['status'] != 'completed':
        raise ValueError('Source batch incomplete')
    paths = {name: ROOT / prior[name] for name in ('config', 'workload', 'warmup', 'shape_warmup')}
    for name, path in paths.items():
        if digest_file(path) != prior['input_sha256'][name]:
            raise ValueError(f'Frozen {name} changed')
    config, workload, warmup, shapes = (read(paths[name]) for name in ('config', 'workload', 'warmup', 'shape_warmup'))
    validate_workload(workload)
    if workload['requests'] != 1206 or len(workload['sessions']) != 20:
        raise ValueError('Unexpected workload extent')
    if not Path(config['model_path']).is_dir():
        raise ValueError('Locked model unavailable')
    overlay = args.overlay.resolve()
    pristine = args.pristine_overlay.resolve()
    pristine_lock = read(pristine / 'engine.lock.json')
    overlay_lock = read(overlay / 'frontier.lock.json')
    if (not pristine_lock['source_unmodified'] or
        pristine_lock['official_wheel_sha256'] != overlay_lock['official_wheel_sha256']):
        raise ValueError('Pristine engine and frontier must use the same official wheel')
    if overlay_lock['frontier_sha256'] != digest_file(ROOT / 'scripts/bounded_frontier.py'):
        raise ValueError('Frontier overlay differs from the current tested source')
    settings = read(args.settings)
    if not settings.get('enabled') or settings.get('split_only'):
        raise ValueError('Supply the frozen protection configuration')
    expected = read(source / '01_lru_slru/01_lru/effective_signature.json')
    state = {'status': 'running', 'purpose': 'bounded_frontier_full_session_validation',
             'strategies': args.strategies, 'source_batch': str(source.relative_to(ROOT)),
             'input_sha256': prior['input_sha256'], 'settings': settings,
             'settings_sha256': digest_file(args.settings),
             'overlay': str(overlay.relative_to(ROOT)),
             'overlay_lock_sha256': digest_file(overlay / 'frontier.lock.json'),
             'pristine_overlay': str(pristine.relative_to(ROOT)),
             'pristine_lock_sha256': digest_file(pristine / 'engine.lock.json'),
             'shared_full_swa_rule': True, 'runs': [],
             'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'limitations': ['Fixed historical inputs, completion-dependent scaled waits; not real tool execution.',
                             'Original LRU is the unmodified official engine, not the frontier-disabled overlay.',
                             'Paired request deltas include changed interleaving and are not same-state counterfactuals.']}
    save_json(output / 'suite.json', state)
    try:
        for i, strategy in enumerate(args.strategies, 1):
            if digest_file(overlay / 'frontier.lock.json') != state['overlay_lock_sha256']:
                raise ValueError('Overlay lock changed during the experiment')
            folder = output / f'{i:02d}_{strategy}'
            mode = None if strategy == 'lru' else dict(settings, enabled=strategy == 'bounded_frontier',
                                                       split_only=strategy == 'split_only')
            print(json.dumps({'starting': str(folder), 'strategy': strategy}), flush=True)
            await run_once(config, paths['config'], workload, warmup, 'lru', folder, expected,
                           args.ready_timeout, shapes, strategy=strategy,
                           frontier_overlay=overlay if mode is not None else None,
                           frontier_settings=mode,
                           pristine_overlay=pristine if strategy == 'lru' else None)
            audit = audit_run(folder)
            save_json(folder / 'integrity.json', audit)
            if not all(audit[key] for key in ('protocol_integrity_passed', 'cached_tokens_all_known',
                                              'post_flush_native_metrics_empty', 'cleanup_confirmed')):
                raise ValueError(f'Run integrity failed: {audit["integrity_errors"]}')
            frontier = audit_frontier(folder, mode) if mode is not None else None
            if frontier:
                save_json(folder / 'frontier_integrity.json', frontier)
            state['runs'].append({'strategy': strategy, 'path': folder.name,
                                  'audit': audit, 'frontier_audit': frontier,
                                  'measurement_seconds': read(folder / 'measurement/summary.json')['elapsed_seconds']})
            save_json(output / 'suite.json', state)
            print(json.dumps({'completed': folder.name,
                              'hit_fraction': audit['token_weighted_cache_hit_fraction'],
                              'ttft_p95': audit['ttft_seconds']['p95']}), flush=True)
        state['status'] = 'completed'
    except BaseException as error:
        state.update(status='failed', error=repr(error))
        raise
    finally:
        state['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(output / 'suite.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-batch', type=Path, default=ROOT / 'results/order_balanced/20261008T035423Z_1593ea96')
    parser.add_argument('--overlay', type=Path, default=ROOT / 'runtime/frontier_overlay_20261008_v1')
    parser.add_argument('--pristine-overlay', type=Path, default=ROOT / 'runtime/frontier_pristine_20261008_v1')
    parser.add_argument('--settings', type=Path, default=ROOT / 'configs/bounded_frontier_v1.json')
    parser.add_argument('--strategies', nargs='+', choices=['lru', 'bounded_frontier', 'split_only'],
                        default=['bounded_frontier', 'lru', 'split_only', 'lru', 'bounded_frontier'])
    parser.add_argument('--ready-timeout', type=float, default=3600)
    args = parser.parse_args()
    os.umask(0o077)
    destination = ROOT / 'results/frontier' / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                                              + '_' + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True, exist_ok=False)
    print(json.dumps({'suite': str(destination)}), flush=True)
    with (ROOT / 'runtime/suite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(execute(args, destination))


if __name__ == '__main__':
    main()
