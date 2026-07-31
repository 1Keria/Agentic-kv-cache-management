#!/usr/bin/env python3
"""Measure 7.8K prefix hit/miss TTFT while competing prefills arrive."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from transformers import AutoTokenizer

from benchmark_ttft_cold_vs_hit import (
    DEFAULT_TOKENIZER,
    flush_cache,
    health_check,
    make_exact_token_text,
    make_messages,
    measure_request,
    summarize,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/"
    "exp_f01_cross_session_ttft_under_load/run_1.json"
)


def unique_noise_text(
    tokenizer: Any, target_tokens: int, index: int
) -> str:
    marker = (
        f"Unique competing request {index} "
        f"{hashlib.sha256(str(index).encode()).hexdigest()} "
    )
    body = make_exact_token_text(tokenizer, target_tokens, seed=index)
    return marker + body


async def run_batch(
    client: AsyncOpenAI,
    model: str,
    probe_messages: list[dict[str, str]],
    noise_messages: list[list[dict[str, str]]],
    label: str,
    max_tokens: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    probe_task = asyncio.create_task(
        measure_request(
            client, model, probe_messages, f"{label}-probe", max_tokens
        )
    )
    noise_tasks = [
        asyncio.create_task(
            measure_request(
                client,
                model,
                messages,
                f"{label}-noise-{index}",
                max_tokens,
            )
        )
        for index, messages in enumerate(noise_messages)
    ]
    probe = await probe_task
    noise = await asyncio.gather(*noise_tasks)
    return probe, noise


async def one_round(
    client: AsyncOpenAI,
    server_url: str,
    model: str,
    prefix: str,
    warm_tail: str,
    probe_tail: str,
    noise_messages: list[list[dict[str, str]]],
    concurrency: int,
    round_index: int,
    max_tokens: int,
) -> dict[str, Any]:
    probe_messages = make_messages(prefix, probe_tail)

    flush_cache(server_url)
    cold, cold_noise = await run_batch(
        client,
        model,
        probe_messages,
        noise_messages,
        f"c{concurrency}-r{round_index}-cold",
        max_tokens,
    )

    flush_cache(server_url)
    warm = await measure_request(
        client,
        model,
        make_messages(prefix, warm_tail),
        f"c{concurrency}-r{round_index}-warm",
        max_tokens,
    )
    hit, hit_noise = await run_batch(
        client,
        model,
        probe_messages,
        noise_messages,
        f"c{concurrency}-r{round_index}-hit",
        max_tokens,
    )
    if cold["ttft_ms"] is None or hit["ttft_ms"] is None:
        raise RuntimeError("Missing probe first-token timestamp")
    return {
        "round": round_index,
        "cold_probe": cold,
        "hit_probe": hit,
        "warm": warm,
        "cold_noise_ttft_ms": summarize(
            [
                row["ttft_ms"]
                for row in cold_noise
                if row["ttft_ms"] is not None
            ]
        ),
        "hit_noise_ttft_ms": summarize(
            [
                row["ttft_ms"]
                for row in hit_noise
                if row["ttft_ms"] is not None
            ]
        ),
        "paired_probe_ttft_saving_ms": round(
            cold["ttft_ms"] - hit["ttft_ms"], 3
        ),
        "paired_probe_ttft_reduction_pct": round(
            100 * (cold["ttft_ms"] - hit["ttft_ms"]) / cold["ttft_ms"],
            3,
        ),
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
        max_retries=0,
    )
    prefix = make_exact_token_text(
        tokenizer, args.prefix_tokens, seed=2
    )
    warm_tail = make_exact_token_text(
        tokenizer, args.tail_tokens, seed=0
    )
    probe_tail = make_exact_token_text(
        tokenizer, args.tail_tokens, seed=1
    )

    results: dict[str, Any] = {}
    for concurrency in args.noise_concurrency:
        noise_messages = [
            make_messages(
                unique_noise_text(tokenizer, args.noise_tokens, index),
                f"Answer noise request {index}.",
            )
            for index in range(concurrency)
        ]
        await one_round(
            client,
            args.server_url,
            args.model,
            prefix,
            warm_tail,
            probe_tail,
            noise_messages,
            concurrency,
            -1,
            args.max_tokens,
        )
        rounds = []
        print(f"noise_concurrency={concurrency}", flush=True)
        for round_index in range(args.rounds):
            row = await one_round(
                client,
                args.server_url,
                args.model,
                prefix,
                warm_tail,
                probe_tail,
                noise_messages,
                concurrency,
                round_index,
                args.max_tokens,
            )
            rounds.append(row)
            print(
                f"  round={round_index} "
                f"cold={row['cold_probe']['ttft_ms']:.1f}ms "
                f"hit={row['hit_probe']['ttft_ms']:.1f}ms "
                f"cached={row['hit_probe']['cached_tokens']}",
                flush=True,
            )
        cold = [row["cold_probe"]["ttft_ms"] for row in rounds]
        hit = [row["hit_probe"]["ttft_ms"] for row in rounds]
        savings = [
            row["paired_probe_ttft_saving_ms"] for row in rounds
        ]
        reductions = [
            row["paired_probe_ttft_reduction_pct"] for row in rounds
        ]
        results[str(concurrency)] = {
            "noise_concurrency": concurrency,
            "summary": {
                "cold_probe_ttft_ms": summarize(cold),
                "hit_probe_ttft_ms": summarize(hit),
                "paired_probe_ttft_saving_ms": summarize(savings),
                "paired_probe_ttft_reduction_pct": summarize(reductions),
                "hit_probe_cached_tokens": summarize(
                    [row["hit_probe"]["cached_tokens"] for row in rounds]
                ),
                "slo_violation_rates_pct": {
                    str(threshold): {
                        "cold": round(
                            100
                            * sum(value > threshold for value in cold)
                            / len(cold),
                            3,
                        ),
                        "hit": round(
                            100
                            * sum(value > threshold for value in hit)
                            / len(hit),
                            3,
                        ),
                    }
                    for threshold in (100.0, 200.0, 500.0, 1000.0)
                },
            },
            "rounds": rounds,
        }
    return {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "configuration": {
            "server_url": args.server_url,
            "model": args.model,
            "prefix_content_tokens": args.prefix_tokens,
            "tail_content_tokens": args.tail_tokens,
            "noise_prompt_content_tokens_approx": args.noise_tokens,
            "noise_concurrency": args.noise_concurrency,
            "rounds": args.rounds,
            "discarded_warmup_rounds_per_concurrency": 1,
            "max_tokens": args.max_tokens,
        },
        "by_noise_concurrency": results,
        "limitations": [
            (
                "Concurrent synthetic prefills create queue/scheduler pressure "
                "but are not a calibrated production arrival process."
            ),
            (
                "The experiment preserves the prefix before the loaded batch; "
                "it does not implement or compare a Family retention policy."
            ),
            (
                "Cold and hit batches are paired but execute sequentially, so "
                "slow thermal/system drift can still affect the comparison."
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
    parser.add_argument("--prefix-tokens", type=int, default=7808)
    parser.add_argument("--tail-tokens", type=int, default=128)
    parser.add_argument("--noise-tokens", type=int, default=4096)
    parser.add_argument(
        "--noise-concurrency", type=int, nargs="+", default=[4, 8]
    )
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
