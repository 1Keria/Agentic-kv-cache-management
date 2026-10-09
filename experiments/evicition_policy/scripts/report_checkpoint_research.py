#!/usr/bin/env python3
"""Generate a concise, auditable research report from accepted no-split runs."""

import argparse
import json
from pathlib import Path

from analyze_resizable_native import read, digest

ROOT = Path(__file__).resolve().parents[1]
PHASES = ("initial", "half", "quarter", "restored")
NAMES = {"initial": "初始", "half": "半容量", "quarter": "四分之一容量", "restored": "恢复"}
VARIANTS = ("lru", "v1", "v2", "partial", "v3", "workspace")


def report(source, workspace_source, output):
    v3, workspace = read(source), read(workspace_source)
    assert v3["all_checks_passed"] and workspace["all_checks_passed"]
    assert workspace["v3_analysis_sha256"] == digest(source)
    assert output.resolve().is_relative_to(ROOT / "reports")
    all_conditions = {**v3["archived_baselines"], **v3["conditions"], **workspace["conditions"]}
    comparisons = workspace["comparisons"]
    main = comparisons["shrink_restore_workspace_vs_v2"]
    partial = v3["comparisons"]["shrink_restore_partial_vs_v2"]
    downgrade = v3["comparisons"]["shrink_restore_v3_vs_partial"]
    success = all(workspace["stage_acceptance"][p] for p in ("half", "quarter"))
    recommendation = ("保留按已到达工作集预留 Full 空间的版本作为下一阶段候选。" if success else
                      "工作空间预留尚未同时通过两个缩容阶段的净收益门槛，不升级为推荐版本。")
    pct = lambda item: f"{100 * item['hit_rate']:.4f}%"
    signed = lambda value: f"{value:+.4f}"
    rate = lambda variant, phase: pct(all_conditions["shrink_restore_" + variant]["phases"][phase])
    lines = ["# 浅检查点与工作空间预留 v3 验证", "",
        "日期：2026-10-09。范围：纯 Agent 请求，官方 Full/SWA CPU 树与真实索引分配器；不含模型 KV payload、decode、GPU 时延或混合流量反馈。", "",
        "## 结论", "", recommendation,
        f"单独增加浅检查点，在四分之一容量相对 v2 的净命中变化为 {signed(partial['phases']['quarter']['hit_rate_delta_pp'])} 个百分点；"
        f"再增加已有祖先降级，相对浅检查点的变化为 {signed(downgrade['phases']['quarter']['hit_rate_delta_pp'])} 个百分点。",
        f"增加工作空间预留后，四分之一容量命中率由 v2 的 {rate('v2','quarter')} 变为 {rate('workspace','quarter')}；"
        f"缩容恢复全程相对 v2 为 {signed(main['total']['hit_rate_delta_pp'])} 个百分点。",
        "这些对照检验的是同一状态机中各机制的增量。阶段净收益已计入所有退化请求；不把合法浅边界的存在解释为必然收益，也不把历史 Full 缺失解释为物理上绝对无解。", "",
        "## 冻结设置与审计", "",
        "冻结 20 会话、1,206 请求，每条件输入 48,787,785 token。页大小 256、窗口 128、prefill 分块 8,192。"
        "Full/SWA 预算依次为 589,824/52,224 → 294,912/26,112 → 147,456/13,056 → 恢复初始；切换索引为 301、603、904。",
        "v2、partial-only、v3 各执行恒定容量和缩容恢复两条件，共 7,236 请求；工作空间版本另执行两条件，共 2,412 请求。"
        "**接受的 8 个条件共 9,648 请求**。LRU/v1 引用同输入、同顺序、同预算的冻结归档。",
        "v2 与归档逐请求复现命中、Full 驻留匹配、历史匹配和真实释放；预算、锁、物理页所有权、真实 free、单元生命周期、源码和输入哈希审计通过。"
        "本次接受的全部条件新增输入边界拆分和窗口尾拆分均为 0。原 47 项检查和新增 4 项检查通过，回执独立保存。", "",
        "## 命中结果", "",
        "| 变容量阶段 | LRU | v1 | v2 | 浅检查点 | v3 加祖先降级 | v3 加工作空间 |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for phase in PHASES:
        lines.append("| " + NAMES[phase] + " | " + " | ".join(rate(v, phase) for v in VARIANTS) + " |")
    lines.append("| 全程 | " + " | ".join(pct(all_conditions["shrink_restore_" + v]["total"]) for v in VARIANTS) + " |")
    lines += ["", "| 恒定容量全程 | LRU | v1 | v2 | 浅检查点 | v3 加祖先降级 | v3 加工作空间 |",
              "|---|---:|---:|---:|---:|---:|---:|",
              "| 命中率 | " + " | ".join(pct(all_conditions["constant_" + v]["total"]) for v in VARIANTS) + " |", "",
              "工作空间版本相对 v2 的完整收益/损失分布：", "",
              "| 阶段 | 净变化 pp | 净新增命中 token | 改善 token | 退化 token | 改善请求 | 退化请求 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for phase in PHASES:
        d = main["phases"][phase]
        lines.append(f"| {NAMES[phase]} | {signed(d['hit_rate_delta_pp'])} | {d['matched_token_delta']:,} | {d['positive_tokens']:,} | {d['negative_tokens']:,} | {d['improved_requests']} | {d['regressed_requests']} |")
    sessions = workspace["descriptive_session_deltas"]["shrink_restore"]
    session_net = [s["total_vs_v2"]["matched_token_delta"] for s in sessions.values()]
    lines += ["", f"按会话汇总，工作空间版本相对 v2：{sum(x>0 for x in session_net)} 个会话净改善、"
              f"{sum(x<0 for x in session_net)} 个净退化、{sum(x==0 for x in session_net)} 个相同。"
              "这是同一已探索负载内的描述统计，不是独立泛化验证或置信区间。", "",
              "## 工作空间规则与机制证据", "",
              "Full 保护上限采用 `min(262144, max(0, Full硬预算 − 已到达完整输入的页对齐长度高水位))`。"
              "每个请求使用本次已到达输入长度更新高水位；预算事件使用此前已到达请求的高水位。SWA 上限仍为 4,096，单元最多 8 个。"
              "缩容和扩容都不重置缓存；扩容可恢复保护上限。逐请求在线公式已独立重算核验。", "",
              "| 变容量阶段 | Full 保护上限最小值 | 最大值 |",
              "|---|---:|---:|"]
    for phase, a in workspace["workspace_audits"]["shrink_restore_workspace"]["phases"].items():
        lines.append(f"| {NAMES[phase]} | {a['min_cap']:,} | {a['max_cap']:,} |")
    lines += ["", "资格生命周期观测：", "",
              "| 变体（变容量） | 准入单元 | 保护期间被复用单元 | 复用事件 | 祖先降级次数 |",
              "|---|---:|---:|---:|---:|"]
    for variant in ("v2", "partial", "v3", "workspace"):
        summary = workspace if variant == "workspace" else v3
        name = "shrink_restore_" + variant
        life = summary["unit_lifecycle"][name]
        counts = summary["conditions"][name]["frontier_counts"]
        downgrades = sum(value for key, value in counts.items() if key.startswith("resident_downgrades_"))
        lines.append(f"| {variant} | {life['admitted_units']} | {life['units_reused_while_protected']} | {life['observed_reuse_events']} | {downgrades} |")
    lines += ["", "降级在真实 Full/SWA 连续窗口存在时才允许，缺失窗口不会补造 KV。"
              "工作空间上限限制深边界的保护资格，允许请求正常计算与原生缓存准入。"
              "对照支持在压力前限制保护占用这个方向，但尚未识别每个被替代 victim 的完整反事实价值。", "",
              "## 未通过结构审计的首轮结果", "",
              "初始 v3 的浅边界登记继承了旧尾部隔离操作，恒定容量增加 26 次窗口尾拆分、变容量增加 18 次；"
              "初始工作空间版本分别增加 26/20 次。因此原 v3 分析器按预设零拆分条件拒绝该轮；没有放松门槛。"
              "两批完整结果和拒绝回执保留。新版本只读查找已有精确节点，按实际压缩节点依赖收费，重新冻结后完整执行。"
              "预算、单元数和工作空间公式未因首轮结果调参。", "",
              "## 限制与下一步", "",
              "当前证据来自一条已探索的确定性输入轨迹和外部固定容量轨迹。请求按合成串行轮询调度，原始自然时间与闭环工具执行没有被重建。"
              "全输入最大长度用于驱动的容量可执行性检查；工作空间策略高水位只使用已到达长度。",
              "工作空间预留会双计活跃请求与受保护前缀共享的页，是保守消融。高水位遇到长请求后不会随短请求下降；"
              "未证明此公式最优，也未证明 GPU TTFT、混合流量分区收益或跨负载泛化。",
              "下一阶段先冻结独立会话与顺序对照、扫描容量和长请求占比；保持逐阶段净收益门槛，并记录共享页双计的代价。"
              "GPU 服务验证留待资源可用后进行，不能把这里的命中增量换算为时延收益。", "",
              "## 可复核产物", "",
              f"- [v3 分析]({str(source.relative_to(ROOT/'reports')) if source.is_relative_to(ROOT/'reports') else '../'+str(source.relative_to(ROOT))})",
              f"- [工作空间分析](../{workspace_source.relative_to(ROOT)})",
              "- [比较图](figures/checkpoint_frontier_20261009/native_checkpoint_comparison.png)",
              "- [研究接续入口](Agent策略研究接续.md)", ""]
    with output.open("x") as stream:
        stream.write("\n".join(lines))
    compact = {"schema": "agentkv.checkpoint_research_report.v3", "accepted_requests": 9648,
        "audits_passed": True, "recommend_workspace_candidate": success,
        "analysis_sha256": {str(p.relative_to(ROOT)): digest(p) for p in (source, workspace_source)},
        "stage_acceptance": workspace["stage_acceptance"], "conditions": all_conditions,
        "mechanism_comparisons": {"partial_vs_v2": partial, "downgrade_increment": downgrade, **comparisons},
        "limitations": workspace["limitations"]}
    with output.with_suffix(".json").open("x") as stream:
        json.dump(compact, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(output), "recommend_workspace_candidate": success}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report(args.source.resolve(), args.workspace_source.resolve(), args.output.resolve())
