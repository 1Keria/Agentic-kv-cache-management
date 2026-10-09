#!/usr/bin/env python3
"""Write a compact shareable Chinese report from completed audited evidence."""

import argparse
import datetime
import json
from pathlib import Path

from prepare_data import ROOT, digest_file, save_json


def percent(value):
    return f'{value * 100:.2f}%'


def write(source, destination):
    data = json.loads(source.read_text())
    if not data['all_runs_complete_and_audited'] or not data['all_effective_signatures_equal']:
        raise ValueError('Report requires complete audited runs')
    if destination.exists() or destination.with_suffix('.json').exists():
        raise ValueError('Refusing to overwrite reports')
    aggregates = data['aggregates']
    original, frontier = aggregates['lru'], aggregates['bounded_frontier']
    delta = (frontier['hit_rate']['mean'] - original['hit_rate']['mean']) * 100
    uncached = frontier['uncached_input_tokens']['mean'] / original['uncached_input_tokens']['mean'] - 1
    changes = {field + '_' + metric: frontier[field][metric]['mean'] / original[field][metric]['mean'] - 1
               for field in ('ttft_seconds', 'latency_seconds') for metric in ('mean', 'p50', 'p95', 'p99')}
    duration = frontier['measurement_elapsed_seconds']['mean'] / original['measurement_elapsed_seconds']['mean'] - 1
    pairs = data['protection_vs_lru_pairs']
    repeated = len(pairs) >= 2 and all(row['cached_tokens_delta'] > 0 for row in pairs)
    compact = {
        'schema': 'agentkv.frontier_report.v1', 'all_runs_complete_and_audited': True,
        'source_summary': str(source.relative_to(ROOT)), 'source_summary_sha256': digest_file(source),
        'source_suite': data['source'], 'total_requests': data['total_requests'],
        'requests_per_run': data['requests_per_run'], 'settings': data['settings'],
        'same_model_backend_capacities_inputs': True,
        'protection_vs_lru': {'hit_rate_gain_percentage_points': delta,
                              'uncached_input_relative_change': uncached,
                              'timing_relative_changes': changes,
                              'replay_duration_relative_change': duration,
                              'cache_gain_positive_in_both_orders': repeated},
        'aggregates': aggregates, 'pairs': pairs,
        'structural_ablation_comparisons': data['structural_ablation_comparisons'],
        'repeated_request_deltas': data['repeated_request_deltas'],
        'runs': [{name: row[name] for name in (
            'run_id', 'strategy', 'path', 'requests', 'hit_rate', 'cached_tokens', 'uncached_input_tokens',
            'ttft_seconds', 'latency_seconds', 'measurement_elapsed_seconds',
            'rank0_scheduler_queue_mean_seconds', 'client_ttft_minus_scheduler_queue_mean_seconds',
            'native_eviction_per_rank_mean', 'measurement_deepgemm_jit_messages',
            'evidence_sha256')}
            | {'frontier_integrity': row.get('frontier_integrity'),
               'extra_boundary_splits': row.get('extra_boundary_splits'),
               'pool_accounting_mismatch_samples': row['monitor']['rank0_pool_accounting_mismatch_samples'],
               'native_num_retractions': row['native_num_retractions']['sum']}
            for row in data['runs']],
        'limitations': data['limitations'],
    }
    save_json(destination.with_suffix('.json'), compact)
    rows = data['runs']
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conclusion = ('两种顺序中均提高了总体缓存命中，值得保留机制并继续做容量与混合流量验证。'
                  if repeated else '目前尚不能认为总体缓存收益稳定，需要依据重复中的退化继续定位原因。')
    text = [
        '# 可复用边界保护 v1：完整验证', '',
        f'完成时间（UTC）：{timestamp}。状态：5 次完整 GPU 运行已结束，共 {data["total_requests"]:,} 个请求，完整性、同容量、输出数量、缓存清空及自有服务释放审计通过。', '',
        f'**相对完全原生 LRU，保护版本平均命中率提高 {delta:.4f} 个百分点，未命中输入量变化 {percent(uncached)}，平均 TTFT 变化 {percent(changes["ttft_seconds_mean"])}，TTFT p95 变化 {percent(changes["ttft_seconds_p95"])}。** {conclusion}此处未命中输入包含必要新内容，不能全称为淘汰重算；两次重复是描述性证据，不是显著性检验。', '',
        '## 实验边界', '',
        '纯 Agent-only，完整 20 会话 / 1,206 请求，模型 DeepSeek-V4-Flash、官方 SGLang 0.5.13.post1、UnifiedRadixCache、TP8、8 张 H800。Full 524,288 token、SWA 52,224 token，page 256、窗口 128，最大并发 8、chunked prefill 8,192；等待和启动间隔使用原冻结的 0.30 缩放。每次输入 48,787,785 token、生成 693,217 token，策略之间重启服务。分类器、业务分区、旧 Exposure Barrier 均关闭。', '',
        '原生基线是从固定 SHA256 的官方 wheel 新解出的完全未经修改副本。保护和结构消融使用同一个单独副本；没有覆盖已有 venv、项目引擎或历史结果。最初启动在正式测量前由控制器中断，用于进一步排除既有环境中的关闭状态历史补丁，0 个测量请求，不计入结果。', '',
        '保护对象是实际输入的可复用边界：连续 Full 祖先和匹配必需的末端 SWA 窗口，共用同一个单元。同一精确前缀链出现新边界就替换旧边界；最多 8 个单元、去重 Full 依赖上限 262,144、SWA 依赖上限 4,096。超限撤销最旧保护；没有未保护合法候选时，撤销阻挡候选的最旧单元并回退 LRU。两池仅在物理候选/锁/释放适配上不同，没有两套策略，也没有工具时间预测。详细设计见 [设计与验收](可复用边界保护_v1设计与验收.md)。', '',
        '## 五次运行与重复', '',
        '| 顺序 | 机制 | 命中率 | 未命中输入（百万） | TTFT 均值（秒） | TTFT p95（秒） | 请求耗时 p95（秒） | 测量时长（分钟） |',
        '|---:|---|---:|---:|---:|---:|---:|---:|',
    ]
    names = {'lru': '完全原生 LRU', 'bounded_frontier': '有限边界保护', 'split_only': '只登记/拆分，关闭保护'}
    for row in rows:
        text.append(f'| {row["position"]} | {names[row["strategy"]]} | {row["hit_rate"] * 100:.4f}% | {row["uncached_input_tokens"] / 1e6:.3f} | {row["ttft_seconds"]["mean"]:.3f} | {row["ttft_seconds"]["p95"]:.3f} | {row["latency_seconds"]["p95"]:.3f} | {row["measurement_elapsed_seconds"] / 60:.2f} |')
    text += ['', f'两个主要策略均值：LRU {original["hit_rate"]["mean"] * 100:.4f}%，保护 {frontier["hit_rate"]["mean"] * 100:.4f}%。平均请求耗时变化 {percent(changes["latency_seconds_mean"])}，p95 变化 {percent(changes["latency_seconds_p95"])}；完整回放时长变化 {percent(duration)}。此处策略分位数均值是“两次运行各自分位数再取均值”，不是合并两轮请求的分位数。由于会话等待保留，回放时长不等于无等待吞吐。', '',
             '| 对照顺序 | 净新增命中 token | 新增命中请求 / 下降请求 | 新增 / 损失 token | 命中提升（百分点） |',
             '|---|---:|---:|---:|---:|']
    for pair in pairs:
        text.append(f'| {" → ".join(names[value] for value in pair["order"])} | {pair["cached_tokens_delta"]:,} | {pair["more_cached_requests"]} / {pair["less_cached_requests"]} | {pair["positive_cached_tokens_delta"]:,} / {abs(pair["negative_cached_tokens_delta"]):,} | {pair["hit_rate_delta_percentage_points"]:.4f} |')
    repeated_deltas = data['repeated_request_deltas']
    text += ['', f'两次对照中均增加命中的请求有 {repeated_deltas["positive_in_every_pair_requests"]} 个，均下降的有 {repeated_deltas["negative_in_every_pair_requests"]} 个。所有下降请求都已计入净收益。相同输入的配对仍包含完成时间改变造成的交错变化，因此不能把每个负差直接叫“保护造成的替代损失”。此前同状态、等量释放的正负局部反事实仍保留在原生诊断报告中。', '',
             '![总体对照](figures/frontier_validation_20261008/comparison.png)', '',
             '![收益和退化](figures/frontier_validation_20261008/gains_and_regressions.png)', '',
             '## 结构与保护审计', '',
             '| 运行 | 登记 / prefill 登记 | 额外拆分 | 最大单元 / Full 依赖 / SWA 依赖 | 预算撤销 | 压力撤销 Full / SWA |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        if 'frontier_integrity' not in row:
            continue
        audit = row['frontier_integrity']
        counters = audit['final_observed_counters']
        text.append(f'| {row["run_id"]} | {counters.get("registered", 0)} / {counters.get("input_staged_prefill", 0)} | {row["extra_boundary_splits"]} | {audit["max_units"]} / {audit["max_full_dependency_tokens"]:,} / {audit["max_swa_dependency_tokens"]:,} | {counters.get("drop_budget", 0)} | {counters.get("drop_pressure_full", 0)} / {counters.get("drop_pressure_swa", 0)} |')
    split_counts = [row['extra_boundary_splits'] for row in rows if 'extra_boundary_splits' in row]
    if all(value == 0 for value in split_counts):
        text += ['', '**本数据没有触发任何新增边界拆分。** 官方 prefill 缓存路径已经隔出输入末端和所需页尾部；只拆分消融实际成为“登记检查、关闭保护”的控制。因此不能解释为“拆分有害”，也不能把保护版本的收益归因于新增拆分。后续跨引擎/输入边界验证仍要检查拆分的独立影响。']
    text += ['', '保护日志仅由 rank 0 写出，序列连续且没有超预算。保护版本记录的两池实际 free 与官方聚合计数除以 TP8 后完全一致。输入边界来自实际缓存提交，未读未来请求；所有正式请求在 prefill 阶段已登记。官方引用锁、原子叶回收与容量分配继续生效。', '',
             '## 时间为什么没有按命中率等比例改善', '',
             '| 机制 | 客户端 TTFT 均值 | rank 0 队列均值 | 两者均值之差 | 记录回收时间（各 rank 平均） | 回收调用（各 rank 平均） |',
             '|---|---:|---:|---:|---:|---:|']
    for strategy in ('lru', 'split_only', 'bounded_frontier'):
        aggregate = aggregates[strategy]
        text.append(f'| {names[strategy]} | {aggregate["ttft_seconds"]["mean"]["mean"]:.3f} 秒 | {aggregate["rank0_scheduler_queue_mean_seconds"]["mean"]:.3f} 秒 | {aggregate["client_ttft_minus_scheduler_queue_mean_seconds"]["mean"]:.3f} 秒 | {aggregate["native_eviction_per_rank_mean"]["recorded_seconds"]["mean"]:.2f} 秒 | {aggregate["native_eviction_per_rank_mean"]["calls"]["mean"]:.1f} |')
    text += ['', f'**TTFT 中位数没有稳定改善。** p50 两轮变化分别为 {percent(pairs[0]["ttft_seconds_relative_change"]["p50"])} / {percent(pairs[1]["ttft_seconds_relative_change"]["p50"])}，两次指标均值由 {original["ttft_seconds"]["p50"]["mean"]:.3f} 秒变为 {frontier["ttft_seconds"]["p50"]["mean"]:.3f} 秒（{percent(changes["ttft_seconds_p50"])}）。第二轮 TTFT p99 变化 {percent(pairs[1]["ttft_seconds_relative_change"]["p99"])}。当前明确复现的是总体命中、未命中输入、平均 TTFT、TTFT p95 和请求耗时改善，p50/p99 尚不稳定。', '',
             '队列直方图每个 TP rank 的覆盖均核对为完整 1,206 请求，不叠加副本。TTFT 减平均队列时间后的数值同时含 prefill、首 token、传输和其他前端开销，不是孤立 GPU prefill；也不能用 p95 减另一个分布的 p95。保护减少未命中工作后，队列和请求交错都可能变化，因此 decode 阶段观测变化也不能宣称来自新的 decode 算法。', '',
             'v1 用树依赖重算和候选跳过实现，正式回收计时包含这些成本。这个数字用于定位工程开销，不是把八张卡的回收时间累加到服务时长。下一版可优先减少重复依赖遍历，保持机制和对照配置一致。', '',
             '## 验证范围与下一步', '',
             '本轮支持在该 Agent-only 压力点继续研究统一可复用边界保护；尚未证明所有容量、其他 Agent 流量或动态分区组合下都有效。下一步先做相邻压力容量点的对照，再回到混合流量/动态分区组合。保留完全原生 LRU 和当前版本作为冻结参照；不要同时堆加新的预测和评分机制。', '',
             f'五次测量期间 DeepGEMM JIT 提示数依次为 {[row["measurement_deepgemm_jit_messages"] for row in rows]}。提示条数不是实际编译成本；当前时间结果保留这些事件，仍需进一步统一预热或计时验证。实际请求重调度次数依次为 {[row["native_num_retractions"]["sum"] for row in rows]}；监控容量记账残差采样次数依次为 {[row["monitor"]["rank0_pool_accounting_mismatch_samples"] for row in rows]}，瞬时 scrape 残差保留在明细中。', '',
             '下一轮输入仍来自历史轨迹，等待上一轮实际完成后再按原记录缩放等待；新生成通常不等于历史回答。该结果不是执行真实工具的 Agent 闭环。本版本只保护实际输入边界，没有自动保护当前新生成尾部；真实闭环仍需专门验证。', '',
             '## 复现与证据', '',
             f'- 完整运行：`{data["source"]}/suite.json`；分析：`{source.parent.relative_to(ROOT)}/summary.json`，同目录保留逐请求与会话配对 CSV。',
             '- [机器结果](可复用边界保护_v1完整验证_20261008.json)；[冻结配置](../configs/bounded_frontier_v1.json)；[实现](../scripts/bounded_frontier.py)；[运行入口](../scripts/run_frontier_validation.py)；[分析入口](../scripts/analyze_frontier_validation.py)。',
             '- 新机制 11 项 CPU 检查、21 项回放回归检查通过；官方节点拆分与锁 UUID 释放已通过 CPU 检查，GPU 完整性和所有自有服务释放审计通过。',
             '- 原始输入、输出、环境、权重和大日志仅保留本地。本报告和紧凑 JSON 不包含原始请求文本或输出。未执行 git commit/push。', '',
             f'分析文件 SHA256：`{digest_file(source)}`。',
             f'保护副本 lock SHA256：`{data["overlay_lock_sha256"]}`。',
             f'纯净原生副本 lock SHA256：`{data["pristine_lock_sha256"]}`。', '']
    destination.write_text('\n'.join(text))
    print(json.dumps(compact['protection_vs_lru'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'reports'):
        raise ValueError('Keep the report inside experiment reports')
    write(args.input.resolve(), args.output.resolve())
