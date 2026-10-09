#!/usr/bin/env python3
"""Audit total benefits, regressions, and structural ablation for frontier runs."""

import argparse
from collections import defaultdict
import csv
import json
import os
from pathlib import Path

from analyze_order_balanced import compare, mean_range, run_summary
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from run_frontier_validation import audit_frontier


def read(path):
    return json.loads(path.read_text())


def pair(before, after, records):
    result = {'baseline': before['run_id'], 'candidate': after['run_id'],
              'order': [row['strategy'] for row in sorted((before, after), key=lambda row: row['position'])],
              **compare(records[before['run_id']], records[after['run_id']])}
    for field in ('ttft_seconds', 'latency_seconds'):
        result[field + '_relative_change'] = {
            metric: after[field][metric] / before[field][metric] - 1
            for metric in ('mean', 'p50', 'p95', 'p99')}
    result['uncached_input_tokens_relative_change'] = after['uncached_input_tokens'] / before['uncached_input_tokens'] - 1
    result['measurement_duration_relative_change'] = after['measurement_elapsed_seconds'] / before['measurement_elapsed_seconds'] - 1
    return result


def analyze(source, destination):
    metadata = read(source / 'suite.json')
    if metadata['status'] != 'completed':
        raise ValueError('Only complete suites can produce comparison claims')
    destination.mkdir(parents=True, exist_ok=False)
    runs, records = [], {}
    for i, entry in enumerate(metadata['runs'], 1):
        run_id = entry['path']
        folder = source / run_id
        result, rows = run_summary(folder, run_id, None, i)
        result['strategy'] = entry['strategy']
        tp = result['integrity']['signature']['server']['tp_size']
        queues = result['scheduler_queue_by_rank']
        if (len(queues) != tp or not all(row['measurement_coverage_validated'] for row in queues)
            or {int(row['labels']['tp_rank']) for row in queues} != set(range(tp))):
            raise ValueError('Scheduler queue coverage is incomplete on one or more TP ranks')
        queue = [row for row in result['scheduler_queue_by_rank'] if row['labels'].get('tp_rank') == '0']
        if len(queue) != 1 or not queue[0]['measurement_coverage_validated']:
            raise ValueError('Measured scheduler queue coverage is incomplete')
        result['rank0_scheduler_queue_mean_seconds'] = queue[0]['mean_seconds']
        result['client_ttft_minus_scheduler_queue_mean_seconds'] = (
            result['ttft_seconds']['mean'] - queue[0]['mean_seconds'])
        native = {row['name']: row['raw_delta'] for row in result['raw_native_counter_deltas']}
        result['native_eviction_per_rank_mean'] = {
            'calls': native['sglang:eviction_duration_seconds_count'] / tp,
            'recorded_seconds': native['sglang:eviction_duration_seconds_sum'] / tp,
            'combined_full_swa_token_frees': native['sglang:evicted_tokens_total'] / tp,
            'normalization': 'Shared cache_type Prometheus series sums TP ranks; divide by TP, not by requests.',
            'note': 'Combined component tokens are not bytes; recorded rank durations are not additive serving wall time.'}
        fingerprints = read(folder / 'script_fingerprints.json')
        result['frontier_launcher_source_sha256'] = {
            name: fingerprints[name] for name in ('server_frontier.py', 'run_frontier_server.sh',
                                                  'server_pristine.py', 'run_pristine_server.sh',
                                                  'bounded_frontier.py', 'run_frontier_validation.py')}
        if result['strategy'] != 'lru':
            mode = read(folder / 'frontier_settings.json')
            expected_mode = dict(metadata['settings'], enabled=result['strategy'] == 'bounded_frontier',
                                 split_only=result['strategy'] == 'split_only')
            if mode != expected_mode:
                raise ValueError('Protection limits or structural mode drifted')
            result['frontier_integrity'] = audit_frontier(folder, mode)
            counters = result['frontier_integrity']['final_observed_counters']
            result['extra_boundary_splits'] = (counters.get('input_boundary_splits', 0)
                                               + counters.get('window_tail_splits', 0))
            if result['strategy'] == 'bounded_frontier':
                observed = counters.get('freed_full_tokens', 0) + counters.get('freed_swa_tokens', 0)
                expected = result['native_eviction_per_rank_mean']['combined_full_swa_token_frees']
                if observed != expected:
                    raise ValueError('Frontier physical frees and original engine counters disagree')
                result['frontier_frees_agree_with_native_tp_aggregate'] = True
            lock = read(folder / 'frontier_overlay.json')
            if lock['lock_sha256'] != metadata['overlay_lock_sha256']:
                raise ValueError('Frontier overlay differs across runs')
            if lock['settings_sha256'] != digest_file(folder / 'frontier_settings.json'):
                raise ValueError('Measured frontier settings changed')
        else:
            pristine = read(folder / 'pristine_engine.json')
            if not pristine['source_unmodified'] or pristine['lock_sha256'] != metadata['pristine_lock_sha256']:
                raise ValueError('LRU baseline is not the completely original locked engine')
        runs.append(result)
        records[run_id] = rows
    if (len(runs) != len(metadata['strategies'])
        or len({canonical_digest(row['integrity']['signature']) for row in runs}) != 1
        or len({canonical_digest(row['measurement_script_sha256']) for row in runs}) != 1
        or len({canonical_digest(row['frontier_launcher_source_sha256']) for row in runs}) != 1
        or len({canonical_digest(read(ROOT / row['path'] / 'config.resolved.json')) for row in runs}) != 1
        or len({read(ROOT / row['path'] / 'measurement/summary.json')['workload_sha256'] for row in runs}) != 1):
        raise ValueError('Configuration, backend, input, or measurement scripts drifted')
    if any(set(rows) != set(next(iter(records.values()))) for rows in records.values()):
        raise ValueError('Request sets differ')
    by_strategy = defaultdict(list)
    for row in runs:
        by_strategy[row['strategy']].append(row)
    if not by_strategy['lru'] or not by_strategy['bounded_frontier']:
        raise ValueError('Both original LRU and protection must complete')
    pairs = [pair(lru, frontier, records) for lru, frontier in
             zip(by_strategy['lru'], by_strategy['bounded_frontier'])]
    ablation = []
    for split in by_strategy['split_only']:
        ablation.extend(pair(lru, split, records) for lru in by_strategy['lru'])
        ablation.extend(pair(split, frontier, records) for frontier in by_strategy['bounded_frontier'])
    paired = []
    for key, original in next(iter(records.values())).items():
        row = {'session_id': key[0], 'task_id': original['task_id'], 'turn_index': key[1],
               'prompt_tokens': original['prompt_tokens'],
               'previous_input_lcp_tokens': original.get('previous_input_lcp_tokens')}
        for result in runs:
            observed = records[result['run_id']][key]
            row['cached_' + result['run_id']] = observed['cached_tokens']
            row['ttft_' + result['run_id']] = observed['ttft_seconds']
        for i, result in enumerate(pairs, 1):
            row['delta_pair' + str(i)] = row['cached_' + result['candidate']] - row['cached_' + result['baseline']]
        paired.append(row)
    fields = [name for name in paired[0] if name.startswith('delta_pair')]
    stable_positive = [row for row in paired if all(row[field] > 0 for field in fields)]
    stable_negative = [row for row in paired if all(row[field] < 0 for field in fields)]
    session_rows = []
    for session in sorted({row['session_id'] for row in paired}):
        selected = [row for row in paired if row['session_id'] == session]
        session_rows.append({'session_id': session, 'task_id': selected[0]['task_id'], 'requests': len(selected),
                             'prompt_tokens': sum(row['prompt_tokens'] for row in selected),
                             **{field: sum(row[field] for row in selected) for field in fields}})
    aggregate = {}
    for strategy, selected in by_strategy.items():
        aggregate[strategy] = {
            'hit_rate': mean_range([row['hit_rate'] for row in selected]),
            'uncached_input_tokens': mean_range([row['uncached_input_tokens'] for row in selected]),
            'measurement_elapsed_seconds': mean_range([row['measurement_elapsed_seconds'] for row in selected]),
            'rank0_scheduler_queue_mean_seconds': mean_range([row['rank0_scheduler_queue_mean_seconds'] for row in selected]),
            'client_ttft_minus_scheduler_queue_mean_seconds': mean_range([row['client_ttft_minus_scheduler_queue_mean_seconds'] for row in selected]),
            'native_eviction_per_rank_mean': {
                field: mean_range([row['native_eviction_per_rank_mean'][field] for row in selected])
                for field in ('calls', 'recorded_seconds', 'combined_full_swa_token_frees')},
            **{field: {metric: mean_range([row[field][metric] for row in selected])
                       for metric in ('mean', 'p50', 'p95', 'p99')}
               for field in ('ttft_seconds', 'latency_seconds')},
        }
    result = {'schema': 'agentkv.frontier_validation.v1', 'source': str(source.relative_to(ROOT)),
              'all_runs_complete_and_audited': True, 'all_effective_signatures_equal': True,
              'all_measurement_scripts_equal': True, 'requests_per_run': runs[0]['requests'],
              'total_requests': sum(row['requests'] for row in runs),
              'settings': metadata['settings'], 'overlay_lock_sha256': metadata['overlay_lock_sha256'],
              'pristine_lock_sha256': metadata['pristine_lock_sha256'],
              'runs': runs, 'aggregates': aggregate, 'protection_vs_lru_pairs': pairs,
              'structural_ablation_comparisons': ablation,
              'repeated_request_deltas': {
                  'comparison_pairs': len(pairs), 'positive_in_every_pair_requests': len(stable_positive),
                  'negative_in_every_pair_requests': len(stable_negative),
                  'sum_minimum_positive_delta_tokens': sum(min(row[field] for field in fields) for row in stable_positive),
                  'sum_minimum_negative_magnitude_tokens': sum(min(-row[field] for field in fields) for row in stable_negative),
                  'largest_positive_cases': sorted(stable_positive, key=lambda row: min(row[field] for field in fields), reverse=True)[:12],
                  'largest_negative_cases': sorted(stable_negative, key=lambda row: min(-row[field] for field in fields), reverse=True)[:12],
              },
              'session_deltas': session_rows,
              'limitations': metadata['limitations'] + [
                  'Uncached input includes necessary new content and recomputation, not solely eviction loss.',
                  'Client TTFT includes transport, scheduler queue, prefill, and first-token work.',
                  'Native per-response queue_time is untrusted; use per-rank scheduler histograms.',
                  'Pairing equal inputs measures whole-run differences; negative deltas are not a proven causal replacement loss.',
                  'Two serving repeats describe variation, not significance; structural ablation has one run.',
                  'Current protection anchors historical input boundaries, not the newly generated output tail.',
                  'Subtracting whole-population mean scheduler queue from client TTFT leaves a combined residual, not isolated GPU prefill.',
                  'Remaining DeepGEMM JIT messages are retained in measured serving times; message count is not compiler cost.',
              ], 'source_suite_sha256': digest_file(source / 'suite.json')}
    for filename, rows in (('paired_requests.csv', paired), ('session_deltas.csv', session_rows)):
        with (destination / filename).open('x') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    save_json(destination / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if not args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Keep output inside this experiment')
    result = analyze(args.suite.resolve(), args.output.resolve())
    print(json.dumps({'total_requests': result['total_requests'], 'pairs': result['protection_vs_lru_pairs']}, indent=2))
