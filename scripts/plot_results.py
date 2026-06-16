# vLLM KV Cache 实验可视化脚本
#
# 用法: python scripts/plot_results.py [实验名或all]
#   python scripts/plot_results.py exp1_prefix_hit
#   python scripts/plot_results.py exp3_offload_compare
#   python scripts/plot_results.py all
#
# 产出: experiments/vllm_kv_cache/figures/ 目录下的 PNG 图片

import json
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# 中文字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

EXPERIMENT_DIR = "/share/dai-sys/zhoulongsheng/agentkv/experiments/vllm_kv_cache"
FIGURE_DIR = os.path.join(EXPERIMENT_DIR, "figures")


def load_runs(exp_name):
    """加载某实验的所有 run 数据"""
    exp_dir = os.path.join(EXPERIMENT_DIR, exp_name)
    if not os.path.isdir(exp_dir):
        print(f"  No data found: {exp_dir}")
        return []
    runs = []
    for fname in sorted(os.listdir(exp_dir)):
        if fname.startswith("run_") and fname.endswith(".json"):
            with open(os.path.join(exp_dir, fname)) as f:
                runs.append(json.load(f))
    return runs


def save_fig(fig, name):
    """保存图片"""
    os.makedirs(FIGURE_DIR, exist_ok=True)
    path = os.path.join(FIGURE_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# 实验 1: Prefix Cache 命中 — TTFT 对比柱状图
# ---------------------------------------------------------------------------

def plot_exp1():
    print("\n[Exp1] Prefix Cache Hit — TTFT Comparison")
    runs = load_runs("exp1_prefix_hit")
    if not runs:
        return

    # 取所有 run 的平均
    cold_ttft = []
    warm_ttft = []
    cold_cached = []
    warm_cached = []
    for run in runs:
        for req in run.get("requests", []):
            if "cold" in req["label"]:
                cold_ttft.append(req.get("ttft_ms", 0))
                cold_cached.append(req.get("cached_tokens", 0))
            elif "warm" in req["label"]:
                warm_ttft.append(req.get("ttft_ms", 0))
                warm_cached.append(req.get("cached_tokens", 0))

    if not cold_ttft or not warm_ttft:
        print("  No cold/warm data found")
        return

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    # 左图: TTFT 对比
    labels = ["Cold\n(no cache)", "Warm\n(prefix hit)"]
    means = [np.mean(cold_ttft), np.mean(warm_ttft)]
    stds = [np.std(cold_ttft), np.std(warm_ttft)]
    colors = ["#e74c3c", "#2ecc71"]
    bars = axes[0].bar(labels, means, yerr=stds, color=colors, capsize=5, width=0.5)
    axes[0].set_ylabel("TTFT (ms)")
    axes[0].set_title("Time to First Token")
    for bar, val in zip(bars, means):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                     f"{val:.0f}ms", ha='center', va='bottom', fontsize=11, fontweight='bold')
    # 标注加速比
    if means[0] > 0:
        speedup = means[0] / means[1] if means[1] > 0 else float('inf')
        axes[0].text(0.5, 0.85, f"{speedup:.1f}x faster", transform=axes[0].transAxes,
                     ha='center', fontsize=12, color='#27ae60', fontweight='bold')

    # 右图: cached_tokens
    labels2 = ["Cold", "Warm"]
    cached_means = [np.mean(cold_cached), np.mean(warm_cached)]
    colors2 = ["#95a5a6", "#3498db"]
    bars2 = axes[1].bar(labels2, cached_means, color=colors2, width=0.5)
    axes[1].set_ylabel("Cached Tokens")
    axes[1].set_title("Prefix Cache Hit Tokens")
    for bar, val in zip(bars2, cached_means):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                     f"{val:.0f}", ha='center', va='bottom', fontsize=11, fontweight='bold')

    fig.suptitle("Experiment 1: Prefix Cache Basic Hit Verification", fontsize=13, fontweight='bold')
    fig.tight_layout()
    save_fig(fig, "exp1_prefix_hit_ttft.png")


