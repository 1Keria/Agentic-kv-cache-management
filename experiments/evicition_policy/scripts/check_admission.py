#!/usr/bin/env python3
"""Reject requests that the pinned native scheduler would silently shorten."""


def output_limit(prompt_tokens: int, context_length: int, full_capacity: int, page_size: int) -> int:
    if min(context_length, full_capacity, page_size) <= 0 or prompt_tokens <= 0:
        raise ValueError("Admission dimensions must be positive")
    max_request_length = min(context_length, full_capacity) - 1
    if prompt_tokens > max_request_length - 5:
        return 0
    paged_prompt = ((prompt_tokens + page_size - 1) // page_size) * page_size
    return max(0, min(max_request_length - prompt_tokens - 1,
                      full_capacity - paged_prompt - page_size - 1))


def validate_admission(loaded: list, workload: dict, info: dict) -> dict:
    minimum_headroom = None
    limiting_request = None
    count = 0
    for entry, rows in loaded:
        for row in rows:
            target = row["output_tokens"]
            if workload.get("output_token_cap") is not None:
                target = min(target, workload["output_token_cap"])
            allowed = output_limit(row["prompt_tokens"], info["context_length"],
                                   info["max_total_num_tokens"], info["page_size"])
            headroom = allowed - target
            if headroom < 0:
                raise ValueError(f"Native scheduler would shorten {entry['session_id']} turn {row['turn_index']}: "
                                 f"requested output {target}, allowed {allowed}; no truncation permitted")
            if minimum_headroom is None or headroom < minimum_headroom:
                minimum_headroom = headroom
                limiting_request = {"session_id": entry["session_id"], "turn_index": row["turn_index"],
                                    "prompt_tokens": row["prompt_tokens"], "output_tokens": target}
            count += 1
    if not count:
        raise ValueError("Empty admission workload")
    return {"status": "passed", "requests": count, "minimum_output_headroom_tokens": minimum_headroom,
            "limiting_request": limiting_request, "engine_release": "0.5.13.post1",
            "checks": ["maximum_input_length", "context_output_margin", "page_aligned_cache_output_margin"],
            "note": "Single-request admission only; this does not guarantee concurrent requests fit."}
