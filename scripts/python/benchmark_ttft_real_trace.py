#!/usr/bin/env python3
"""Validate TTFT conversion on a real cross-project OpenHands prefix."""

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

from lmcache_trace_utils import (
    DEFAULT_TOKENIZER,
    DEFAULT_TRACE_DIR,
    clean_message,
    load_first_turns,
    tokenize_messages,
)
from benchmark_ttft_cold_vs_hit import (
    flush_cache,
    health_check,
    measure_request,
    summarize,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/"
    "exp_f01_real_cross_project_ttft/run_1.json"
)


def pick_session(
    rows: list[dict[str, Any]], project: str
) -> dict[str, Any]:
    prefix = f"swebench__{project}__"
    for row in rows:
        if (
            row["session_id"].startswith(prefix)
            and row["model"] == "minimax-m2.5"
        ):
            return row
    raise ValueError(f"No minimax first turn found for project {project}")


def exact_lcp(left: list[int], right: list[int]) -> int:
    count = 0
    for left_token, right_token in zip(left, right):
        if left_token != right_token:
            break
        count += 1
    return count


def api_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [clean_message(message) for message in row["messages"]]


async def run_direction(
    client: AsyncOpenAI,
    server_url: str,
    model: str,
    warm_row: dict[str, Any],
    probe_row: dict[str, Any],
    rounds: int,
    max_tokens: int,
) -> dict[str, Any]:
    warm_messages = api_messages(warm_row)
    probe_messages = api_messages(probe_row)
    direction = (
        f"{warm_row['session_id']} -> {probe_row['session_id']}"
    )

    async def one_round(round_index: int) -> dict[str, Any]:
        flush_cache(server_url)
        cold = await measure_request(
            client,
            model,
            probe_messages,
            f"real-r{round_index}-cold",
            max_tokens,
        )
        flush_cache(server_url)
        warm = await measure_request(
            client,
            model,
            warm_messages,
            f"real-r{round_index}-warm",
            max_tokens,
        )
        hit = await measure_request(
            client,
            model,
            probe_messages,
            f"real-r{round_index}-hit",
            max_tokens,
        )
        if cold["ttft_ms"] is None or hit["ttft_ms"] is None:
            raise RuntimeError("Missing first-token timestamp")
        return {
            "round": round_index,
            "cold": cold,
            "warm": warm,
            "hit": hit,
            "paired_ttft_saving_ms": round(
                cold["ttft_ms"] - hit["ttft_ms"], 3
            ),
            "paired_ttft_reduction_pct": round(
                100
                * (cold["ttft_ms"] - hit["ttft_ms"])
                / cold["ttft_ms"],
                3,
            ),
        }

    await one_round(-1)
    measured = []
    print(direction, flush=True)
    for round_index in range(rounds):
        result = await one_round(round_index)
        measured.append(result)
        print(
            f"  round={round_index} "
            f"cold={result['cold']['ttft_ms']:.1f}ms "
            f"hit={result['hit']['ttft_ms']:.1f}ms "
            f"cached={result['hit']['cached_tokens']}",
            flush=True,
        )

    cold_ttft = [row["cold"]["ttft_ms"] for row in measured]
    hit_ttft = [row["hit"]["ttft_ms"] for row in measured]
    savings = [row["paired_ttft_saving_ms"] for row in measured]
    reductions = [
        row["paired_ttft_reduction_pct"] for row in measured
    ]
    return {
        "direction": direction,
        "warm_session_id": warm_row["session_id"],
        "probe_session_id": probe_row["session_id"],
        "summary": {
            "cold_ttft_ms": summarize(cold_ttft),
            "hit_ttft_ms": summarize(hit_ttft),
            "paired_ttft_saving_ms": summarize(savings),
            "paired_ttft_reduction_pct": summarize(reductions),
            "cold_cached_tokens": summarize(
                [row["cold"]["cached_tokens"] for row in measured]
            ),
            "hit_cached_tokens": summarize(
                [row["hit"]["cached_tokens"] for row in measured]
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
                for threshold in (100.0, 200.0, 500.0)
            },
        },
        "rounds": measured,
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    health_check(args.server_url)
    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True
    )
    rows, audit = load_first_turns(args.trace_dir, None, None)
    astropy = pick_session(rows, "astropy")
    django = pick_session(rows, "django")
    astropy_tokens = tokenize_messages(tokenizer, astropy["messages"])
    django_tokens = tokenize_messages(tokenizer, django["messages"])
    lcp_tokens = exact_lcp(astropy_tokens, django_tokens)

    client = AsyncOpenAI(
        base_url=f"{args.server_url}/v1",
        api_key="dummy",
        timeout=args.request_timeout,
    )
    directions = [
        await run_direction(
            client,
            args.server_url,
            args.model,
            astropy,
            django,
            args.rounds,
            args.max_tokens,
        ),
        await run_direction(
            client,
            args.server_url,
            args.model,
            django,
            astropy,
            args.rounds,
            args.max_tokens,
        ),
    ]
    return {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "configuration": {
            "server_url": args.server_url,
            "model": args.model,
            "rounds": args.rounds,
            "discarded_warmup_rounds_per_direction": 1,
            "max_tokens": args.max_tokens,
            "tokenizer_path": str(args.tokenizer_path),
            "chat_template_sha256": hashlib.sha256(
                (tokenizer.chat_template or "").encode()
            ).hexdigest(),
        },
        "trace_audit": {
            "sessions": audit["unique_explicit_sessions"],
            "astropy_session_id": astropy["session_id"],
            "django_session_id": django["session_id"],
            "astropy_prompt_tokens": len(astropy_tokens),
            "django_prompt_tokens": len(django_tokens),
            "exact_lcp_tokens": lcp_tokens,
        },
        "directions": directions,
        "limitations": [
            (
                "The experiment uses real prompts but remains a single-request "
                "no-queue microbenchmark with explicit cache flushes."
            ),
            (
                "It proves TTFT conversion for one representative cross-project "
                "pair, not the full workload distribution."
            ),
            (
                "Content-addressed radix reuse is exercised without session_id; "
                "the next phase must test retention under cache pressure."
            ),
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="Qwen3-8B")
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument(
        "--tokenizer-path", type=Path, default=DEFAULT_TOKENIZER
    )
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=120.0)
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