# ---------------------------------------------------------------------------
# 实验 2: Block 粒度浪费 — 浪费量 vs prefix 长度
# ---------------------------------------------------------------------------

def plot_exp2():
    print("\n[Exp2] Block Granularity Waste")
    runs = load_runs("exp2_block_granularity")
    if not runs:
        return

    # 提取每组 prefix_tokens 和实际浪费
    prefix_lens = []
    actual_waste = []
    expected_waste = []
    for run in runs:
        for result in run.get("results", []):
            pt = result.get("prefix_tokens", 0)
            ct = result.get("cached_tokens", 0)
            ew = result.get("expected_waste", pt % 16)
            prefix_lens.append(pt)
            actual_waste.append(pt - ct)
            expected_waste.append(ew)

    if not prefix_lens:
        print("  No block granularity data found")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(prefix_lens))
    width = 0.35
    bars1 = ax.bar(x - width/2, actual_waste, width, label='Actual waste', color='#e74c3c', alpha=0.8)
    bars2 = ax.bar(x + width/2, expected_waste, width, label='Expected waste (mod 16)', color='#3498db', alpha=0.8)

    ax.set_xlabel("Prefix Length (tokens)")
    ax.set_ylabel("Wasted Tokens")
    ax.set_title("Experiment 2: Block-Level Granularity Waste (block_size=16)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(p) for p in prefix_lens])
    ax.legend()
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    # 在柱子上标注数值
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.2, f"{int(h)}",
                    ha='center', va='bottom', fontsize=9)

    fig.tight_layout()
    save_fig(fig, "exp2_block_waste.png")


# ---------------------------------------------------------------------------
# 实验 3: Offloading 对比 — 命中恢复对比
# ---------------------------------------------------------------------------

def plot_exp3():
    print("\n[Exp3] KV Offloading Effect Comparison")
    # 加载有/无 offloading 两组数据
    runs_on = load_runs("exp3_offload_on")
    runs_off = load_runs("exp3_offload_off")
    if not runs_on and not runs_off:
        return

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    # 左图: req_C 的 cached_tokens 对比
    labels = ["No Offload", "With Offload\n(8 GiB)"]
    cached_on = []
    cached_off = []
    ttft_on = []
    ttft_off = []

    for run in runs_off:
        for req in run.get("requests", []):
            if "req_C" in req.get("label", "") or "recovery" in req.get("label", ""):
                cached_off.append(req.get("cached_tokens", 0))
                ttft_off.append(req.get("ttft_ms", 0))

    for run in runs_on:
        for req in run.get("requests", []):
            if "req_C" in req.get("label", "") or "recovery" in req.get("label", ""):
                cached_on.append(req.get("cached_tokens", 0))
                ttft_on.append(req.get("ttft_ms", 0))

    if cached_on or cached_off:
        cached_means = [
            np.mean(cached_off) if cached_off else 0,
            np.mean(cached_on) if cached_on else 0,
        ]
        cached_stds = [
            np.std(cached_off) if cached_off else 0,
            np.std(cached_on) if cached_on else 0,
        ]
        colors = ["#e74c3c", "#2ecc71"]
        bars = axes[0].bar(labels, cached_means, yerr=cached_stds, color=colors, capsize=5, width=0.5)
        axes[0].set_ylabel("Cached Tokens on Recovery Request")
        axes[0].set_title("Prefix Recovery After Eviction")
        for bar, val in zip(bars, cached_means):
            axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                         f"{val:.0f}", ha='center', va='bottom', fontsize=11, fontweight='bold')

    # 右图: TTFT 对比
    if ttft_on or ttft_off:
        ttft_means = [
            np.mean(ttft_off) if ttft_off else 0,
            np.mean(ttft_on) if ttft_on else 0,
        ]
        ttft_stds = [
            np.std(ttft_off) if ttft_off else 0,
            np.std(ttft_on) if ttft_on else 0,
        ]
        bars2 = axes[1].bar(labels, ttft_means, yerr=ttft_stds, color=colors, capsize=5, width=0.5)
        axes[1].set_ylabel("TTFT (ms)")
        axes[1].set_title("Recovery Request Latency")
        for bar, val in zip(bars2, ttft_means):
            axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                         f"{val:.0f}ms", ha='center', va='bottom', fontsize=11, fontweight='bold')

    fig.suptitle("Experiment 3: KV Offloading Effect on Prefix Recovery", fontsize=13, fontweight='bold')
    fig.tight_layout()
    save_fig(fig, "exp3_offload_compare.png")


