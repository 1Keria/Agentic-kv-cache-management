#!/usr/bin/env python3
"""Post-pressure retention benchmark for LRU and priority-tagged Families."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from transformers import AutoTokenizer

from analyze_f01_cross_session_prefix import (
    DEFAULT_TRACE_DIR,
    clean_message,
    load_first_turns,
    tokenize_messages,
)
from benchmark_cross_session_ttft import (
    DEFAULT_TOKENIZER,
    flush_cache,
    health_check,
    make_exact_token_text,
    make_messages,
    measure_request,
    summarize,
)
from benchmark_real_cross_project_ttft import exact_lcp, pick_session


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/exp_f02_oracle_family_retention"
)


def noise_messages(tokenizer: Any, tokens: int, index: int) -> list[dict[str, str]]:
    digest = hashlib.sha256(f"f02-noise-{index}".encode()).hexdigest()
    prefix = f"Independent pressure stream {index} {digest}. "
    body = make_exact_token_text(tokenizer, tokens, seed=index)
    return make_messages(prefix + body, f"Complete pressure task {index}.")


def real_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [clean_message(message) for message in row["messages"]]


def build_scenarios(
    tokenizer: Any, trace_dir: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    prefix = make_exact_token_text(tokenizer, 7808, seed=2)
    synthetic = {
        "warm": make_messages(
            prefix, make_exact_token_text(tokenizer, 128, seed=0)
        ),
        "probe": make_messages(
            prefix, make_exact_token_text(tokenizer, 128, seed=1)
        ),
        "expected_shared_tokens": 7816,
        "overprotected_tokens": 133,
    }

    rows, audit = load_first_turns(trace_dir, None, None)
    astropy = pick_session(rows, "astropy")
    django = pick_session(rows, "django")
    astropy_tokens = tokenize_messages(tokenizer, astropy["messages"])
    django_tokens = tokenize_messages(tokenizer, django["messages"])
    shared = exact_lcp(astropy_tokens, django_tokens)
    real = {
        "warm": real_messages(astropy),
        "probe": real_messages(django),
        "expected_shared_tokens": shared,
        "overprotected_tokens": len(astropy_tokens) - shared,
        "warm_session_id": astropy["session_id"],
        "probe_session_id": django["session_id"],
    }
    return {"synthetic": synthetic, "real": real}, {
        "trace_sessions": audit["unique_explicit_sessions"],
        "real_exact_lcp_tokens": shared,
    }


async def one_round(
    client: AsyncOpenAI,
    server_url: str,
    model: str,
    scenario_name: str,
    scenario: dict[str, Any],
    pressure: list[list[dict[str, str]]],
    round_index: int,
    family_priority: int,
    noise_priority: int,
    max_tokens: int,
) -> dict[str, Any]:
    flush_cache(server_url)
    warm = await measure_request(
        client,
        model,
        scenario["warm"],
        f"{scenario_name}-r{round_index}-warm",
        max_tokens,
        priority=family_priority,
    )
    baseline_probe = await measure_request(
        client,
        model,
        scenario["probe"],
        f"{scenario_name}-r{round_index}-baseline",
        max_tokens,
        priority=noise_priority,
    )
    pressure_results = []
    for index, messages in enumerate(pressure):
        pressure_results.append(
            await measure_request(
                client,
                model,
                messages,
                f"{scenario_name}-r{round_index}-noise-{index}",
                max_tokens,
                priority=noise_priority,
            )
        )
    post_probe = await measure_request(
        client,
        model,
        scenario["probe"],
        f"{scenario_name}-r{round_index}-post",
        max_tokens,
        priority=family_priority,
    )
    expected = scenario["expected_shared_tokens"]
    return {
        "round": round_index,
        "warm": warm,
        "baseline_probe": baseline_probe,
        "pressure": pressure_results,
        "post_pressure_probe": post_probe,
        "expected_shared_tokens": expected,
        "retained_shared_tokens": min(expected, post_probe["cached_tokens"]),
        "retained_shared_ratio": round(
            min(expected, post_probe["cached_tokens"]) / expected, 6
        ),
        "lost_cached_tokens_vs_baseline": max(
            0, baseline_probe["cached_tokens"] - post_probe["cached_tokens"]
        ),
    }


def summarize_rounds(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    cached = [row["post_pressure_probe"]["cached_tokens"] for row in rounds]
    ttft = [row["post_pressure_probe"]["ttft_ms"] for row in rounds]
    retained = [row["retained_shared_ratio"] * 100 for row in rounds]
    expected = rounds[0]["expected_shared_tokens"]
    return {
        "post_pressure_cached_tokens": summarize(cached),
        "post_pressure_ttft_ms": summarize(ttft),
        "retained_shared_ratio_pct": summarize(retained),
        "full_family_residency_rate_pct": round(
            100 * sum(value >= expected for value in cached) / len(cached), 3
        ),
        "slo_violation_rates_pct": {
            str(threshold): round(
                100 * sum(value > threshold for value in ttft) / len(ttft), 3
            )
            for threshold in (100.0, 200.0, 500.0)
        },
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    health_check(args.server_url)
    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True
    )
    scenarios, trace_audit = build_scenarios(tokenizer, args.trace_dir)
    pressure = [
        noise_messages(tokenizer, args.noise_tokens, index)
        for index in range(args.noise_count)
    ]
    client = AsyncOpenAI(
        base_url=f"{args.server_url}/v1",
        api_key="dummy",
        timeout=args.request_timeout,
        max_retries=0,
    )

    by_scenario = {}
    for name in args.scenarios:
        scenario = scenarios[name]
        await one_round(
            client,
            args.server_url,
            args.model,
            name,
            scenario,
            pressure,
            -1,
            args.family_priority,
            args.noise_priority,
            args.max_tokens,
        )
        rounds = []
        print(f"scenario={name}", flush=True)
        for round_index in range(args.rounds):
            row = await one_round(
                client,
                args.server_url,
                args.model,
                name,
                scenario,
                pressure,
                round_index,
                args.family_priority,
                args.noise_priority,
                args.max_tokens,
            )
            rounds.append(row)
            probe = row["post_pressure_probe"]
            print(
                f"  round={round_index} cached={probe['cached_tokens']} "
                f"ttft={probe['ttft_ms']:.1f}ms "
                f"retained={row['retained_shared_ratio']:.1%}",
                flush=True,
            )
        by_scenario[name] = {
            "expected_shared_tokens": scenario["expected_shared_tokens"],
            "request_level_overprotected_tokens": scenario["overprotected_tokens"],
            "summary": summarize_rounds(rounds),
            "rounds": rounds,
        }

    return {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "configuration": {
            "arm": args.arm,
            "expected_eviction_policy": args.eviction_policy,
            "server_url": args.server_url,
            "model": args.model,
            "family_priority": args.family_priority,
            "noise_priority": args.noise_priority,
            "noise_count": args.noise_count,
            "noise_content_tokens": args.noise_tokens,
            "rounds": args.rounds,
            "discarded_warmup_rounds": 1,
            "max_tokens": args.max_tokens,
            "request_order": "strictly sequential",
        },
        "trace_audit": trace_audit,
        "by_scenario": by_scenario,
        "limitations": [
            "The arm label is supplied by the runner; the HTTP API does not expose the active eviction policy.",
            "Request priority protects the complete warm path, not only the shared Family prefix.",
            "Priority is max-aggregated and has no TTL or decay in this SGLang version.",
            "Synthetic sequential pressure is a controlled capacity test, not a production arrival process.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="Qwen3-8B")
    parser.add_argument("--arm", required=True)
    parser.add_argument(
        "--eviction-policy", choices=("lru", "priority"), required=True
    )
    parser.add_argument("--family-priority", type=int, default=0)
    parser.add_argument("--noise-priority", type=int, default=0)
    parser.add_argument("--noise-count", type=int, default=6)
    parser.add_argument("--noise-tokens", type=int, default=10000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument(
        "--scenarios", nargs="+", choices=("synthetic", "real"),
        default=["synthetic", "real"],
    )
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument(
        "--tokenizer-path", type=Path, default=DEFAULT_TOKENIZER
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(benchmark(args))
    output = args.output or (
        DEFAULT_OUTPUT_DIR / f"{args.arm}_n{args.noise_count}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
