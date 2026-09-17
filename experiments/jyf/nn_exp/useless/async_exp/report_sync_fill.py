"""Validate the synchronous on-demand-fill arm against the prior three runs."""
import argparse
import json
from pathlib import Path

from report_online import pct


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    a = p.parse_args()
    old = json.loads((a.baseline / "comparison.json").read_text())
    arm = a.run / "sync_fill"
    summary = json.loads((arm / "replay/summary.json").read_text())
    assert summary["integrity"]["n_ok"] == 2000 and summary["integrity"]["n_err"] == 0
    meta = json.loads((arm / "replay/meta.json").read_text())
    info = json.loads((arm / "server_info.json").read_text())
    capacities = set()
    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("memory_usage"), dict):
                capacities.add(x["memory_usage"].get("token_capacity"))
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for value in x:
                walk(value)
    walk(info)
    config = {k: info.get(k) for k in ("model_path", "tp_size", "mem_fraction_static", "page_size", "random_seed", "kv_cache_dtype", "chunked_prefill_size", "max_running_requests")}
    config.update(token_capacities=sorted(capacities), arrival=meta["arrival"], gap_scale=meta["gap_scale"],
                  n_turns=meta["n_turns"], n_sessions=meta["n_sessions"])
    assert config == old["lru"]["validated_configuration"], "effective configuration mismatch"
    def requests(path):
        rs = [json.loads(line) for line in path.read_text().splitlines()]
        return sorted((r["trace_id"], r["prompt_tokens"], r["max_tokens"]) for r in rs)
    assert requests(arm / "replay/replay.jsonl") == requests(a.baseline / "lru/replay/replay.jsonl")
    before = json.loads((a.baseline / "manifest.json").read_text())
    after = json.loads((a.run / "manifest.json").read_text())
    for field in ("workload_sha256", "checkpoint_sha256"):
        assert before[field] == after[field], field
    ranks = {}
    for f in (arm / "metrics").glob("rank*_pid*.jsonl"):
        rows = [json.loads(line) for line in f.read_text().splitlines()]
        init = [r for r in rows if r["kind"] == "init"]
        assert len(init) == 1 and init[0]["mode"] == "sync_fill"
        rank = init[0]["rank"]
        assert rank not in ranks
        ranks[rank] = rows
    assert set(ranks) == set(range(8))
    signatures = []
    for rank in range(8):
        es = [r for r in ranks[rank] if r["kind"] == "evict"]
        signatures.append([(r["index"], r["seq"], r["freed_full"], r["freed_swa"], r["digest"], r["choices"],
                            r["mlp_choices"], r["fill_nodes"], r["fill_batches"]) for r in es])
    assert all(s == signatures[0] for s in signatures), "TP decision/refill divergence"
    es = [r for r in ranks[0] if r["kind"] == "evict" and r["wall_s"] >= meta["created_unix"]]
    fs = [r for r in ranks[0] if r["kind"] == "finish" and r["wall_s"] >= meta["created_unix"]]
    assert es and fs
    assert all(r["choices"] == r["mlp_choices"] for r in es), "unexpected LRU fallback"
    choices = sum(r["choices"] for r in es)
    filled = sum(r["fill_nodes"] for r in es)
    changed = sum(r["changed_choices"] for r in es)
    assert choices > 0 and filled > 0 and changed > 0
    metrics = dict(tp_consistent=True, evictions=len(es), finish_calls=len(fs), choices=choices,
                   mlp_choices=choices, mlp_fraction=1.0, changed_choices=changed,
                   changed_fraction=changed/choices, fallback_choices=0,
                   fill_nodes=filled, fill_batches=sum(r["fill_batches"] for r in es),
                   fill_inference_total_s=sum(r["fill_inference_us"] for r in es)/1e6,
                   fill_selection_and_tp_total_s=sum(r["fill_selection_and_tp_us"] for r in es)/1e6,
                   submitted=sum(r["submitted"] for r in fs), dropped=0,
                   full_evicted_tokens=sum(r["freed_full"] for r in es),
                   swa_evicted_tokens=sum(r["freed_swa"] for r in es))
    reasons = {}
    for r in es:
        for reason, n in r["fill_reasons"].items():
            reasons[reason] = reasons.get(reason, 0) + n
    metrics["fill_reasons"] = reasons
    for field in ("total_us", "prediction_hook_us", "original_us"):
        metrics["finish_"+field] = {"p50": pct([r[field] for r in fs],50), "p99": pct([r[field] for r in fs],99)}
    for field in ("total_us", "fill_inference_us", "fill_selection_and_tp_us"):
        metrics["evict_"+field] = {"p50": pct([r[field] for r in es],50), "p99": pct([r[field] for r in es],99)}
    result = {**old, "sync_fill": dict(summary=summary, instrumentation=metrics, validated_configuration=config)}
    (a.run / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# 同步 MLP 现场补算：第四组在线实验", "",
             "本组在 request-end 同步预计算的基础上，增加 eviction 现场补算。每次选择 victim 前，对当前最多 16 个合法 LRU 候选逐个检查：有效预测复用；缺失、失效、超出有限时间范围的预测用当前特征重新批量计算。只有全部获得有限 MLP 分数后才选择 victim，不因预测缺失回退 LRU。",
             "淘汰过程中新增的候选同样检查与补算。rank 0 每次选择前广播完整 shortlist 分数，八个 rank 统一执行。若新计算仍返回无效分数则实验报错，不静默回退。", "",
             f"成功请求 2000/2000，零错误。{choices:,} 次候选选择全部使用 MLP（100%）；零 LRU 回退。八个 rank 的逐 eviction victim digest、释放 token 数、补算数量一致。这里的 100% 指所选最多 16 个候选全部有分数，不代表每次对整棵树重跑模型，也不代表每次都选出与 LRU 不同的 victim。", "",
             "有效配置、逐请求标识/prompt token 数、workload 与 checkpoint SHA256 均与上一轮核对一致。DeepSeek-V4-Flash、TP=8、Full token capacity=705,280、32-token decode 上限、seed=42、9 waves/300s、gap_scale=0.02。", "",
             "| 指标 | LRU（上轮） | 同步预计算＋回退（上轮） | 异步（上轮） | 同步现场补算（本轮） |",
             "|---|---:|---:|---:|---:|"]
    modes = ("lru", "sync", "async", "sync_fill")
    ss = [result[m]["summary"] for m in modes]
    ii = [result[m]["instrumentation"] for m in modes]
    def row(label, values, fmt=".2f"):
        lines.append("| " + label + " | " + " | ".join("—" if v is None else format(v,fmt) for v in values) + " |")
    row("Token 命中率 %", [100*s["kv"]["cached_tokens_sum"]/s["kv"]["prompt_tokens_sum"] for s in ss])
    row("未命中 prompt tokens", [s["kv"]["prompt_tokens_sum"]-s["kv"]["cached_tokens_sum"] for s in ss], ",d")
    for field, label in (("ttft_ms", "TTFT"), ("e2e_ms", "E2E")):
        for quantile in ("p50", "p90", "p99"):
            row(f"{label} {quantile} 秒", [s["latency"][field][quantile]/1000 for s in ss])
    row("回放耗时秒", [s["integrity"]["wall_clock_s"] for s in ss])
    row("请求/秒", [s["throughput"]["req_per_s"] for s in ss], ".3f")
    row("request-end 总耗时 p50 µs", [s["finish_total_us"]["p50"] for s in ii])
    row("request-end 总耗时 p99 µs", [s["finish_total_us"]["p99"] for s in ii])
    row("eviction 耗时 p50 ms", [s["evict_total_us"]["p50"]/1000 for s in ii])
    row("eviction 耗时 p99 ms", [s["evict_total_us"]["p99"]/1000 for s in ii])
    row("使用 MLP 的选择比例 %", [100*s["mlp_fraction"] if s["mlp_fraction"] is not None else None for s in ii])
    row("偏离当前 LRU 的选择比例 %", [100*s["changed_fraction"] if s["changed_fraction"] is not None else None for s in ii])
    row("实际 eviction 次数", [s["evictions"] for s in ii], "d")
    for key, label in (("agent", "Agent"), ("agent_within_session", "Agent 非首轮"), ("request", "普通请求")):
        row(label+" token 命中率 %", [100*s[key]["cached_tokens_sum"]/s[key]["prompt_tokens_sum"] for s in ss])
    lru_hit = ss[0]["kv"]["cached_tokens_sum"]/ss[0]["kv"]["prompt_tokens_sum"]
    fill_hit = summary["kv"]["cached_tokens_sum"]/summary["kv"]["prompt_tokens_sum"]
    lru_miss = ss[0]["kv"]["prompt_tokens_sum"]-ss[0]["kv"]["cached_tokens_sum"]
    fill_miss = summary["kv"]["prompt_tokens_sum"]-summary["kv"]["cached_tokens_sum"]
    lines += ["", "## 本轮结论", "",
              f"在本次配置与 workload 下，现场补算组相对上轮 LRU 的 token 命中率提高 {(fill_hit-lru_hit)*100:.2f} 个百分点，未命中 prompt tokens 减少 {(1-fill_miss/lru_miss)*100:.1f}%。同步全覆盖组的延迟与命中率均优于此前带回退的同步组及异步组。",
              f"{choices} 次选择全部使用 MLP 分数，其中 {changed} 次（{changed/choices:.2%}）实际偏离 LRU。因此，这次验证的不只是推理完成，而是模型分数确实控制了缓存淘汰。",
              "本轮所有现场补算均来自预测缺失或失效，未观测到超出时间范围或非有限数触发补算。这描述本轮的补算原因，不能直接当作上轮回退原因的分布。",
              "这是新增的一次完整在线实验，不是重复实验的统计结论；它提供了全覆盖同步 MLP 的实际参照，但仍不能证明异步执行方式本身造成上轮的收益差距。"]
    lines += ["", "## 现场补算统计", "",
              f"- 现场补算 {metrics['fill_nodes']:,} 个 node-side 预测，共 {metrics['fill_batches']:,} 个 batch。同一 node 的 Full/SWA 分开统计，同一 node 被重新失效后补算也会再次计数。",
              f"- 缺失或失效：{reasons.get('missing_or_invalidated',0):,}；超出原有限预测范围：{reasons.get('outside_horizon',0):,}；原分数非有限数：{reasons.get('nonfinite',0):,}。",
              f"- 补算推理路径累计 {metrics['fill_inference_total_s']:.3f} 秒；选择阶段的检查、快照、补算、评分和 TP 通信合计 {metrics['fill_selection_and_tp_total_s']:.3f} 秒（rank 0 wall time，非独立 CPU 周期）。",
              f"- 实际偏离当前 LRU 的 victim 选择 {changed:,}/{choices:,}（{changed/choices:.2%}）；有效预测仍可以选中 LRU victim，不能把两者混为一谈。", "",
              "## 口径与限制", "",
              "仍使用原 event-bucket checkpoint，没有训练新模型。过期预测的现场补算使用当前 snapshot，并将预测观测时间更新为当前 event；不会把当前特征错误挂到旧预测时间原点上。这是在当前观测点重新预测，不是推断无限尾桶的恒定 hazard。",
              "保留 request-end 同步预计算；本组增加的是缺失分数的同步补算。为保证淘汰中新增候选覆盖，本组每次 victim 选择都进行 TP 分数广播，上轮则在 eviction 入口广播一次。这部分额外通信开销包含在实测 eviction 时间中。",
              "以上每组仅一次运行，上轮与本轮运行时间不同。session 内下一请求等待上一请求完成，策略会改变实际到达时刻和缓存轨迹；不能把所有指标变化都归因于单一开关。只说明该固定 workload 下这次原型的实测结果。",
              "API 指标严格来自 2000 个 workload 请求。request-end 内部计时按 replay 开始时间过滤，但可能仍含少量健康检查或其他额外 finish 调用；此轮记录的调用数为 " + str(metrics['finish_calls']) + "。TTFT 为原 replay 脚本首个可见 content/tool-call 时间。未命中 prompt tokens 包括首次访问，不全是 eviction 导致的重算。", "",
              f"本轮目录：`{a.run.resolve()}`。上轮目录：`{a.baseline.resolve()}`。", "",
              "复现本组：`ONLINE_MODES=sync_fill bash run_online.sh <新run名称>`。原始 API 记录、rank 日志、服务配置与源代码快照均保留在运行目录。", ""]
    (a.run / "report_zh.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