# ---------------------------------------------------------------------------
# 实验 4: Agent 多 Session — 按子场景分组可视化
# ---------------------------------------------------------------------------

def plot_exp4():
    print("\n[Exp4] Agent Multi-Session KV Reuse")
    runs = load_runs("exp4_agent_session")
    if not runs:
        return

    # 按子场景分组
    subexps = {}
    for run in runs:
        key = run.get("subexp", "4.1")  # 向后兼容
        subexps.setdefault(key, []).append(run)

    # 为每个子场景生成图
    if any(k in subexps for k in ("4.1", "4.2", "4.3")):
        _plot_exp4_l0_l1_l2(subexps)
    if "4.4" in subexps:
        _plot_exp4_concurrent(subexps["4.4"])
    if any(k.startswith("4.5") for k in subexps):
        _plot_exp4_eviction_protection(subexps)
    if any(k.startswith("4.6") for k in subexps):
        _plot_exp4_recovery_speed(subexps)


def _plot_exp4_l0_l1_l2(subexps):
    """4.1~4.3: L0/L1/L2 命中率堆叠图"""
    print("  [4.1-4.3] L0/L1/L2 stacked bar")
    # 合并 4.1, 4.2, 4.3 的 runs
    all_runs = []
    for key in ("4.1", "4.2", "4.3"):
        all_runs.extend(subexps.get(key, []))

    if not all_runs:
        return

    requests = []
    for run in all_runs:
        for req in run.get("requests", []):
            requests.append((run.get("subexp", "4.1"), req))

    if not requests:
        return

    labels = []
    l0_hit = []
    l1_hit = []
    l2_hit = []
    miss = []

    for subexp, req in requests:
        label = req.get("label", "")
        prompt = req.get("prompt_tokens", 0)
        cached = req.get("cached_tokens", 0)
        labels.append(f"{subexp}\n{label}")

        # 从 subexp 推断 L0/L1/L2 分配
        if subexp == "4.1":
            # S1-T1: 冷启动，无命中; S1-T2: 全部命中
            if "T2" in label:
                l0_actual = min(cached, 5000)
                l1_actual = min(max(cached - 5000, 0), 1000)
                l2_actual = max(cached - 6000, 0)
            else:
                l0_actual = 0
                l1_actual = 0
                l2_actual = 0
        elif subexp == "4.2":
            # S2-T1: 命中 L0+L1_sqlfluff
            if "S2" in label:
                l0_actual = min(cached, 5000)
                l1_actual = min(max(cached - 5000, 0), 1000)
                l2_actual = max(cached - 6000, 0)
            else:
                l0_actual = 0
                l1_actual = 0
                l2_actual = 0
        elif subexp == "4.3":
            # S3-T1: 仅命中 L0
            if "S3" in label:
                l0_actual = min(cached, 5000)
                l1_actual = min(max(cached - 5000, 0), 800)
                l2_actual = max(cached - 5800, 0)
            else:
                l0_actual = 0
                l1_actual = 0
                l2_actual = 0
        else:
            l0_actual = 0
            l1_actual = 0
            l2_actual = cached

        miss_actual = max(0, prompt - cached)

        l0_hit.append(l0_actual)
        l1_hit.append(l1_actual)
        l2_hit.append(l2_actual)
        miss.append(miss_actual)

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(labels))
    width = 0.6

    p1 = ax.bar(x, l0_hit, width, label='L0 (Global Shared)', color='#3498db')
    p2 = ax.bar(x, l1_hit, width, bottom=l0_hit, label='L1 (Project-Level)', color='#2ecc71')
    p3 = ax.bar(x, l2_hit, width, bottom=np.array(l0_hit)+np.array(l1_hit),
                label='L2 (Session-Specific)', color='#f39c12')
    p4 = ax.bar(x, miss, width,
                bottom=np.array(l0_hit)+np.array(l1_hit)+np.array(l2_hit),
                label='Miss (Computed)', color='#e74c3c', alpha=0.5)

    ax.set_xlabel("Request")
    ax.set_ylabel("Tokens")
    ax.set_title("Experiment 4.1-4.3: Agent Multi-Session KV Cache Reuse (L0/L1/L2)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha='right')
    ax.legend(loc='upper right')

    # 在每个柱子顶部标注 hit rate
    for i, (subexp, req) in enumerate(requests):
        prompt = req.get("prompt_tokens", 0)
        cached = req.get("cached_tokens", 0)
        if prompt > 0:
            rate = cached / prompt * 100
            total = l0_hit[i] + l1_hit[i] + l2_hit[i] + miss[i]
            ax.text(i, total + 50, f"{rate:.0f}%", ha='center', fontsize=9, fontweight='bold')

    fig.tight_layout()
    save_fig(fig, "exp4_l0_l1_l2_reuse.png")


def _plot_exp4_concurrent(runs):
    """4.4: 并发竞争命中比较"""
    print("  [4.4] Concurrent competition")
    if not runs:
        return

    run = runs[-1]  # 取最后一个 run
    requests = run.get("requests", [])
    if not requests:
        return

    labels = []
    cached = []
    prompt = []
    colors = []

    for req in requests:
        label = req.get("label", "")
        labels.append(label)
        cached.append(req.get("cached_tokens", 0))
        prompt.append(req.get("prompt_tokens", 0))
        # S_A/S_B (sqlfluff) 蓝色, S_C (astroid) 橙色
        if "S_C" in label:
            colors.append('#e67e22')
        else:
            colors.append('#3498db')

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(labels))
    width = 0.4
    bars_cached = ax.bar(x - width/2, cached, width, label='Cached Tokens', color=colors, alpha=0.8)
    bars_prompt = ax.bar(x + width/2, prompt, width, label='Prompt Tokens', color=colors, alpha=0.3,
                         edgecolor=colors, linewidth=1.5)

    ax.set_xlabel("Request")
    ax.set_ylabel("Tokens")
    ax.set_title("Experiment 4.4: Concurrent Multi-Session Prefix Sharing")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    for bar, val in zip(bars_cached, cached):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
                    f"{val:.0f}", ha='center', va='bottom', fontsize=10, fontweight='bold')

    fig.tight_layout()
    save_fig(fig, "exp4_concurrent_sharing.png")


