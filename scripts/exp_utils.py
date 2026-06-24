# vLLM KV Cache 实验公共工具

import asyncio
import time
import json
import os
import requests
from datetime import datetime
from openai import AsyncOpenAI
from transformers import AutoTokenizer

MODEL_PATH = "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"
BASE_URL = "http://localhost:8000/v1"
EXPERIMENT_DIR = "/share/dai-sys/zhoulongsheng/agentkv/experiments/vllm_kv_cache"
BLOCK_SIZE = 16
REAL_PROMPTS_PATH = os.path.join(EXPERIMENT_DIR, "real_prompts", "real_prompts.json")

# 初始化 tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

# ---------------------------------------------------------------------------
# 真实 Agent prompt 数据加载
# ---------------------------------------------------------------------------

# 缓存真实 prompt 数据
_real_prompts_cache = None


def load_real_prompts() -> dict:
    """加载 LMCache agentic traces 提取的真实 prompt 数据

    返回格式:
        {
            "django": {"session_id": "...", "turns": [{"turn": 0, "messages": [...], "total_tokens": 10056}, ...]},
            "sympy": {...},
            ...
        }
    """
    global _real_prompts_cache
    if _real_prompts_cache is not None:
        return _real_prompts_cache

    if not os.path.exists(REAL_PROMPTS_PATH):
        print(f"Warning: real prompts not found at {REAL_PROMPTS_PATH}, will use synthetic text")
        return {}

    with open(REAL_PROMPTS_PATH, "r") as f:
        _real_prompts_cache = json.load(f)
    print(f"Loaded real prompts from {REAL_PROMPTS_PATH}: {list(_real_prompts_cache.keys())}")
    return _real_prompts_cache


def get_real_session_prompt(repo: str, turn: int = 0) -> list[dict] | None:
    """获取指定 repo 的真实 agent session prompt

    Args:
        repo: repo 名称，如 "django", "sympy", "scikit-learn", "astropy", "matplotlib"
        turn: 第几轮对话 (0=首轮)

    Returns:
        OpenAI 格式的 messages 列表，或 None（如果数据不可用）
    """
    prompts = load_real_prompts()
    if repo not in prompts:
        return None
    turns = prompts[repo]["turns"]
    if turn >= len(turns):
        return None
    return turns[turn]["messages"]


def get_real_l0_text() -> str | None:
    """获取真实的 L0 (system prompt) 文本

    所有 repo 的 system prompt 相同（OpenHands agent system prompt），
    约 6163 tokens。
    """
    prompts = load_real_prompts()
    for repo, data in prompts.items():
        if data["turns"]:
            for msg in data["turns"][0]["messages"]:
                if msg["role"] == "system":
                    return msg["content"]
    return None


def get_real_l1_text(repo: str) -> str | None:
    """获取指定 repo 的 L1 文本（首轮请求中 system 之后的 user messages）

    Args:
        repo: repo 名称

    Returns:
        L1 文本（多条 user message 拼接），或 None
    """
    prompts = load_real_prompts()
    if repo not in prompts:
        return None
    turns = prompts[repo]["turns"]
    if not turns:
        return None
    # 首轮请求中，system 之后、最后一条 user message 之前的所有内容构成 L1
    messages = turns[0]["messages"]
    l1_parts = []
    found_system = False
    user_count = 0
    for msg in messages:
        if msg["role"] == "system":
            found_system = True
            continue
        if found_system and msg["role"] == "user":
            user_count += 1
            if user_count < len([m for m in messages if m["role"] == "user"]):
                # 不是最后一条 user message → 属于 L1
                l1_parts.append(msg["content"])
    return "\n".join(l1_parts) if l1_parts else None


def make_layered_messages(l0: str, l1: str, l2: str) -> list[dict]:
    """构造分层 Agent prompt (L0+L1 合并为 system, L2 作为 user)

    这模拟了 Agent 场景中的 L0/L1/L2 层次结构：
    - L0 (全局共享): system prompt + tool schema
    - L1 (项目级): CLAUDE.md / README / project context
    - L2 (session 级): problem statement / task

    在 OpenAI API 格式中，L0+L1 合并为 system message，L2 作为 user message。
    这样 vLLM APC 可以在 block level 匹配共享前缀。

    Args:
        l0: L0 全局前缀文本
        l1: L1 项目级前缀文本
        l2: L2 session 级内容

    Returns:
        OpenAI 格式的 messages 列表
    """
    return [
        {"role": "system", "content": l0 + "\n" + l1},
        {"role": "user", "content": l2},
    ]


