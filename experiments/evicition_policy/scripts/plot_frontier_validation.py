#!/usr/bin/env python3
"""Export standalone figures for the audited frontier serving comparison."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = ('lru', 'split_only', 'bounded_frontier')
LABELS = ('Original LRU', 'Split only', 'Bounded frontier')
COLORS = ('#3067a1', '#949494', '#b96229')


def export(fig, output, name):
    for suffix in ('png', 'svg', 'pdf'):
        path = output / f'{name}.{suffix}'
        if path.exists():
            raise ValueError(f'Refusing to overwrite {path}')
        fig.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def plot(report, output):
    if not report['all_runs_complete_and_audited'] or not report['all_effective_signatures_equal']:
        raise ValueError('Only audited runs may be plotted')
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.5))
    specifications = (
        ('Cache hit rate (%)', lambda row: row['hit_rate'] * 100),
        ('Uncached input (million tokens)', lambda row: row['uncached_input_tokens'] / 1e6),
        ('Client TTFT p95 (s)', lambda row: row['ttft_seconds']['p95']),
        ('Replay duration (min)', lambda row: row['measurement_elapsed_seconds'] / 60),
    )
    for axis, (label, value) in zip(axes, specifications):
        for x, (strategy, color) in enumerate(zip(STRATEGIES, COLORS)):
            values = [value(row) for row in report['runs'] if row['strategy'] == strategy]
            if not values:
                continue
            mean = sum(values) / len(values)
            axis.bar(x, mean, width=.55, color=color, alpha=.7)
            for i, y in enumerate(values):
                offset = (i - (len(values) - 1) / 2) * .12
                axis.scatter(x + offset, y, color=color, edgecolor='white', s=35, zorder=3)
            axis.annotate(f'{mean:.2f}', (x, max(values)), xytext=(0, 5), textcoords='offset points',
                          ha='center', fontsize=9)
        axis.set_xticks(range(3), LABELS, rotation=18, ha='right')
        axis.set_ylabel(label)
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(axis='y', alpha=.15)
        axis.margins(y=.2)
    fig.suptitle(f'Agent-only: {report["requests_per_run"]:,} requests per run; identical physical pool capacities', fontsize=12)
    fig.text(.5, -.015, 'Bars are run means; dots are individual runs. Two serving repeats per main method; one structural ablation.',
             ha='center', fontsize=8)
    fig.tight_layout()
    export(fig, output, 'comparison')

    paired = report['protection_vs_lru_pairs']
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for i, row in enumerate(paired):
        positive = row['positive_cached_tokens_delta'] / 1e6
        negative = row['negative_cached_tokens_delta'] / 1e6
        axes[0].bar(i, positive, color='#40886b', label='More cached' if i == 0 else None)
        axes[0].bar(i, negative, color='#b85d62', label='Less cached' if i == 0 else None)
        axes[0].scatter(i, positive + negative, color='black', marker='D', s=40,
                        label='Net change' if i == 0 else None, zorder=3)
    axes[0].axhline(0, color='#555555', linewidth=.8)
    axes[0].set_xticks(range(len(paired)), [' -> '.join(row['order']).replace('bounded_frontier', 'Frontier').replace('lru', 'LRU') for row in paired])
    axes[0].set_ylabel('Cached-token change vs LRU (millions)')
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_title('Whole-run gains include all regressions')
    sessions = report['session_deltas']
    for i in range(len(paired)):
        values = [row['delta_pair' + str(i + 1)] / 1e6 for row in sessions]
        axes[1].plot(range(len(sessions)), values, 'o-', linewidth=1, markersize=3, label=f'Pair {i + 1}')
    axes[1].axhline(0, color='#555555', linewidth=.8)
    axes[1].set_xlabel('Session index (all 20 sessions)')
    axes[1].set_ylabel('Net cached-token change (millions)')
    axes[1].set_title('Distribution of benefit and loss')
    axes[1].legend(frameon=False, fontsize=8)
    for axis in axes:
        axis.grid(axis='y', alpha=.15)
        axis.spines[['top', 'right']].set_visible(False)
    fig.text(.5, -.02, 'Equal historical inputs, completion-dependent request interleaving; request deltas are not same-state causal substitutions.',
             ha='center', fontsize=8)
    fig.tight_layout()
    export(fig, output, 'gains_and_regressions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Keep figures inside the experiment')
    plot(json.loads(args.input.read_text()), args.output.resolve())