def _plot_exp4_eviction_protection(subexps):
    """4.5: 驱逐压力下 L0/L1 保护 — 有/无 offload 对比"""
    print("  [4.5] Eviction protection")
    runs_on = subexps.get("4.5_offload_on", [])
    runs_off = subexps.get("4.5_offload_off", [])
    if not runs_on and not runs_off:
        return

    # 提取 recovery_sqlfluff 请求的 cached_tokens
    cached_on = []
    cached_off = []
    ttft_on = []
    ttft_off = []

    for run in runs_on:
        for req in run.get("requests", []):
            if "recovery" in req.get("label", ""):
                cached_on.append(req.get("cached_tokens", 0))
                ttft_on.append(req.get("ttft_ms", 0))

    for run in runs_off:
        for req in run.get("requests", []):
            if "recovery" in req.get("label", ""):
                cached_off.append(req.get("cached_tokens", 0))
                ttft_off.append(req.get("ttft_ms", 0))

    if not cached_on and not cached_off:
        print("    No recovery data found")
        return

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    labels = ["No Offload", "With Offload\n(8 GiB)"]
    colors = ["#e74c3c", "#2ecc71"]

    # 左图: cached_tokens
    cached_means = [
        np.mean(cached_off) if cached_off else 0,
        np.mean(cached_on) if cached_on else 0,
    ]
    cached_stds = [
        np.std(cached_off) if cached_off else 0,
        np.std(cached_on) if cached_on else 0,
    ]
    bars = axes[0].bar(labels, cached_means, yerr=cached_stds, color=colors, capsize=5, width=0.5)
    axes[0].set_ylabel("Cached Tokens on Recovery")
    axes[0].set_title("L0/L1 Protection After Eviction")
    for bar, val in zip(bars, cached_means):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                     f"{val:.0f}", ha='center', va='bottom', fontsize=11, fontweight='bold')

    # 右图: TTFT
    ttft_means = [
        np.mean(ttft_off) if ttft_off else 0,
        np.mean(ttft_on) if ttft_on else 0,
    ]
    ttft_stds = [
        np.std(ttft_off) if ttft_off else 0,
        np.std(ttft_on) if ttft_on else 0,
    ]
    bars2 = axes[1].bar(labels, ttft_means, yerr=ttft_stds, color=colors, capsize=5, width=0.5)
    axes[1].set_ylabel("TTFT (ms)")
    axes[1].set_title("Recovery Latency")
    for bar, val in zip(bars2, ttft_means):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                     f"{val:.0f}ms", ha='center', va='bottom', fontsize=11, fontweight='bold')

    fig.suptitle("Experiment 4.5: L0/L1 Protection Under Eviction Pressure", fontsize=13, fontweight='bold')
    fig.tight_layout()
    save_fig(fig, "exp4_eviction_protection.png")