def make_text_with_token_count(target_tokens: int, seed: int = 0) -> str:
    """构造精确 target_tokens 个 token 的文本

    通过逐步追加基础文本直到 token 数 >= target，然后精确截断。
    不同 seed 产生不同的文本，用于区分不同请求。

    注意：由于 BPE tokenizer 的 decode→encode 不完全可逆，截断后的文本
    再次 encode 时可能产生略少的 token。本函数通过先追加到超过目标再截断
    的方式确保最终文本的 token 数精确等于 target_tokens。
    """
    bases = [
        "The quick brown fox jumps over the lazy dog. ",
        "A stitch in time saves nine and prevents future issues. ",
        "To be or not to be that is the question we must answer. ",
        "All that glitters is not gold but sometimes it shines bright. ",
    ]
    base = bases[seed % len(bases)]
    # 逐步追加直到 token 数 >= target
    text = ""
    while len(tokenizer.encode(text)) < target_tokens:
        text += base
    # 精确截断到目标 token 数
    token_ids = tokenizer.encode(text)[:target_tokens]
    return tokenizer.decode(token_ids)


def make_messages(prefix_text: str, unique_text: str):
    """构造 OpenAI 格式的 messages 列表"""
    return [
        {"role": "system", "content": prefix_text},
        {"role": "user", "content": unique_text},
    ]


# ---------------------------------------------------------------------------
# Prometheus 指标采集（必须在 KVTimelineCollector 之前定义）
# ---------------------------------------------------------------------------

def get_prometheus_metrics():
    """从 /metrics endpoint 采集关键 KV cache 指标

    返回:
        dict: 指标名 -> 值（仅提取 KV cache 相关指标）
    """
    try:
        resp = requests.get("http://localhost:8000/metrics", timeout=5)
        text = resp.text
    except Exception as e:
        print(f"Warning: failed to fetch Prometheus metrics: {e}")
        return {}

    metrics = {}
    # 需要采集的指标列表（完整覆盖 KV cache 生命周期）
    target_keys = [
        # Prefix cache 命中
        "prefix_cache_queries",
        "prefix_cache_hits",
        "external_prefix_cache_queries",
        "external_prefix_cache_hits",
        # Token 计数
        "prompt_tokens_cached",
        "prompt_tokens_by_source",
        "request_prefill_kv_computed_tokens",
        # 抢占
        "num_preemptions",
        # KV offloading 传输量
        "kv_offload_load_bytes",
        "kv_offload_load_time",
        "kv_offload_store_bytes",
        "kv_offload_store_time",
        # KV offload stores 跳过
        "kv_offload_stores_skipped",
    ]

    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        for key in target_keys:
            if key in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # 累计指标用全名（含 label）
                        metrics[parts[0]] = float(parts[1])
                    except ValueError:
                        pass

    # 单独提取 gauge 指标
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        # kv_cache_usage_perc — GPU KV cache 使用百分比
        if "kv_cache_usage_perc" in line:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    metrics["kv_cache_usage_perc"] = float(parts[1])
                except ValueError:
                    pass
        # cache_config_info — 包含 num_gpu_blocks, num_cpu_blocks 等 label
        if "cache_config_info" in line:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    metrics["cache_config_info"] = float(parts[1])
                except ValueError:
                    pass

    return metrics


def compute_prometheus_delta(before: dict, after: dict) -> dict:
    """计算 Prometheus 累计指标的差值"""
    delta = {}
    for key in before:
        if key in after:
            delta[key] = after[key] - before[key]
    return delta


# ---------------------------------------------------------------------------
# Block 生命周期时间线采集器（必须在 send_and_record 之前定义）
# ---------------------------------------------------------------------------

