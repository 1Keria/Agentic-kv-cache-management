#!/usr/bin/env python3
"""Phase 1B: Single-session multi-turn replay on vLLM.

Replays a real LMCache trace session (30+ turns) on vLLM,
recording cached_tokens, TTFT, and kv_cache_usage_perc per turn.

Compares measured cached_tokens with theoretical prefix_reusable_tokens from Phase 1A.
"""

import json
import time
import sys
from pathlib import Path

import pyarrow.ipc as ipc
import openai

# --- Config ---
BASE_URL = "http://localhost:8000/v1"
API_KEY = "dummy"
TRACE_DIR = Path("experiments/vllm_kv_cache/lmcache_traces")
OUTPUT_DIR = Path("experiments/vllm_kv_cache/investigation/data")
MODEL_PATH = "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"

# Pick a session with many turns (we'll find one from the data)
TARGET_SESSION_PREFIX = "swebench__django__django-10097__minimax"


def load_session(session_id: str):
    """Load all turns for a given session from Arrow files."""
    turns = []
    for i in range(5):
        path = TRACE_DIR / f"data-0000{i}-of-00005.arrow"
        reader = ipc.open_stream(str(path))
        table = reader.read_all()
        for j in range(table.num_rows):
            sid = table.column("session_id")[j].as_py()
            if sid == session_id:
                msgs = table.column("input")[j].as_py()
                output_len = table.column("output_length")[j].as_py()
                pre_gap = table.column("pre_gap")[j].as_py()
                turns.append({
                    "messages": msgs,
                    "output_length": output_len,
                    "pre_gap": pre_gap,
                })
    return turns


def find_long_session(min_turns=5):
    """Find a SWE-bench minimax session suitable for replay.

    Criteria: enough turns, but not so long that early turns exceed context.
    We need sessions where the first ~5 turns fit in 40K context.
    """
    session_turns = {}
    for i in range(5):
        path = TRACE_DIR / f"data-0000{i}-of-00005.arrow"
        reader = ipc.open_stream(str(path))
        table = reader.read_all()
        for j in range(table.num_rows):
            sid = table.column("session_id")[j].as_py()
            model = table.column("model")[j].as_py()
            if sid.startswith("swebench__django") and model == "minimax-m2.5":
                session_turns[sid] = session_turns.get(sid, 0) + 1

    # Pick sessions with 8-15 turns (not too long)
    candidates = [(sid, count) for sid, count in session_turns.items() if min_turns <= count <= 15]
    candidates.sort(key=lambda x: -x[1])

    print(f"Found {len(candidates)} django minimax sessions with {min_turns}-15 turns")
    if candidates:
        print(f"Top 3: {[(s[:60], c) for s, c in candidates[:3]]}")
        return candidates[0][0]
    return None