def _plot_exp4_recovery_speed(subexps):
    """4.6: Offloading 层级恢复速度 — 三路径 TTFT 对比"""
    print("  [4.6] Recovery speed comparison")
    runs_on = subexps.get("4.6_offload_on", [])
    runs_off = subexps.get("4.6_offload_off", [])
    if not runs_on and not runs_off:
        return

    # 从数据中提取三种路径 TTFT
    gpu_hit_ttft = []
    cpu_recovery_ttft = []
    full_recompute_ttft = []

    # 有 offloading 的运行：GPU hit + CPU recovery
    for run in runs_on:
        for req in run.get("requests", []):
            if "gpu_hit" in req.get("label", ""):
                gpu_hit_ttft.append(req.get("ttft_ms", 0))
            elif "req_C" in req.get("label", ""):
                cpu_recovery_ttft.append(req.get("ttft_ms", 0))

    # 无 offloading 的运行：GPU hit + full recompute
    for run in runs_off:
        for req in run.get("requests", []):
            if "gpu_hit" in req.get("label", ""):
                gpu_hit_ttft.append(req.get("ttft_ms", 0))
            elif "req_C" in req.get("label", ""):
                full_recompute_ttft.append(req.get("ttft_ms", 0))

    # 也可以从 recovery_paths 字段读取
    for run in runs_on:
        rp = run.get("recovery_paths", {})
        if rp.get("gpu_hit_ttft_ms"):
            gpu_hit_ttft.append(rp["gpu_hit_ttft_ms"])
        if rp.get("recovery_ttft_ms"):
            cpu_recovery_ttft.append(rp["recovery_ttft_ms"])

    for run in runs_off:
        rp = run.get("recovery_paths", {})
        if rp.get("gpu_hit_ttft_ms"):
            gpu_hit_ttft.append(rp["gpu_hit_ttft_ms"])
        if rp.get("recovery_ttft_ms"):
            full_recompute_ttft.append(rp["recovery_ttft_ms"])

    if not gpu_hit_ttft and not cpu_recovery_ttft and not full_recompute_ttft:
        print("    No recovery speed data found")
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    path_labels = ["GPU Direct\nHit", "CPU Offload\nRecovery", "Full\nRecomputation"]
    means = [
        np.mean(gpu_hit_ttft) if gpu_hit_ttft else 0,
        np.mean(cpu_recovery_ttft) if cpu_recovery_ttft else 0,
        np.mean(full_recompute_ttft) if full_recompute_ttft else 0,
    ]
    stds = [
        np.std(gpu_hit_ttft) if gpu_hit_ttft else 0,
        np.std(cpu_recovery_ttft) if cpu_recovery_ttft else 0,
        np.std(full_recompute_ttft) if full_recompute_ttft else 0,
    ]
    colors = ["#2ecc71", "#3498db", "#e74c3c"]

    bars = ax.bar(path_labels, means, yerr=stds, color=colors, capsize=5, width=0.5)
    ax.set_ylabel("TTFT (ms)")
    ax.set_title("Experiment 4.6: KV Cache Recovery Speed — Three Paths")

    for bar, val in zip(bars, means):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                    f"{val:.0f}ms", ha='center', va='bottom', fontsize=11, fontweight='bold')

    # 标注加速比
    if means[0] > 0 and means[2] > 0:
        speedup = means[2] / means[0]
        ax.text(0.5, 0.9, f"GPU hit {speedup:.1f}x faster than recomputation",
                transform=ax.transAxes, ha='center', fontsize=11, color='#27ae60', fontweight='bold')
    if means[0] > 0 and means[1] > 0:
        speedup = means[1] / means[0]
        ax.text(0.5, 0.82, f"CPU recovery {speedup:.1f}x vs GPU hit",
                transform=ax.transAxes, ha='center', fontsize=10, color='#2980b9')

    fig.tight_layout()
    save_fig(fig, "exp4_recovery_speed.png")


