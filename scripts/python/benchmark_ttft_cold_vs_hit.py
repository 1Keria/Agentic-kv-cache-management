#!/usr/bin/env python3
"""Measure how cross-request prefix hits translate into TTFT.

For each requested prefix length, the benchmark compares the same probe under:

1. cold: flush radix cache, then issue the probe;
2. hit: flush radix cache, warm the shared prefix with a different request,
   then issue the probe.

The two requests represent different sessions by construction: they share only
the system prefix and have different user tails. This is a controlled
mechanism-level microbenchmark; it does not yet model cache pressure, eviction,
or a production arrival process.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

import requests
from openai import AsyncOpenAI
from transformers import AutoTokenizer


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOKENIZER = Path(
    "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/"
    "exp_f01_cross_session_ttft/run_1.json"
)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * q)
    return round(ordered[index], 3)


def summarize(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
            "stdev": None,
        }
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": round(max(values), 3),
        "mean": round(statistics.mean(values), 3),
        "stdev": (
            round(statistics.stdev(values), 3) if len(values) > 1 else 0.0
        ),
    }


def make_exact_token_text(
    tokenizer: Any, target_tokens: int, seed: int
) -> str:
    if target_tokens <= 0:
        return ""
    bases = [
        "Shared agent instructions and tool documentation remain stable. ",
        "Repository analysis requires careful inspection and verification. ",
        "The serving system should preserve reusable prefix state safely. ",
        "Cache management decisions must remain bounded and reversible. ",
    ]
    base = bases[seed % len(bases)]
    repeats = max(2, target_tokens // max(1, len(tokenizer.encode(base))) + 2)
    text = base * repeats
    ids = tokenizer.encode(text, add_special_tokens=False)[:target_tokens]
    decoded = tokenizer.decode(ids)
    encoded = tokenizer.encode(decoded, add_special_tokens=False)
    while len(encoded) < target_tokens:
        decoded += base
        encoded = tokenizer.encode(decoded, add_special_tokens=False)
    if len(encoded) != target_tokens:
        decoded = tokenizer.decode(encoded[:target_tokens])
        encoded = tokenizer.encode(decoded, add_special_tokens=False)
    if len(encoded) != target_tokens:
        raise ValueError(
            f"Could not construct stable {target_tokens}-token text; "
            f"got {len(encoded)}"
        )
    return decoded


def flush_cache(server_url: str) -> dict[str, Any]:
    response = requests.post(f"{server_url}/flush_cache", timeout=30)
    response.raise_for_status()
    try:
        payload = response.json()
    except requests.JSONDecodeError:
        payload = {"text": response.text}
    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(f"flush_cache failed: {payload}")
    return payload


def health_check(server_url: str) -> None:
    response = requests.get(f"{server_url}/health", timeout=10)
    response.raise_for_status()


async def measure_request(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, str]],
    label: str,
    max_tokens: int,
    priority: int | None = None,
) -> dict[str, Any]:
    started_ns = time.perf_counter_ns()
    first_token_ns: int | None = None
    prompt_tokens = 0
    cached_tokens = 0
    completion_tokens = 0
    output_parts: list[str] = []

    extra_body = {"priority": priority} if priority is not None else None
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=extra_body,
    )
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            content = delta.content or ""
            reasoning = getattr(delta, "reasoning_content", None) or ""
            visible = reasoning or content
            if visible and first_token_ns is None:
                first_token_ns = time.perf_counter_ns()
            if visible:
                output_parts.append(visible)
        if chunk.usage is not None:
            prompt_tokens = chunk.usage.prompt_tokens or 0
            completion_tokens = chunk.usage.completion_tokens or 0
            details = chunk.usage.prompt_tokens_details
            if details is not None:
                cached_tokens = details.cached_tokens or 0

    ended_ns = time.perf_counter_ns()
    return {
        "label": label,
        "ttft_ms": (
            round((first_token_ns - started_ns) / 1_000_000, 3)
            if first_token_ns is not None
            else None
        ),
        "total_ms": round((ended_ns - started_ns) / 1_000_000, 3),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "uncached_tokens": max(0, prompt_tokens - cached_tokens),
        "completion_tokens": completion_tokens,
        "priority": priority,
        "output_preview": "".join(output_parts)[:80],
    }


def make_messages(prefix: str, tail: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prefix},
        {"role": "user", "content": tail},
    ]


async def run_condition(
    client: AsyncOpenAI,
    server_url: str,
    model: str,
    prefix: str,
    warm_tail: str,
    probe_tail: str,
    prefix_tokens: int,
    round_index: int,
    max_tokens: int,
) -> dict[str, Any]:
    flush_cache(server_url)
    cold = await measure_request(
        client,
        model,
        make_messages(prefix, probe_tail),
        f"p{prefix_tokens}-r{round_index}-cold",
        max_tokens,
    )

    flush_cache(server_url)
    warm = await measure_request(
        client,
        model,
        make_messages(prefix, warm_tail),
        f"p{prefix_tokens}-r{round_index}-warm",
        max_tokens,
    )
    hit = await measure_request(
        client,
        model,
        make_messages(prefix, probe_tail),
        f"p{prefix_tokens}-r{round_index}-hit",
        max_tokens,
    )

    if cold["ttft_ms"] is None or hit["ttft_ms"] is None:
        raise RuntimeError("A request completed without a measurable first token")
    return {
        "round": round_index,
        "cold": cold,
        "warm": warm,
        "hit": hit,
        "paired_ttft_saving_ms": round(
            cold["ttft_ms"] - hit["ttft_ms"], 3
        ),
        "paired_ttft_reduction_pct": round(
            100 * (cold["ttft_ms"] - hit["ttft_ms"]) / cold["ttft_ms"],
            3,
        ),
    }


def summarize_prefix(
    prefix_tokens: int,
    rounds: list[dict[str, Any]],
    slo_thresholds_ms: list[float],
) -> dict[str, Any]:
    cold_ttft = [row["cold"]["ttft_ms"] for row in rounds]
    hit_ttft = [row["hit"]["ttft_ms"] for row in rounds]
    savings = [row["paired_ttft_saving_ms"] for row in rounds]
    reductions = [row["paired_ttft_reduction_pct"] for row in rounds]
    cached = [row["hit"]["cached_tokens"] for row in rounds]
    cold_cached = [row["cold"]["cached_tokens"] for row in rounds]
    return {
        "prefix_content_tokens": prefix_tokens,
        "rounds": len(rounds),
        "cold_ttft_ms": summarize(cold_ttft),
        "hit_ttft_ms": summarize(hit_ttft),
        "paired_ttft_saving_ms": summarize(savings),
        "paired_ttft_reduction_pct": summarize(reductions),
        "cold_cached_tokens": summarize(cold_cached),
        "hit_cached_tokens": summarize(cached),
        "median_cached_tokens_per_requested_prefix_token": round(
            statistics.median(cached) / prefix_tokens, 4
        ),
        "slo_violation_rates_pct": {
            str(threshold): {
                "cold": round(
                    100
                    * sum(value > threshold for value in cold_ttft)
                    / len(cold_ttft),
                    3,
                ),
                "hit": round(
                    100
                    * sum(value > threshold for value in hit_ttft)
                    / len(hit_ttft),
                    3,
                ),
            }
            for threshold in slo_thresholds_ms
        },
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    health_check(args.server_url)
    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True
    )
    client = AsyncOpenAI(
        base_url=f"{args.server_url}/v1",
        api_key="dummy",
        timeout=args.request_timeout,
    )

    tiny_prefix = make_exact_token_text(tokenizer, 32, seed=0)
    tiny_tail = make_exact_token_text(tokenizer, 32, seed=1)
    await measure_request(
        client,
        args.model,
        make_messages(tiny_prefix, tiny_tail),
        "model-warmup",
        args.max_tokens,
    )
    flush_cache(args.server_url)

    all_results: dict[str, Any] = {}
    raw_rounds: dict[str, list[dict[str, Any]]] = {}
    for prefix_tokens in args.prefix_tokens:
        print(f"Benchmarking prefix={prefix_tokens} tokens", flush=True)
        prefix = make_exact_token_text(tokenizer, prefix_tokens, seed=2)
        warm_tail = make_exact_token_text(
            tokenizer, args.tail_tokens, seed=0
        )
        probe_tail = make_exact_token_text(
            tokenizer, args.tail_tokens, seed=1
        )

        # Prime length-dependent kernels and discard this round.
        await run_condition(
            client,
            args.server_url,
            args.model,
            prefix,
            warm_tail,
            probe_tail,
            prefix_tokens,
            -1,
            args.max_tokens,
        )

        rounds = []
        for round_index in range(args.rounds):
            result = await run_condition(
                client,
                args.server_url,
                args.model,
                prefix,
                warm_tail,
                probe_tail,
                prefix_tokens,
                round_index,
                args.max_tokens,
            )
            rounds.append(result)
            print(
                f"  round={round_index} "
                f"cold={result['cold']['ttft_ms']:.1f}ms "
                f"hit={result['hit']['ttft_ms']:.1f}ms "
                f"cached={result['hit']['cached_tokens']}",
                flush=True,
            )
        key = str(prefix_tokens)
        raw_rounds[key] = rounds
        all_results[key] = summarize_prefix(
            prefix_tokens, rounds, args.slo_thresholds_ms
        )

    return {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "configuration": {
            "server_url": args.server_url,
            "model": args.model,
            "tokenizer_path": str(args.tokenizer_path),
            "tokenizer_class": type(tokenizer).__name__,
            "chat_template_sha256": hashlib.sha256(
                (tokenizer.chat_template or "").encode()
            ).hexdigest(),
            "prefix_content_tokens": args.prefix_tokens,
            "tail_content_tokens": args.tail_tokens,
            "rounds": args.rounds,
            "discarded_warmup_rounds_per_length": 1,
            "max_tokens": args.max_tokens,
            "slo_thresholds_ms": args.slo_thresholds_ms,
        },
        "summary_by_prefix": all_results,
        "raw_rounds_by_prefix": raw_rounds,
        "limitations": [
            (
                "This is a single-request, no-queue microbenchmark; it measures "
                "prefill-to-TTFT conversion, not production tail latency."
            ),
            (
                "flush_cache creates controlled cold/hit states and does not "
                "represent natural eviction under capacity pressure."
            ),
            (
                "Synthetic text controls prefix length; a follow-up should "
                "replay the measured 7.8K real OpenHands prefix."
            ),
            (
                "The warm and probe calls are distinct requests but do not rely "
                "on a session_id API; content identity drives radix reuse."
            ),
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="Qwen3-8B")
    parser.add_argument(
        "--tokenizer-path", type=Path, default=DEFAULT_TOKENIZER
    )
    parser.add_argument(
        "--prefix-tokens",
        type=int,
        nargs="+",
        default=[1024, 4096, 7808],
    )
    parser.add_argument("--tail-tokens", type=int, default=128)
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument(
        "--slo-thresholds-ms",
        type=float,
        nargs="+",
        default=[100.0, 200.0, 500.0],
    )
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if any(value <= 0 for value in args.prefix_tokens):
        raise ValueError("--prefix-tokens values must be positive")
    if args.rounds < 2:
        raise ValueError("--rounds must be at least 2")
    result = asyncio.run(benchmark(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
