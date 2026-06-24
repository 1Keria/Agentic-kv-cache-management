#!/usr/bin/env python3
"""Phase 2A: Simplified KV Cache simulation using Python.

Implements FIFO/LRU/Optimal eviction policies on block hash sequences
derived from tiktoken tokenization of LMCache agentic traces.

Output: experiments/vllm_kv_cache/investigation/data/simulation_results.json
"""

import json
import time
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.ipc as ipc
import tiktoken

# --- Config ---
TRACE_DIR = Path("experiments/vllm_kv_cache/lmcache_traces")
OUTPUT_DIR = Path("experiments/vllm_kv_cache/investigation/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ENC = tiktoken.get_encoding("cl100k_base")
BLOCK_SIZE = 16  # vLLM default


def count_tokens(text: str) -> int:
    return len(ENC.encode(text))


def hash_block(parent_hash: int, token_ids: list) -> int:
    """Simple prefix-aware hash for a block of token IDs."""
    import hashlib
    data = parent_hash.to_bytes(8, 'little') + b','.join(str(t).encode() for t in token_ids)
    return int(hashlib.blake2b(data, digest_size=8).hexdigest(), 16)


def compute_block_hashes(token_ids: list, block_size: int = BLOCK_SIZE) -> list:
    """Compute prefix-aware block hashes for a token sequence."""
    hashes = []
    parent_hash = 0
    for i in range(0, len(token_ids), block_size):
        block_tokens = token_ids[i:i+block_size]
        if len(block_tokens) < block_size:
            break  # Skip incomplete blocks (they can't be cached in vLLM)
        h = hash_block(parent_hash, block_tokens)
        hashes.append(h)
        parent_hash = h
    return hashes


def tokenize_messages(messages):
    """Tokenize all messages and return concatenated token IDs."""
    all_tokens = []
    for msg in messages:
        content = msg.get("content", "") or ""
        if content:
            all_tokens.extend(ENC.encode(content))
    return all_tokens


def load_traces(max_sessions=None):
    """Load traces and compute block hash sequences per request."""
    print("Loading and tokenizing traces...")

    # Group by session
    session_rows = defaultdict(list)
    for fi in range(5):
        path = TRACE_DIR / f"data-0000{fi}-of-00005.arrow"
        reader = ipc.open_stream(str(path))
        table = reader.read_all()
        for j in range(table.num_rows):
            sid = table.column("session_id")[j].as_py()
            model = table.column("model")[j].as_py()
            msgs = table.column("input")[j].as_py()
            output_len = table.column("output_length")[j].as_py()
            # Only use SWE-bench minimax for consistency
            if sid.startswith("swebench") and model == "minimax-m2.5":
                session_rows[sid].append({
                    "messages": msgs,
                    "output_length": output_len,
                })

    if max_sessions:
        # Take a subset
        sids = sorted(session_rows.keys())[:max_sessions]
        session_rows = {sid: session_rows[sid] for sid in sids}

    # Compute block hashes for each request
    print(f"  {len(session_rows)} sessions")

    requests = []  # List of (block_hashes, num_tokens, session_id, turn_index)
    t0 = time.time()

    for sid, turns in sorted(session_rows.items()):
        for turn_idx, turn in enumerate(turns):
            token_ids = tokenize_messages(turn["messages"])
            block_hashes = compute_block_hashes(token_ids, BLOCK_SIZE)
            requests.append({
                "block_hashes": block_hashes,
                "num_tokens": len(token_ids),
                "num_blocks": len(block_hashes),
                "session_id": sid,
                "turn_index": turn_idx,
            })

    elapsed = time.time() - t0
    total_blocks = sum(r["num_blocks"] for r in requests)
    unique_blocks = len(set(h for r in requests for h in r["block_hashes"]))

    print(f"  Tokenized {len(requests)} requests in {elapsed:.1f}s")
    print(f"  Total blocks: {total_blocks}, Unique blocks: {unique_blocks}")
    print(f"  Unique block ratio: {unique_blocks/total_blocks*100:.2f}%")

    return requests


def simulate_fifo(requests, capacity_blocks):
    """Simulate FIFO eviction policy."""
    cache = []  # Ordered list of block hashes in cache
    cache_set = set()  # For O(1) lookup
    hit_tokens = 0
    total_tokens = 0

    for req in requests:
        for bh in req["block_hashes"]:
            total_tokens += BLOCK_SIZE
            if bh in cache_set:
                hit_tokens += BLOCK_SIZE
            else:
                if len(cache) >= capacity_blocks:
                    evicted = cache.pop(0)
                    cache_set.discard(evicted)
                cache.append(bh)
                cache_set.add(bh)

    return hit_tokens, total_tokens


def simulate_lru(requests, capacity_blocks):
    """Simulate LRU eviction policy."""
    cache = {}  # block_hash -> last_access_index
    access_order = 0
    hit_tokens = 0
    total_tokens = 0

    for req in requests:
        for bh in req["block_hashes"]:
            total_tokens += BLOCK_SIZE
            if bh in cache:
                hit_tokens += BLOCK_SIZE
                cache[bh] = access_order
            else:
                if len(cache) >= capacity_blocks:
                    # Evict least recently used
                    evict_hash = min(cache, key=cache.get)
                    del cache[evict_hash]
                cache[bh] = access_order
            access_order += 1

    return hit_tokens, total_tokens


def simulate_optimal(requests, capacity_blocks):
    """Simulate Optimal (Belady) eviction policy.

    Uses pre-computed next-use positions to decide which block to evict.
    """
    # Pre-compute all block access positions
    block_accesses = defaultdict(list)
    for req_idx, req in enumerate(requests):
        for block_idx, bh in enumerate(req["block_hashes"]):
            block_accesses[bh].append((req_idx, block_idx))

    # Create position-to-next-use mapping
    next_use = {}
    for bh, positions in block_accesses.items():
        for i, (req_idx, block_idx) in enumerate(positions):
            global_idx = sum(requests[r]["num_blocks"] for r in range(req_idx)) + block_idx
            next_use[(bh, global_idx)] = positions[i+1][0] if i+1 < len(positions) else float('inf')

    cache = {}  # block_hash -> (global_access_idx, next_use_idx)
    hit_tokens = 0
    total_tokens = 0
    global_idx = 0

    for req_idx, req in enumerate(requests):
        for block_idx, bh in enumerate(req["block_hashes"]):
            total_tokens += BLOCK_SIZE

            if bh in cache:
                hit_tokens += BLOCK_SIZE
                # Update next use
                nu = next_use.get((bh, global_idx), float('inf'))
                cache[bh] = (global_idx, nu)
            else:
                if len(cache) >= capacity_blocks:
                    # Evict block with furthest next use
                    evict_hash = max(cache, key=lambda h: cache[h][1])
                    del cache[evict_hash]
                nu = next_use.get((bh, global_idx), float('inf'))
                cache[bh] = (global_idx, nu)

            global_idx += 1

    return hit_tokens, total_tokens


def main():
    print("=" * 60)
    print("Phase 2A: KV Cache Capacity Sweep Simulation")
    print("=" * 60)

    # Load and tokenize traces
    requests = load_traces(max_sessions=50)  # Use 200 sessions for speed

    if not requests:
        print("No requests loaded!")
        return 1

    # Compute capacity range
    total_unique = len(set(h for r in requests for h in r["block_hashes"]))
    total_blocks = sum(r["num_blocks"] for r in requests)

    print(f"\nTotal unique blocks: {total_unique}")
    print(f"Total blocks: {total_blocks}")

    # Capacity sweep: from 100 to total_unique blocks
    import math
    max_capacity = min(total_unique, 10000)
    capacities = []
    # Logarithmic spacing
    for exp in range(0, 20):
        for mult in [1, 2, 5]:
            c = int(mult * (10 ** exp))
            if 100 <= c <= max_capacity:
                capacities.append(c)
    capacities = sorted(set(capacities))

    # Add key reference points
    # Qwen3-8B on H800 with gpu_util=0.3: ~2750 blocks (44K tokens / 16)
    # With gpu_util=0.1: would be ~0 blocks (can't load model)
    reference_points = [2750]  # 44K tokens on H800
    for rp in reference_points:
        if rp not in capacities:
            capacities.append(rp)
    capacities = sorted(set(capacities))

    print(f"\nCapacity sweep: {len(capacities)} points from {capacities[0]} to {capacities[-1]} blocks")
    print(f"  Reference point: 2750 blocks (~44K tokens on H800)")

    # Run simulations
    WARMUP_FRACTION = 0.5
    warmup_count = int(len(requests) * WARMUP_FRACTION)
    measurement_requests = requests[warmup_count:]

    results = {}
    for policy_name, simulate_fn in [("fifo", simulate_fifo), ("lru", simulate_lru), ("optimal", simulate_optimal)]:
        print(f"\nSimulating {policy_name}...")
        policy_results = []

        for cap in capacities:
            t0 = time.time()
            hit, total = simulate_fn(measurement_requests, cap)
            elapsed = time.time() - t0
            hit_rate = hit / total if total > 0 else 0

            policy_results.append({
                "capacity_blocks": cap,
                "capacity_tokens": cap * BLOCK_SIZE,
                "hit_tokens": hit,
                "total_tokens": total,
                "hit_rate": round(hit_rate, 4),
                "sim_time_s": round(elapsed, 2),
            })

            if cap in [500, 1000, 2750, 5000]:
                print(f"  capacity={cap} ({cap*BLOCK_SIZE}t): hit_rate={hit_rate:.4f} ({elapsed:.1f}s)")

        results[policy_name] = policy_results

    # Save results
    output = {
        "block_size": BLOCK_SIZE,
        "num_requests": len(requests),
        "measurement_requests": len(measurement_requests),
        "total_unique_blocks": total_unique,
        "warmup_fraction": WARMUP_FRACTION,
        "capacities": capacities,
        "results": results,
    }

    output_path = OUTPUT_DIR / "simulation_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {output_path}")

    # Print key comparison
    print(f"\n{'='*60}")
    print("KEY FINDINGS")
    print(f"{'='*60}")

    # Find LRU vs Optimal gap at 2750 blocks (H800 capacity)
    for cap in [1000, 2750, 5000]:
        lru_hr = next((r["hit_rate"] for r in results["lru"] if r["capacity_blocks"] == cap), None)
        opt_hr = next((r["hit_rate"] for r in results["optimal"] if r["capacity_blocks"] == cap), None)
        fifo_hr = next((r["hit_rate"] for r in results["fifo"] if r["capacity_blocks"] == cap), None)
        if lru_hr and opt_hr:
            gap = (opt_hr - lru_hr) * 100
            print(f"  @ {cap} blocks ({cap*BLOCK_SIZE}t): LRU={lru_hr:.4f}, Optimal={opt_hr:.4f}, FIFO={fifo_hr:.4f}, LRU→Opt gap={gap:.2f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
