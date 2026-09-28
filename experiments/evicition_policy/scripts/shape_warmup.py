#!/usr/bin/env python3
"""Fixed engineering-only shapes; never counted as replay measurements."""

import asyncio
import json
from pathlib import Path
import time

import aiohttp

from prepare_data import canonical_digest, save_json
from check_admission import output_limit


def validate_shapes(plan: dict, info: dict) -> None:
    if plan.get("purpose") != "engineering_shape_warmup_only" or plan.get("passes") != 2:
        raise ValueError("Expected two fixed engineering warmup passes")
    cases = plan["cases"]
    if not cases or len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("Missing or duplicate warmup cases")
    for case in cases:
        tokens = case["input_ids"]
        if not tokens or any(type(token) is not int or token < 0 for token in tokens):
            raise ValueError("Invalid warmup token IDs")
        if canonical_digest(tokens) != case["input_ids_sha256"]:
            raise ValueError("Warmup input hash drift")
        if type(case["output_tokens"]) is not int or not 0 < case["output_tokens"] <= output_limit(
                len(tokens), info["context_length"], info["max_total_num_tokens"], info["page_size"]):
            raise ValueError("Warmup exceeds native admission")
    referenced = [case_id for group in plan["groups"] for case_id in group]
    if sorted(referenced) != sorted(case["case_id"] for case in cases) or any(not group for group in plan["groups"]):
        raise ValueError("Warmup groups must cover every case exactly once")


async def run_shapes(client, base_url: str, plan: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    cases = {case["case_id"]: case for case in plan["cases"]}
    records = []
    started = time.perf_counter()
    async def generate(case):
        begin = time.perf_counter()
        record = {"case_id": case["case_id"], "input_ids_sha256": case["input_ids_sha256"],
                  "prompt_tokens": len(case["input_ids"]), "expected_output_tokens": case["output_tokens"],
                  "source": case["source"], "status": "running"}
        try:
            payload = {"input_ids": case["input_ids"], "return_prompt_token_ids": True,
                       "sampling_params": {"temperature": 0, "sampling_seed": 42,
                                           "max_new_tokens": case["output_tokens"], "ignore_eos": True}}
            async with client.post(base_url + "/generate", json=payload,
                                   timeout=aiohttp.ClientTimeout(total=1800)) as response:
                response.raise_for_status()
                result = await response.json()
            meta = result["meta_info"]
            record.update(actual_output_tokens=len(result.get("output_ids", [])),
                          output_ids=result.get("output_ids", []), meta_info=meta,
                          native_input_echo_exact_match=result.get("prompt_token_ids") == case["input_ids"])
            if (not record["native_input_echo_exact_match"] or meta.get("prompt_tokens") != len(case["input_ids"])
                    or record["actual_output_tokens"] != case["output_tokens"]
                    or meta.get("completion_tokens") != case["output_tokens"]
                    or meta.get("finish_reason", {}).get("type") != "length"):
                raise ValueError("Warmup echo/output protocol mismatch")
            record["status"] = "completed"
        except BaseException as error:
            record.update(status="failed", error=repr(error))
            raise
        finally:
            record["elapsed_seconds"] = time.perf_counter() - begin
            records.append(record)
            save_json(output / (case["case_id"] + ".json"), record)
    status = "failed"
    try:
        for group in plan["groups"]:
            outcomes = await asyncio.gather(*(generate(cases[case_id]) for case_id in group), return_exceptions=True)
            if any(isinstance(outcome, BaseException) for outcome in outcomes):
                raise RuntimeError("At least one shape warmup request failed")
        status = "completed"
    finally:
        summary = {"status": status, "expected_requests": len(cases), "recorded_requests": len(records),
                   "completed_requests": sum(record["status"] == "completed" for record in records),
                   "plan_sha256": canonical_digest(plan), "elapsed_seconds": time.perf_counter() - started,
                   "maximum_prompt_tokens": max(len(case["input_ids"]) for case in cases.values()),
                   "batch_sizes_requested": [len(group) for group in plan["groups"]],
                   "note": "Requested concurrency does not prove a specific scheduler batch; no performance claims."}
        save_json(output / "summary.json", summary)
    return summary