class KVTimelineCollector:
    """Block 生命周期时间线采集器

    在实验运行期间后台持续采样 KV cache 相关指标，
    和请求事件对齐，产出完整的 KV cache 生命周期时间线。

    采集四个观测渠道的数据：
    ① cached_tokens — 通过 record_event 的 extra 参数传入（请求级）
    ② /metrics 指标 — 后台持续采样（全局聚合）
    ③ 无（DEBUG 日志需从 server 日志文件解析，见 parse_server_log）
    ④ 无（源码阅读需人工进行）

    使用方式：
        collector = KVTimelineCollector(interval=0.5)
        await collector.start()                 # 启动后台采样
        collector.record_event("req_start", "S1-T1")   # 记录请求事件
        ...
        collector.record_event("req_end", "S1-T1")
        timeline = await collector.stop()       # 停止采样，返回时间线数据

    产出数据格式：
        [
          {"t": 0.0,  "event": "collector_start", "gpu_usage": 0.0, ...},
          {"t": 0.5,  "event": "sample", "gpu_usage": 0.0, ...},
          {"t": 1.2,  "event": "req_start", "label": "S1-T1", "gpu_usage": 0.0, ...},
          {"t": 2.8,  "event": "req_end", "label": "S1-T1", "gpu_usage": 0.35, ...},
          ...
        ]
    """

    # 持续采样的指标 key 列表（从 /metrics 端点）
    METRIC_KEYS = [
        "kv_cache_usage_perc",             # GPU KV cache 使用百分比
        "prefix_cache_hits",               # Prefix cache 命中次数
        "prefix_cache_queries",            # Prefix cache 查询次数
        "num_preemptions",                 # 请求被 preempt 次数
        "kv_offload_store_bytes",          # GPU→CPU offload 传输量
        "kv_offload_load_bytes",           # CPU→GPU 恢复传输量
        "kv_offload_stores_skipped",       # 跳过的 offload 次数
        "request_prefill_kv_computed_tokens",  # prefill 需重算的 tokens
        "prompt_tokens_cached",            # 总 cached tokens
    ]

    def __init__(self, interval: float = 0.5):
        """初始化采集器

        Args:
            interval: 采样间隔（秒），默认 0.5s。太小会增加 /metrics 请求频率，
                      太大可能错过瞬态变化。
        """
        self.interval = interval
        self.timeline: list[dict] = []
        self._start_time: float = 0
        self._running: bool = False
        self._task: asyncio.Task | None = None
        self._prev_metrics: dict = {}  # 上一轮采样的累计指标，用于计算 delta

    def _elapsed(self) -> float:
        """从采集器启动到当前的秒数"""
        return round(time.time() - self._start_time, 3)

    def _extract_metrics(self, metrics: dict) -> dict:
        """从原始 metrics dict 中提取关注的关键指标，并计算累计指标的 delta"""
        result = {}
        for key in self.METRIC_KEYS:
            val = metrics.get(key)
            if val is not None:
                result[key] = val
        # 额外采集所有 offload 相关指标（可能有新指标不在列表中）
        for key in metrics:
            if "offload" in key and key not in result:
                result[key] = metrics[key]
        # 计算 delta（当前值 - 上一轮值）
        delta = {}
        for key in result:
            if key in self._prev_metrics:
                delta[f"delta_{key}"] = result[key] - self._prev_metrics[key]
        result.update(delta)
        self._prev_metrics = dict(result)  # 保存（不含 delta）
        return result

    def record_event(self, event: str, label: str = "", extra: dict | None = None):
        """记录一个事件点（请求开始/结束等），同时采集当前指标

        Args:
            event: 事件类型，如 "req_start", "req_end", "phase_start", "phase_end"
            label: 请求标签，如 "S1-T1"
            extra: 额外信息，如 {"prompt_tokens": 6500, "cached_tokens": 5000}
        """
        if not self._running:
            return
        metrics = get_prometheus_metrics()
        entry: dict = {
            "t": self._elapsed(),
            "event": event,
            "label": label,
        }
        entry.update(self._extract_metrics(metrics))
        if extra:
            entry.update(extra)
        self.timeline.append(entry)

    async def _sample_loop(self):
        """后台定时采样循环"""
        while self._running:
            metrics = get_prometheus_metrics()
            entry: dict = {
                "t": self._elapsed(),
                "event": "sample",
            }
            entry.update(self._extract_metrics(metrics))
            self.timeline.append(entry)
            await asyncio.sleep(self.interval)

    async def start(self):
        """启动后台采样"""
        self._start_time = time.time()
        self._running = True
        self.timeline = []
        self._prev_metrics = {}
        # 记录起始状态
        self.record_event("collector_start")
        self._task = asyncio.create_task(self._sample_loop())
        print(f"  KVTimelineCollector started (interval={self.interval}s, "
              f"metrics={len(self.METRIC_KEYS)} keys)")

    async def stop(self) -> list[dict]:
        """停止采样，返回时间线数据"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # 记录结束状态
        self.record_event("collector_end")
        print(f"  KVTimelineCollector stopped ({len(self.timeline)} entries)")
        return self.timeline


# ---------------------------------------------------------------------------
# 请求发送与记录（依赖上面的 KVTimelineCollector）
# ---------------------------------------------------------------------------

async def send_and_record(messages, label, max_tokens=50, timeline=None):
    """发送请求并记录完整指标（streaming 模式，精确测量 TTFT）

    Args:
        messages: OpenAI 格式的 messages 列表
        label: 请求标签（用于时间线对齐）
        max_tokens: 最大生成 token 数
        timeline: 可选的 KVTimelineCollector，自动记录请求开始/结束事件

    返回:
        dict: 包含 label, ttft_ms, total_ms, prompt_tokens, cached_tokens,
              hit_rate, completion_tokens, timestamp
    """
    if timeline:
        timeline.record_event("req_start", label)

    client = AsyncOpenAI(base_url=BASE_URL, api_key="dummy")
    start = time.time()
    first_token_time = None
    cached_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    response_text = ""

    stream = await client.chat.completions.create(
        model="Qwen3-8B",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
    )

    async for chunk in stream:
        # 记录 TTFT：首个有内容的 chunk
        if first_token_time is None and chunk.choices and chunk.choices[0].delta.content:
            first_token_time = time.time()
            response_text += chunk.choices[0].delta.content
        elif chunk.choices and chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content

        # 记录 usage（最后一个 chunk 包含完整 usage）
        if chunk.usage is not None:
            prompt_tokens = chunk.usage.prompt_tokens
            completion_tokens = chunk.usage.completion_tokens
            if (chunk.usage.prompt_tokens_details is not None
                    and chunk.usage.prompt_tokens_details.cached_tokens is not None):
                cached_tokens = chunk.usage.prompt_tokens_details.cached_tokens

    result = {
        "label": label,
        "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
        "total_ms": round((time.time() - start) * 1000, 1),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens > 0 else 0,
        "completion_tokens": completion_tokens,
        "response_preview": response_text[:100] if response_text else "",
        "timestamp": datetime.fromtimestamp(start).isoformat(),
    }

    if timeline:
        timeline.record_event("req_end", label, extra={
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "ttft_ms": result["ttft_ms"],
        })

    return result


# ---------------------------------------------------------------------------
# 数据保存与汇总
# ---------------------------------------------------------------------------

def save_run(exp_name: str, run_id: int, data: dict, suffix: str = ""):
    """保存单次运行数据到 JSON 文件

    Args:
        exp_name: 实验名（目录名）
        run_id: 运行编号
        data: 运行数据
        suffix: 可选后缀（如 "4.1", "4.5_on"），用于同一目录下区分子场景
    """
    exp_dir = os.path.join(EXPERIMENT_DIR, exp_name)
    os.makedirs(exp_dir, exist_ok=True)
    if suffix:
        path = os.path.join(exp_dir, f"run_{run_id}_{suffix}.json")
    else:
        path = os.path.join(exp_dir, f"run_{run_id}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")


def save_config():
    """保存实验环境配置"""
    config = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "model": "Qwen3-8B",
        "model_path": MODEL_PATH,
        "vllm_version": "0.8.5.dev0 (source)",
        "gpu": "NVIDIA H800 x 1",
        "gpu_memory_utilization": 0.3,
        "max_model_len": 32768,
        "enable_prefix_caching": True,
        "prefix_caching_hash_algo": "xxhash",
        "enable_prompt_tokens_details": True,
        "kv_cache_metrics": True,
        "kv_cache_metrics_sample": 1.0,
        "kv_cache_dtype": "auto (bf16)",
        "block_size": BLOCK_SIZE,
        "watermark": 0.02,
        "enable_chunked_prefill": True,
        "kv_offloading_size_gib": 8,
        "kv_offloading_backend": "native",
        "estimated_gpu_kv_capacity_tokens": 44000,
        "estimated_gpu_kv_capacity_gb": 6.0,
        "estimated_cpu_kv_capacity_tokens": 58667,
        "estimated_total_kv_capacity_tokens": 102667,
        "tensor_parallel_size": 1,
        "port": 8000,
    }
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)
    path = os.path.join(EXPERIMENT_DIR, "config.json")
    with open(path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"Config saved: {path}")


def summarize_runs(exp_name: str):
    """汇总多次运行数据到 summary.json"""
    exp_dir = os.path.join(EXPERIMENT_DIR, exp_name)
    runs = []
    for fname in sorted(os.listdir(exp_dir)):
        if fname.startswith("run_") and fname.endswith(".json"):
            with open(os.path.join(exp_dir, fname)) as f:
                runs.append(json.load(f))

    if not runs:
        print(f"No runs found for {exp_name}")
        return

    # 按 label 聚合每个请求的指标
    all_labels = set()
    for run in runs:
        for req in run.get("requests", []):
            all_labels.add(req["label"])

    aggregated = {}
    for label in sorted(all_labels):
        metrics = {"ttft_ms": [], "cached_tokens": [], "hit_rate": [], "prompt_tokens": [], "total_ms": []}
        for run in runs:
            for req in run.get("requests", []):
                if req["label"] == label:
                    for key in metrics:
                        if req.get(key) is not None:
                            metrics[key].append(req[key])

        agg = {}
        for key, values in metrics.items():
            if values:
                agg[key] = {
                    "mean": round(sum(values) / len(values), 2),
                    "std": round((sum((v - sum(values)/len(values))**2 for v in values) / len(values))**0.5, 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "count": len(values),
                }
        aggregated[label] = agg

    # 计算 TTFT 降低比例（如果 req1_cold 和 req2_warm 都存在）
    if "req1_cold" in aggregated and "req2_warm" in aggregated:
        cold_ttft = aggregated["req1_cold"]["ttft_ms"]["mean"]
        warm_ttft = aggregated["req2_warm"]["ttft_ms"]["mean"]
        if cold_ttft > 0:
            aggregated["ttft_reduction_pct"] = round((1 - warm_ttft / cold_ttft) * 100, 1)

    summary = {
        "experiment": exp_name,
        "num_runs": len(runs),
        "aggregated": aggregated,
        "timestamp": datetime.now().isoformat(),
    }

    path = os.path.join(exp_dir, "summary.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary saved: {path}")


async def wait_for_server(timeout=120):
    """等待 vLLM server 就绪"""
    client = AsyncOpenAI(base_url=BASE_URL, api_key="dummy")
    start = time.time()
    while time.time() - start < timeout:
        try:
            await client.models.list()
            print("Server is ready!")
            return True
        except Exception:
            await asyncio.sleep(2)
    print(f"Server not ready after {timeout}s")
    return False


# ---------------------------------------------------------------------------
# vLLM server 日志解析（观测渠道 ③：调度决策级）
# ---------------------------------------------------------------------------

def parse_server_log(log_path: str, start_time: float | None = None) -> list[dict]:
    """从 vLLM server 日志中提取调度决策事件

    适用于 server 以 --log-level debug 启动时的日志。

    Args:
        log_path: server 日志文件路径
        start_time: 实验开始时间戳（time.time()），用于计算相对时间。
                    如果为 None，使用日志中的绝对时间。

    Returns:
        list[dict]: 调度事件列表，每个事件包含：
            - t: 相对时间（秒）
            - event: 事件类型（preempt/swap_in/swap_out/evict/offload_store/offload_load/recompute）
            - detail: 事件详情（原始日志行截断）
            - raw: 完整日志行
    """
    # 关键词 → 事件类型映射
    KEYWORDS = {
        "preempt": "preempt",
        "Preempting": "preempt",
        "swap_in": "swap_in",
        "swap_out": "swap_out",
        "swapping": "swap",
        "evict": "evict",
        "eviction": "evict",
        "offload_store": "offload_store",
        "offload_load": "offload_load",
        "storing": "offload_store",
        "loading": "offload_load",
        "recompute": "recompute",
        "recomputing": "recompute",
    }

    events = []
    try:
        with open(log_path, "r", errors="ignore") as f:
            for line in f:
                for keyword, event_type in KEYWORDS.items():
                    if keyword in line:
                        # 提取时间戳（vLLM 日志格式：YYYY-MM-DD HH:MM:SS,mmm）
                        t = 0.0
                        if len(line) > 23:
                            try:
                                ts_str = line[:23].strip()
                                # 解析到秒级精度
                                from datetime import timezone
                                ts = datetime.fromisoformat(
                                    ts_str.replace(",", ".")
                                ).replace(tzinfo=timezone.utc).timestamp()
                                if start_time:
                                    t = round(ts - start_time, 3)
                                else:
                                    t = round(ts, 3)
                            except (ValueError, IndexError):
                                pass

                        events.append({
                            "t": t,
                            "event": event_type,
                            "detail": line.strip()[:200],
                            "raw": line.strip(),
                        })
                        break  # 一行只匹配一个事件类型
    except FileNotFoundError:
        print(f"Warning: server log not found: {log_path}")

    return events


def summarize_log_events(events: list[dict]) -> dict:
    """汇总日志事件统计

    Args:
        events: parse_server_log 的返回值

    Returns:
        dict: 各事件类型的计数和关键统计
    """
    summary = {}
    for e in events:
        etype = e["event"]
        if etype not in summary:
            summary[etype] = {"count": 0, "first_t": e["t"], "last_t": e["t"]}
        summary[etype]["count"] += 1
        summary[etype]["last_t"] = e["t"]

    return summary