def send_request(client, messages, max_tokens=10):
    """Send a chat completion request and measure TTFT + cached_tokens."""
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL_PATH,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        elapsed = time.time() - start

        # Extract metrics
        usage = resp.usage
        cached_tokens = 0
        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            for detail in usage.prompt_tokens_details:
                if hasattr(detail, 'cached_tokens'):
                    cached_tokens = detail.cached_tokens

        prompt_tokens = usage.prompt_tokens if usage else 0

        return {
            "ttft_ms": round(elapsed * 1000, 1),
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "hit_rate": round(cached_tokens / prompt_tokens * 100, 1) if prompt_tokens > 0 else 0,
            "success": True,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def get_kv_usage():
    """Scrape kv_cache_usage_perc from Prometheus metrics."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8000/metrics") as resp:
            text = resp.read().decode()
            for line in text.split("\n"):
                if line.startswith("vllm:kv_cache_usage_perc"):
                    return float(line.split()[1])
    except:
        pass
    return None


def main():
    print("=" * 60)
    print("Phase 1B: vLLM Single-Session Multi-Turn Replay")
    print("=" * 60)

    client = openai.Client(base_url=BASE_URL, api_key=API_KEY)

    # Find a suitable session
    print("\n[1/3] Finding a suitable session...")
    session_id = find_long_session(min_turns=8)
    if not session_id:
        print("❌ No suitable session found!")
        return 1
    print(f"Selected: {session_id}")

    # Load turns
    print("\n[2/3] Loading session turns...")
    turns = load_session(session_id)
    print(f"Loaded {len(turns)} turns")
    if len(turns) < 5:
        print("❌ Too few turns!")
        return 1

    # Replay each turn (only those that fit in context)
    print(f"\n[3/3] Replaying turns on vLLM (max context = 40960 tokens)...")
    results = []
    MAX_CONTEXT = 40960  # Qwen3-8B max context

    # Load Phase 1A data for comparison
    per_row_path = OUTPUT_DIR / "per_row_metrics.json"
    theoretical = {}
    if per_row_path.exists():
        with open(per_row_path) as f:
            phase1a_data = json.load(f)
        for r in phase1a_data:
            if r["session_id"] == session_id:
                theoretical[r["turn_index"]] = r

    for turn_idx, turn in enumerate(turns):
        messages = turn["messages"]

        # Convert to OpenAI format, handling tool_calls properly
        openai_msgs = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []
            tool_call_id = msg.get("tool_call_id", "")
            name = msg.get("name", "")

            if role == "assistant" and tool_calls:
                # Assistant with tool calls - just include the text content if any
                # Skip tool calls for simplicity (they'd require tool schemas)
                if content:
                    openai_msgs.append({"role": "assistant", "content": content})
                else:
                    # Summarize tool calls
                    tc_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                    openai_msgs.append({"role": "assistant", "content": f"[Called tools: {', '.join(tc_names)}]"})
            elif role == "tool":
                # Tool result - convert to user message with context
                tool_content = content if content else "[tool result]"
                openai_msgs.append({"role": "user", "content": f"[Tool result from {name or tool_call_id}]: {tool_content[:500]}"})
            elif content:
                openai_msgs.append({"role": role, "content": content})
            # Skip empty messages

        if len(openai_msgs) == 0:
            print(f"  Turn {turn_idx}: SKIP (no messages)")
            continue

        # Estimate token count to check if it fits in context
        # Rough estimate: chars / 3.5 (empirical for Qwen3)
        total_chars = sum(len(m.get("content", "")) for m in openai_msgs)
        est_tokens = total_chars // 3
        if est_tokens > MAX_CONTEXT - 10:
            print(f"  Turn {turn_idx}: SKIP (estimated {est_tokens} tokens > {MAX_CONTEXT})")
            # Still record the skip
            results.append({
                "turn_index": turn_idx,
                "num_messages": len(openai_msgs),
                "est_tokens": est_tokens,
                "success": False,
                "error": f"exceeds context limit (est {est_tokens} > {MAX_CONTEXT})",
            })
            continue

        # Send request
        result = send_request(client, openai_msgs, max_tokens=5)
        kv_usage = get_kv_usage()

        result["turn_index"] = turn_idx
        result["num_messages"] = len(openai_msgs)
        result["kv_cache_usage_perc"] = kv_usage

        # Compare with theoretical
        if turn_idx in theoretical:
            th = theoretical[turn_idx]
            result["theoretical_total_tokens"] = th["total_tokens"]
            result["theoretical_prefix_reusable"] = th.get("prefix_reusable_tokens", 0)
            if turn_idx > 0 and turn_idx - 1 in theoretical:
                result["theoretical_prefix_reusable"] = theoretical[turn_idx - 1]["total_tokens"]

        results.append(result)

        status = "✅" if result.get("success") else "❌"
        cached = result.get("cached_tokens", "?")
        prompt = result.get("prompt_tokens", "?")
        ttft = result.get("ttft_ms", "?")
        kv = result.get("kv_cache_usage_perc", "?")
        th_prefix = result.get("theoretical_prefix_reusable", "?")
        print(f"  Turn {turn_idx}: {status} prompt={prompt}, cached={cached} ({result.get('hit_rate', '?')}%), "
              f"TTFT={ttft}ms, KV_usage={kv}%, theory_prefix={th_prefix}")

        # Wait a bit between turns
        time.sleep(0.5)

    # Save results
    output_path = OUTPUT_DIR / "phase1b_single_session_replay.json"
    output = {
        "session_id": session_id,
        "num_turns": len(turns),
        "results": results,
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {output_path}")

    # Validation: compare theoretical vs measured
    print(f"\n{'='*60}")
    print("VALIDATION: Theoretical vs Measured cached_tokens")
    print(f"{'='*60}")

    match_count = 0
    total_count = 0
    for r in results:
        if not r.get("success") or "theoretical_prefix_reusable" not in r:
            continue
        measured = r.get("cached_tokens", 0)
        theoretical_val = r.get("theoretical_prefix_reusable", 0)
        if r["turn_index"] == 0:
            # First turn: should have 0 cached
            expected = 0
        else:
            expected = theoretical_val

        total_count += 1
        # Allow 20% tolerance (block alignment + tokenization differences)
        if expected == 0 and measured < 100:
            match = True
        elif expected > 0 and abs(measured - expected) / expected < 0.25:
            match = True
        else:
            match = False

        if match:
            match_count += 1

        sym = "✅" if match else "⚠️"
        print(f"  Turn {r['turn_index']}: expected≈{expected}, measured={measured}, diff={measured-expected if expected else 'N/A'} {sym}")

    print(f"\n  Match rate: {match_count}/{total_count} ({match_count/total_count*100:.0f}%)" if total_count > 0 else "  No comparable turns")

    return 0


if __name__ == "__main__":
    sys.exit(main())