# ---------------------------------------------------------------------------
# 通用: KV Usage 时间线图
# ---------------------------------------------------------------------------

def plot_timeline(exp_name, title=None):
    """画 KV cache usage 随时间变化的曲线"""
    print(f"\n[Timeline] {exp_name}")
    runs = load_runs(exp_name)
    if not runs:
        return

    run = runs[-1]  # 取最后一个 run
    timeline = run.get("timeline", [])
    if not timeline:
        print(f"  No timeline data in {exp_name}")
        return

    times = [e["t"] for e in timeline]
    gpu_usage = [e.get("gpu_usage", 0) for e in timeline]

    fig, ax = plt.subplots(figsize=(12, 4))

    # 画 GPU usage 曲线
    ax.fill_between(times, gpu_usage, alpha=0.3, color='#3498db')
    ax.plot(times, gpu_usage, color='#3498db', linewidth=1.5, label='GPU KV Usage %')

    # 标注请求事件
    for e in timeline:
        if e["event"] == "req_start":
            ax.axvline(x=e["t"], color='#27ae60', linewidth=0.8, linestyle='--', alpha=0.7)
            ax.text(e["t"], ax.get_ylim()[1] * 0.95, f"▶ {e.get('label', '')}",
                    fontsize=7, rotation=90, va='top', ha='right', color='#27ae60')
        elif e["event"] == "req_end":
            ax.axvline(x=e["t"], color='#e74c3c', linewidth=0.8, linestyle='--', alpha=0.7)
            ax.text(e["t"], ax.get_ylim()[1] * 0.85, f"◀ {e.get('label', '')}",
                    fontsize=7, rotation=90, va='top', ha='right', color='#e74c3c')

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("GPU KV Cache Usage %")
    ax.set_title(title or f"KV Cache Usage Timeline — {exp_name}")
    ax.set_ylim(0, min(100, max(gpu_usage) * 1.3) if gpu_usage else 100)
    ax.legend(loc='upper left')

    fig.tight_layout()
    safe_name = exp_name.replace("/", "_")
    save_fig(fig, f"timeline_{safe_name}.png")


# ---------------------------------------------------------------------------
# 实验 5: 组感知驱逐 — 命中率对比
# ---------------------------------------------------------------------------

