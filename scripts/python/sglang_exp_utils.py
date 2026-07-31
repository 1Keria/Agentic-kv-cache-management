#!/usr/bin/env python3
"""SGLang 实验公共工具函数

基于 exp_utils.py 改写，适配 SGLang 的 API 差异。
"""

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
EXPERIMENT_DIR = "/share/dai-sys/zhoulongsheng/agentkv/experiments/sglang_kv_cache"
BLOCK_SIZE = 1  # SGLang uses token-level matching (page_size=1)

# Load real prompts
REAL_PROMPTS_PATH = os.path.join(
    "/share/dai-sys/zhoulongsheng/agentkv/experiments/vllm_kv_cache",
    "real_prompts", "real_prompts.json"
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

_real_prompts_cache = None

def load_real_prompts():
    global _real_prompts_cache
    if _real_prompts_cache is not None:
        return _real_prompts_cache
    if not os.path.exists(REAL_PROMPTS_PATH):
        print(f"Warning: real prompts not found at {REAL_PROMPTS_PATH}")
        return {}
    with open(REAL_PROMPTS_PATH, "r") as f:
        _real_prompts_cache = json.load(f)
    print(f"Loaded real prompts: {list(_real_prompts_cache.keys())}")
    return _real_prompts_cache


def get_real_session_prompt(repo, turn=0):
    prompts = load_real_prompts()
    if repo not in prompts:
        return None
    turns = prompts[repo]["turns"]
    if turn >= len(turns):
        return None
    return turns[turn]["messages"]


def make_text_with_token_count(target_tokens, seed=0):
    """Generate text with exactly target_tokens tokens (same as vLLM exp_utils)"""
    bases = [
        "The quick brown fox jumps over the lazy dog. ",
        "A stitch in time saves nine and prevents future issues. ",
        "To be or not to be that is the question we must answer. ",
        "All that glitters is not gold but sometimes it shines bright. ",
    ]
    base = bases[seed % len(bases)]
    text = ""
    while len(tokenizer.encode(text)) < target_tokens:
        text += base
    token_ids = tokenizer.encode(text)[:target_tokens]
    return tokenizer.decode(token_ids)


def make_messages(prefix_text, unique_text):
    return [
        {"role": "system", "content": prefix_text},
        {"role": "user", "content": unique_text},
    ]


def get_prometheus_metrics():
    """Fetch Prometheus metrics from SGLang server"""
    try:
        resp = requests.get("http://localhost:8000/metrics", timeout=5)
        text = resp.text
    except Exception as e:
        print(f"Warning: failed to fetch SGLang metrics: {e}")
        return {}

    metrics = {}
    target_keys = [
        "sglang:cached_tokens_total",
        "sglang:max_total_num_tokens",
        "sglang:num_running_reqs",
        "sglang:num_queue_reqs",
        "sglang:prompt_tokens_total",
        "sglang:generation_tokens_total",
    ]

    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        for key in target_keys:
            if key in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        metrics[parts[0]] = float(parts[1])
                    except ValueError:
                        pass

    return metrics


async def send_and_record(messages, label, max_tokens=50, timeline=None):
    """Send request and record metrics (SGLang version)"""
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
        if first_token_time is None and chunk.choices and chunk.choices[0].delta.content:
            first_token_time = time.time()
            response_text += chunk.choices[0].delta.content
        elif chunk.choices and chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content

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
    }

    if timeline:
        timeline.record_event("req_end", label, extra={
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
        })

    return result


def save_run(exp_name, run_id, data, suffix=""):
    exp_dir = os.path.join(EXPERIMENT_DIR, exp_name)
    os.makedirs(exp_dir, exist_ok=True)
    if suffix:
        path = os.path.join(exp_dir, f"run_{run_id}_{suffix}.json")
    else:
        path = os.path.join(exp_dir, f"run_{run_id}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")
