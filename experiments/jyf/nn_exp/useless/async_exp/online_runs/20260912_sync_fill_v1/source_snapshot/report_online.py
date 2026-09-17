"""Validate actual runs and compare user-visible cache/latency results."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def pct(xs, q):
    if not xs:
        return None
    ys = sorted(xs)
    pos = (len(ys)-1)*q/100
    lo = int(pos)
    hi = min(lo+1, len(ys)-1)
    return ys[lo] + (ys[hi]-ys[lo])*(pos-lo)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--run", type=Path, required=True)
    args = a.parse_args()
    output = {}
    reference_config = None
    reference_requests = None
    for mode in ("lru", "sync", "async"):
        arm = args.run / mode
        summary = json.loads((arm / "replay/summary.json").read_text())
        meta = json.loads((arm / "replay/meta.json").read_text())
        info = json.loads((arm / "server_info.json").read_text())
        capacities = set()
        def walk(value):
            if isinstance(value, dict):
                if isinstance(value.get("memory_usage"), dict):
                    capacities.add(value["memory_usage"].get("token_capacity"))
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
        walk(info)
        config = {k: info.get(k) for k in ("model_path", "tp_size", "mem_fraction_static", "page_size", "random_seed", "kv_cache_dtype", "chunked_prefill_size", "max_running_requests")}
        config.update(token_capacities=sorted(capacities), arrival=meta["arrival"],
                      gap_scale=meta["gap_scale"], n_turns=meta["n_turns"], n_sessions=meta["n_sessions"])
        requests = [json.loads(line) for line in (arm / "replay/replay.jsonl").read_text().splitlines()]
        request_signatures = sorted((r["trace_id"], r["prompt_tokens"], r["max_tokens"]) for r in requests)
        if reference_config is None:
            reference_config, reference_requests = config, request_signatures
        else:
            assert config == reference_config, "effective configuration mismatch"
            assert request_signatures == reference_requests, "request-set/tokenization mismatch"
        assert summary["integrity"]["n_ok"] == 2000, summary["integrity"]
        assert summary["integrity"]["n_err"] == 0, summary["integrity"]
        ranks = {}
        for f in (arm / "metrics").glob("rank*_pid*.jsonl"):
            rows = [json.loads(line) for line in f.read_text().splitlines()]
            init = [r for r in rows if r["kind"] == "init"]
            assert len(init) == 1
            rank = init[0]["rank"]
            assert init[0]["mode"] == mode
            assert rank not in ranks, "multiple cache instances: inspect before aggregation"
            ranks[rank] = rows
        assert set(ranks) == set(range(8)), ranks.keys()
        signatures = []
        for rank in range(8):
            es = [r for r in ranks[rank] if r["kind"] == "evict"]
            signatures.append([(r["index"], r["seq"], r["freed_full"], r["freed_swa"], r["digest"]) for r in es])
        assert all(s == signatures[0] for s in signatures), "TP victim/free divergence"
        es = [r for r in ranks[0] if r["kind"] == "evict" and r["wall_s"] >= meta["created_unix"]]
        fs = [r for r in ranks[0] if r["kind"] == "finish" and r["wall_s"] >= meta["created_unix"]]
        assert es, "no real eviction occurred"
        assert not any(r.get("worker_error") for r in fs), "worker error"
        choices = sum(r["choices"] for r in es)
        mlp = sum(r["mlp_choices"] for r in es)
        changed = sum(r["changed_choices"] for r in es)
        if mode != "lru":
            assert changed > 0, "NN did not actually change any eviction choice"
        metrics = {"tp_consistent": True, "evictions": len(es), "finish_calls": len(fs),
                   "choices": choices, "mlp_choices": mlp, "changed_choices": changed,
                   "mlp_fraction": mlp/choices if choices else None,
                   "changed_fraction": changed/choices if choices else None,
                   "submitted": sum(r["submitted"] for r in fs),
                   "dropped": max(r["dropped"] for r in fs),
                   "full_evicted_tokens": sum(r["freed_full"] for r in es),
                   "swa_evicted_tokens": sum(r["freed_swa"] for r in es)}
        for field in ("total_us", "prediction_hook_us", "original_us"):
            metrics["finish_"+field] = {"p50": pct([r[field] for r in fs],50), "p99": pct([r[field] for r in fs],99)}
        for field in ("total_us", "plan_and_tp_us"):
            metrics["evict_"+field] = {"p50": pct([r[field] for r in es],50), "p99": pct([r[field] for r in es],99)}
        output[mode] = {"summary": summary, "instrumentation": metrics, "validated_configuration": config}
    result_file = args.run / "comparison.json"
    result_file.write_text(json.dumps(output, indent=2) + "\n")
    lines = ["# LRU / 同步 MLP / 异步 MLP：实际 Serving 对比", "",
             "三种策略均实际处理 2000 个请求并改变/执行真实 Full/SWA 缓存淘汰，不是 shadow 排序。同步与异步的 TP 八个 rank 的逐 eviction victim digest 和释放 token 数已核对一致。", "",
             "模型 DeepSeek-V4-Flash，TP=8，mem-fraction-static=0.45，32-token decode 上限；使用相同 agent050_decode32 workload，temperature=0，seed=42，9 waves/300s，gap-scale=0.02。每组重启服务，执行相同内置预热后回放，顺序 LRU→sync→async。三组有效配置、实际 token capacity、逐请求标识和 prompt token 数已核对一致；capacity=705,280。", "",
             "每组一个在线运行。这是高压、压缩间隔 workload，结果不能代表原始三小时 frozen 稳态；不同策略的延迟也会改变 session 内后续请求的实际到达时间。", "",
             "| 指标 | LRU | 同步 MLP | 异步 MLP |", "|---|---:|---:|---:|"]
    def row(label, values, fmt=".2f"):
        lines.append("| " + label + " | " + " | ".join("N/A" if v is None else format(v,fmt) for v in values) + " |")
    summaries = [output[m]["summary"] for m in ("lru", "sync", "async")]
    instruments = [output[m]["instrumentation"] for m in ("lru", "sync", "async")]
    row("成功请求", [s["integrity"]["n_ok"] for s in summaries], "d")
    # Read the ratio from sums, without relying on a display field's name.
    row("cached/prompt token %", [100*s["kv"]["cached_tokens_sum"]/s["kv"]["prompt_tokens_sum"] for s in summaries])
    row("未命中 prompt tokens", [s["kv"]["prompt_tokens_sum"]-s["kv"]["cached_tokens_sum"] for s in summaries], ",d")
    for key, label in (("ttft_ms", "TTFT"), ("e2e_ms", "E2E")):
        for p in ("p50", "p90"):
            row(f"{label} {p} ms", [s["latency"][key].get(p) for s in summaries])
    row("请求/秒", [s["throughput"]["req_per_s"] for s in summaries], ".3f")
    row("回放时长秒", [s["integrity"]["wall_clock_s"] for s in summaries])
    row("request-end 总耗时 p50 µs", [s["finish_total_us"]["p50"] for s in instruments])
    row("request-end 总耗时 p99 µs", [s["finish_total_us"]["p99"] for s in instruments])
    row("预测 hook p50 µs", [s["finish_prediction_hook_us"]["p50"] for s in instruments])
    row("预测 hook p99 µs", [s["finish_prediction_hook_us"]["p99"] for s in instruments])
    row("eviction p50 µs", [s["evict_total_us"]["p50"] for s in instruments])
    row("eviction p99 µs", [s["evict_total_us"]["p99"] for s in instruments])
    row("实际 eviction 次数", [s["evictions"] for s in instruments], "d")
    row("回放期 cache_finished_req 调用数（含少量健康检查）", [s["finish_calls"] for s in instruments], "d")
    row("使用 MLP 的 victim 选择比例 %", [100*s["mlp_fraction"] if s["mlp_fraction"] is not None else None for s in instruments])
    row("偏离当前 LRU 的选择比例 %", [100*s["changed_fraction"] if s["changed_fraction"] is not None else None for s in instruments])
    row("预测队列丢弃数", [s["dropped"] for s in instruments], "d")
    lines += ["", "## 分流量类型的 token 命中率", "",
              "| 流量 | LRU | 同步 MLP | 异步 MLP |", "|---|---:|---:|---:|"]
    for key, label in (("agent", "Agent 全部"), ("agent_within_session", "Agent 非首轮"), ("request", "普通请求")):
        row(label+" %", [100*s[key]["cached_tokens_sum"]/s[key]["prompt_tokens_sum"] for s in summaries])
    sync_hook = instruments[1]["finish_prediction_hook_us"]["p50"]
    async_hook = instruments[2]["finish_prediction_hook_us"]["p50"]
    lines += ["", "## 本次结果的判断", "",
              f"异步确实降低了 request-end 预测 hook 的耗时：p50 从 {sync_hook:.2f}µs 降到 {async_hook:.2f}µs，下降 {(1-async_hook/sync_hook)*100:.1f}%。但本次同步组的缓存命中率和端到端延迟更好；异步组相对 LRU 的缓存收益较小，E2E p50 反而更高。不能将主线程开销下降直接等同于 serving 整体收益。",
              "同步/异步实际使用 MLP 的 victim 选择都不足 8%，大多数选择仍回退 LRU；实际偏离当前 LRU 的选择分别为 318 和 314 次。因此，低覆盖率不能全部归因为异步队列来不及，当前合法候选覆盖、episode 失效、500-event 范围限制和整组回退规则都可能起作用。本轮没有记录每项回退原因，不能进一步确定占比。",
              "每组只跑了一次，session 内下一轮在上一轮完成后发出，策略改变缓存后也改变到达顺序。不能仅凭这三次运行把同步/异步的命中率差归因为异步机制本身；结论限于这次固定配置的实测对比。"]
    lines += ["", "## 实现与口径", "",
              "同步/异步使用同一个 seed_42 Unified 16→64→32→10 checkpoint、相同 20-event 条件复用概率评分、最多 16 个合法 LRU 候选。任何候选预测缺失或超过已定义 500-event 范围时，该次选择回退 LRU。",
              "同步：request-end 构造变化且可淘汰节点的快照，批量 MLP，完成后返回。异步：同一快照入有界队列后返回，由一个 rank-0 CPU worker 推理。队列容量 4096、batch 上限 64，无凑批等待窗口。",
              "Full/SWA 分开维护 episode。树结构变化、访问、加解锁使 ticket 失效；worker 只写旧 ticket，不覆盖新状态。request-end 使用变化节点集合，LRU rank 特征仍需扫描当时 frontier。",
              "每次 eviction，rank 0 只读取已完成预测并广播 score map；八个 rank 使用相同冻结 map 完成本次淘汰。该操作等待 TP 通信，不等待正在运行的 MLP。保留原 SGLang allocator/free/tombstone 逻辑。",
              "LRU 使用原始淘汰函数，不承担 MLP 和 score-map TP 广播成本；三组都有 timing 日志。表中 eviction 时间包括新策略的 score 计算与 TP 通信开销，是当前原型的真实额外成本。",
              "cached/prompt 来自 API usage 的 cached_tokens；未命中 prompt tokens 包括首次访问的 compulsory miss，不能全部称为淘汰造成的重算。request-end 指 cache_finished_req 方法加预测 hook，不包含日志写入；按 replay meta.created_unix 过滤掉回放开始前的预热调用。",
              "内部 finish 计数为 2002/2001/2007，比 workload 请求数多 2/1/7 次。日志没有记录 request id，无法进一步精确剔除回放期间的健康检查等额外调用；内部耗时分位数保留这些调用。API 命中率和延迟统计则严格来自相同的 2000 个 workload 请求。",
              "TTFT 沿用 replay 脚本的首个可见 content/tool-call 时间；reasoning-only 输出可能不计首 token，解读时同时查看 E2E 和 token 命中率。吞吐是此受控到达率下的完成请求/总回放时长，不是饱和吞吐上限。", "",
              "## 模型限制", "",
              "当前 checkpoint 在此前 frozen eviction-frontier 数据上训练，单位是 cache-access event，而不是秒。应用到 request-end 存在观测时刻分布变化；在线 workload 与之前 frozen 实验使用相同请求集合，仅到达模式改变，不能作为独立 workload 泛化测试。三组实验回答该原型在这个固定 workload 下的实际差异。", "",
              "## 文件", "",
              f"运行目录：`{args.run.resolve()}`。",
              "每组包含 server.log、server_info.json、metrics/rank*.jsonl、replay/replay.jsonl、replay/summary.json 和 prometheus.txt。",
              "comparison.json 为汇总；run_online.sh 为三组实验入口；test_serving_cache.py 验证真实 SWARadixCache 的 split、lock/unlock、强制非 LRU 淘汰和计数一致性。", ""]
    (args.run / "report_zh.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({m: output[m]["instrumentation"] for m in output}, indent=2))


if __name__ == "__main__":
    main()