def plot_exp5():
    print("\n[Exp5] Agent-Aware Eviction Comparison")
    runs_lru = load_runs("exp5_lru_eviction")
    runs_aware = load_runs("exp5_aware_eviction")
    if not runs_lru and not runs_aware:
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    # 提取 S_sqlfluff T2 的 cached_tokens
    lru_cached = []
    aware_cached = []
    lru_ttft = []
    aware_ttft = []

    for run in runs_lru:
        for req in run.get("requests", []):
            if "recovery" in req.get("label", "") or "T2" in req.get("label", ""):
                lru_cached.append(req.get("cached_tokens", 0))
                lru_ttft.append(req.get("ttft_ms", 0))

    for run in runs_aware:
        for req in run.get("requests", []):
            if "recovery" in req.get("label", "") or "T2" in req.get("label", ""):
                aware_cached.append(req.get("cached_tokens", 0))
                aware_ttft.append(req.get("ttft_ms", 0))

    labels = ["Default LRU", "Agent-Aware\n(Preserved)"]
    cached_means = [
        np.mean(lru_cached) if lru_cached else 0,
        np.mean(aware_cached) if aware_cached else 0,
    ]
    ttft_means = [
        np.mean(lru_ttft) if lru_ttft else 0,
        np.mean(aware_ttft) if aware_ttft else 0,
    ]
    colors = ["#e74c3c", "#2ecc71"]

    x = np.arange(2)
    width = 0.35

    ax1 = ax
    ax2 = ax.twinx()

    bars1 = ax1.bar(x - width/2, cached_means, width, label='Cached Tokens', color=colors, alpha=0.8)
    bars2 = ax2.bar(x + width/2, ttft_means, width, label='TTFT (ms)', color=colors, alpha=0.5,
                    hatch='//')

    ax1.set_ylabel("Cached Tokens", color='#3498db')
    ax2.set_ylabel("TTFT (ms)", color='#e67e22')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_title("Experiment 5: Default LRU vs Agent-Aware Eviction")

    # 标注数值
    for bar, val in zip(bars1, cached_means):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                 f"{val:.0f}", ha='center', va='bottom', fontsize=10, fontweight='bold')
    for bar, val in zip(bars2, ttft_means):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                 f"{val:.0f}ms", ha='center', va='bottom', fontsize=10, fontweight='bold')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    fig.tight_layout()
    save_fig(fig, "exp5_aware_eviction.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PLOTTERS = {
    "exp1": plot_exp1,
    "exp2": plot_exp2,
    "exp3": plot_exp3,
    "exp4": plot_exp4,
    "exp4_1": plot_exp4,
    "exp4_2": plot_exp4,
    "exp4_3": plot_exp4,
    "exp4_4": plot_exp4,
    "exp4_5": plot_exp4,
    "exp4_6": plot_exp4,
    "exp5": plot_exp5,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_results.py [exp1|exp2|exp3|exp4|exp4_4|exp4_5|exp4_6|exp5|timeline|all]")
        print("  timeline — generate timeline plots for all experiments that have timeline data")
        print("  all      — generate all plots")
        return

    target = sys.argv[1].lower()

    if target == "all":
        for name, plotter in PLOTTERS.items():
            if not name.startswith("exp4_"):  # exp4 的子场景由 plot_exp4 统一处理
                plotter()
        # 也画时间线
        for exp_dir in os.listdir(EXPERIMENT_DIR):
            full = os.path.join(EXPERIMENT_DIR, exp_dir)
            if os.path.isdir(full) and exp_dir.startswith("exp"):
                plot_timeline(exp_dir)
    elif target == "timeline":
        for exp_dir in os.listdir(EXPERIMENT_DIR):
            full = os.path.join(EXPERIMENT_DIR, exp_dir)
            if os.path.isdir(full) and exp_dir.startswith("exp"):
                plot_timeline(exp_dir)
    elif target in PLOTTERS:
        PLOTTERS[target]()
    else:
        print(f"Unknown experiment: {target}")
        print(f"Available: {', '.join(sorted(set(PLOTTERS.keys())))}, timeline, all")


if __name__ == "__main__":
    main()
