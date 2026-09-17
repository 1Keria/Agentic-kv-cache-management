"""Generate the Chinese report directly from measured JSON results."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    r = json.loads((args.run / "results.json").read_text())
    extra = json.loads((args.run / "additional_results.json").read_text())
    med = statistics.median
    def select(mode, n=32, period=1, batch=64, delay=0):
        return [x for x in r["timings"] if x["mode"] == mode and x["nodes_per_request"] == n
                and x["period_ms"] == period and x["batch_size"] == batch and x["injected_delay_ms"] == delay]
    def latency(xs, q):
        return med(x["request_end_us"][q] for x in xs)
    def ready(xs, ms):
        return sum(x["ready_after_return"][str(ms)] for x in xs) / len(xs)
    def drop(xs):
        return sum(x["dropped"] for x in xs) / sum(x["requests"] * x["nodes_per_request"] for x in xs)
    sync, async_ = select("sync"), select("async")
    lines = ["# 异步 Prediction Worker 实验报告", "",
             "实验目录：`/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/async_exp`。", "",
             "## 结论与实验范围", "",
             f"这轮 CPU 机制实验支持 request-end → enqueue → return：32 node/request、每 1ms 注入一批时，同步主线程 p50 为 {latency(sync, 'p50'):.2f}µs，异步为 {latency(async_, 'p50'):.2f}µs，下降 {(1-latency(async_, 'p50')/latency(sync, 'p50'))*100:.1f}%。",
             "预测变慢或队列满时主线程继续返回，代价是预测未就绪和 LRU 回退；它并不保证 worker 永远跟得上。",
             "排序收益不一致：Full 的 shadow regret 改善，SWA 的 token regret 变差，不能据此宣布 NN eviction 整体优于 LRU。", "",
             "**这不是在线 SGLang A/B，也不是 stateful KV cache replay。没有运行真实 decode，没有测 TTFT、吞吐或 KV hit rate。** 主线程延迟是 Python 原型的 episode 快照/入队路径开销，不包含真实 radix 状态维护与 feature 原始元数据采集。",
             "现有 trace 只有 eviction frontier 快照，没有完整 unlock lifecycle；所以这里的入队时刻和间隔是受控构造，不冒充真实 request-end。", "",
             "## 沿用的历史成果", "",
             "参考项目任务《mlp探讨与初步设计》《feature选取》，使用 Frozen frontier 和已有 Unified K=10 模型。", "",
             f"- checkpoint：`{r['checkpoint']}`，单个 seed=42，16→64→32→10，共 3,498 参数。",
             f"- trace：`{r['trace']}`。只选一个 TP rank，避免重复统计。",
             f"- {r['frontiers']} 次 frontier，{r['candidate_exposures']:,} 个候选 exposure，最后 cache-access event={r['end_event']}。",
             "- 10 桶单位仍是 cache-access events：(0,1]、(1,2]、(2,5]、(5,10]、(10,20]、(20,50]、(50,100]、(100,200]、(200,500]、(500,+∞)。",
             "- checkpoint 输出 softmax 概率；转成前 9 个有限桶的条件 hazard，以分段常数 hazard 计算复用概率 1−S(age+H)/S(age)。超过 500 events 没有尾部 rate 定义，直接 LRU，不臆造尾部。",
             "- 这验证了插值实现，没有新增证据证明 eviction-snapshot 模型可直接用于 unlock 时刻。秒级模型仍需秒级 lifecycle 标签。", "",
             "## 原型行为", "",
             "`predictor.py` 提供 Node、episode Ticket、有界 Queue、Prediction Worker 与 choose_candidate。主线程复制平坦原始元数据快照，worker 构造 16 维 feature、标准化、批量推理并发布不可变 Result。",
             "node 每次重新进入 episode、被重新引用、删除或结构变化时，由 serving owner 替换/失效 ticket；worker 只发布到收到的 ticket，因此旧计算不会覆盖新 episode。此接口尚未接到真实 SGLang lifecycle hook。",
             "队列使用 put_nowait；其短 mutex 只保护队列操作，不包住 feature 构造或 MLP。worker 不等待凑满 batch，只取当时可用项；最大 batch 默认 64。队列满则丢弃该次预测。",
             "eviction 输入是已经合法、按 LRU 排列的 shortlist；全部结果有效时向量化插值并选择最低概率，否则选第一个 LRU。没有 queue.join、worker.join 或 MLP 调用。join 只发生在测量结束后的清理。",
             "CPU Python/GIL、对象分配与 OS 调度仍会带来干扰，因此这是不等待推理的控制流保证，不是主线程硬实时延迟保证。", "",
             "## 实验 A：正常负载主线程开销", "",
             "每个配置 300 个合成 request-end，3 次重复（41/42/43 控制 feature 采样，模型固定 seed=42）。每次重复打乱策略执行顺序；表中 p50/p99 是三次对应分位数的中位数，并非合并后的分位数。OMP/MKL/OpenBLAS/PyTorch 都限制为单计算线程。", "",
             "| node/request | 同步 p50 µs | 异步 p50 µs | 同步 p99 µs | 异步 p99 µs | 异步 1ms 就绪率 | 丢弃率 |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for n in (1, 8, 32, 128):
        s, a = select("sync", n), select("async", n)
        lines.append(f"| {n} | {latency(s, 'p50'):.2f} | {latency(a, 'p50'):.2f} | {latency(s, 'p99'):.2f} | {latency(a, 'p99'):.2f} | {ready(a, 1):.2%} | {drop(a):.2%} |")
    lines += ["", "就绪率分母包含被丢弃的 node；时间从该次 request-end 返回之后算，不在 serving 内等待。128 node/ms 已超过这个 Python worker 的处理能力，不能把低入队延迟理解成高预测覆盖率。",
              "LRU 计时基线只是没有预测工作的空路径，不是实际 LRU eviction 端到端延迟。", "",
              "## 实验 B：慢推理与队列过载", "",
              "32 node/request、1ms 间隔；有延迟时 queue capacity=256，无额外延迟时 capacity=4096。延迟为每个 inference batch 的 sleep 注入，不模拟 CPU 忙算。", "",
              "| 额外 batch 延迟 | 同步 p50 µs | 异步 p50 µs | 异步 p99 µs | 5ms 就绪率 | 丢弃率 |",
              "|---:|---:|---:|---:|---:|---:|"]
    for d in (0, 1, 10):
        s, a = select("sync", delay=d), select("async", delay=d)
        lines.append(f"| {d}ms | {latency(s,'p50'):.2f} | {latency(a,'p50'):.2f} | {latency(a,'p99'):.2f} | {ready(a,5):.2%} | {drop(a):.2%} |")
    a = select("async", period=0)
    lines += ["", f"无间隔 burst、capacity=256 时，异步 p50={latency(a,'p50'):.2f}µs，丢弃率={drop(a):.2%}。此测试证明队列过载时返回，不证明 burst 中仍能获得预测收益。", "",
              "## 实验 C：batch 上限", "",
              "32 node/request、1ms 间隔。这里是可用项即时合批，不设置额外 batch 等待窗口。", "",
              "| 最大 batch | 主线程 p50 µs | 1ms node 就绪率 | 5ms node 就绪率 | 丢弃率 |",
              "|---:|---:|---:|---:|---:|"]
    for batch in (1, 16, 64, 128):
        a = select("async", batch=batch)
        lines.append(f"| {batch} | {latency(a,'p50'):.2f} | {ready(a,1):.2%} | {ready(a,5):.2%} | {drop(a):.2%} |")
    lines += ["", "batch=1 明显容易积压；16/64/128 在此负载下更合适。这不是最优 batch 的普适结论，结果受快照 Python 开销和任务调度影响。", "",
              "## 实验 D：eviction 读取与插值", "",
              "预先构造合法 shortlist，无并发 worker；每项 3,000 次调用。包含有效性检查、NumPy 插值和 argmin，不含候选枚举、释放 KV 或 TP 通信。", "",
              "| 候选数 | pending/LRU p50 µs | ready/插值 p50 µs | ready p99 µs |",
              "|---:|---:|---:|---:|"]
    for n in (1, 8, 16, 32, 64, 128):
        get = lambda state: next(x["latency"] for x in extra["eviction_us"] if x["nodes"] == n and x["state"] == state)
        lines.append(f"| {n} | {get('pending')['p50']:.2f} | {get('ready')['p50']:.2f} | {get('ready')['p99']:.2f} |")
    lines += ["", "现场插值无需后台更新，但也不是零成本。若一个 eviction 连续释放很多 node，应避免每选一个 victim 都重复转换整个 shortlist。", "",
              "## 实验 E：真实 frontier 的 held-out shadow 排序", "",
              "沿用训练代码的 digest test split（hash bucket≥85），各 Full/SWA snapshot 取最老的最多 16 个 test candidate，至少两个才评估；只保留距 trace 末尾至少 100 events 的时刻。不是独立 workload，也不按 exposure 做独立显著性检验。",
              "每个 snapshot 只假设选一个 victim，评分为未来 20 events reuse probability。node regret 是选中 node 后 20 events 内出现 demand 的比例；token regret 是这些 node 的 token 占全部选中 token 的比例。它们不是实测 cache hit rate。", "",
              "| Frontier | 决策数 | LRU node regret | MLP node regret | LRU token regret | MLP token regret |",
              "|---|---:|---:|---:|---:|---:|"]
    for kind in ("full", "swa"):
        s = r["shadow"]["results"][kind]
        l, m = s["lru"], s["sync"]
        lines.append(f"| {kind} | {l['decisions']} | {l['soon_reuse_node_20']:.2%} | {m['soon_reuse_node_20']:.2%} | {l['soon_reuse_token_20']:.2%} | {m['soon_reuse_token_20']:.2%} |")
    lines += ["", "异步另开实际 worker，用 1ms 的受控 snapshot 间隔提交，记录完成时间，回溯在指定 deadline 是否可用。deadline 不是主动 sleep 等待预测，也不是从原始 trace 测得的 unlock-to-eviction 时间。异步排序读取 worker 实际输出，并与同步输出做数值一致性检查。", "",
              "| 返回后的假设 eviction 时刻 | Full 整组就绪 | SWA 整组就绪 |",
              "|---:|---:|---:|"]
    for d in (0, 0.1, 0.5, 1, 5):
        f = r["shadow"]["results"]["full"][f"async_{d}ms"]["mlp_used_fraction"]
        s = r["shadow"]["results"]["swa"][f"async_{d}ms"]["mlp_used_fraction"]
        lines.append(f"| {d}ms | {f:.2%} | {s:.2%} |")
    lines += ["", "## 补充：相同最小释放 token 预算", "",
              "每组以 LRU 首个 node 的 token 数为最小目标。MLP 按分数依次选，直到达到这个相同目标；node 不可拆分，允许超额，完整报告超额量。仍然只在固定 frontier 上选，不模拟树变化和后续缓存轨迹。", "",
              "| Frontier | LRU regret tokens | MLP regret tokens | LRU regret/释放 | MLP regret/释放 | MLP 超额释放 |",
              "|---|---:|---:|---:|---:|---:|"]
    for kind in ("full", "swa"):
        s = extra["equal_minimum_tokens_shadow"][kind]
        l, m = s["lru"], s["mlp"]
        lines.append(f"| {kind} | {l['regret']:,} | {m['regret']:,} | {l['regret_per_freed']:.2%} | {m['regret_per_freed']:.2%} | {m['excess_fraction']:.2%} |")
    lines += ["", "Full 仍改善，SWA 仍未改善，并有更多超额释放。当前简单 P(reuse) 排序不能保证 token/byte 成本收益，尤其不能从 node regret 的下降直接推导 KV 命中率提升。", "",
              "## 正确性与下一步边界", "",
              "并发测试用事件屏障将 worker 卡在 inference 内，确认入队、队列满返回、eviction/LRU 读取均已返回；随后重新创建同一 node episode，释放屏障，确认旧预测不会被读取。另验证 feature 快照不可被外部原字典修改、失效后不可读，以及条件 hazard 插值和未定义尾部回退。", "",
              "在线接入仍需：完整的 add/split/re-lock/unlock/delete 生命周期维护；Full/SWA 分开的合法性与 episode；秒级 unlock 数据；TP rank 一致的 victim 选择。现有部署 TP=8，如果各 rank 按自己的异步完成时刻独立决策，可能选出不同 victim，不能直接把当前单进程原型挂上去。",
              "可行方向是在既有调度通信中分发统一决策或统一可用预测版本，并测这部分额外开销；本轮未实现或验证。", "",
              "原型验证的是异步机制与静态排序效果。要回答真正的命中率/TTFT收益，仍需后续在线 A/B 或完整 stateful replay。", "",
              "## 复现与原始结果", "",
              "在目标目录运行 `bash run_all.sh <新的run目录名>`。脚本只使用 CPU，不改共享 SGLang 安装。",
              "- `predictor.py`：原型实现。",
              "- `test_predictor.py`：确定性并发与插值测试。",
              "- `run_experiment.py`：三次重复 timing 与 shadow 排序。",
              "- `additional_experiment.py`：eviction 开销与最小预算对照。",
              "- `runs/20260912_v1/results.json`、`additional_results.json`：完整测量。",
              "- `shadow_decisions.jsonl`、`equal_minimum_tokens_decisions.jsonl`：逐决策记录。",
              "- `source_sha256.json`：最终源文件 hashes；模型/trace hashes 和运行环境已记录在 results.json。", ""]
    (args.run / "report_zh.md").write_text("\n".join(lines), encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in Path(__file__).parent.glob("*.py")}
    (args.run / "source_sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(args.run / "report_zh.md")


if __name__ == "__main__":
    main()
