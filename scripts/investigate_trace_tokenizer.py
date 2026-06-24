#!/usr/bin/env python3
"""Phase 1A: Full-dataset trace tokenization and characterization.

Tokenizes all 24,880 LMCache agentic trace requests using tiktoken,
computes L0/L1/L2 boundaries and per-turn metrics.

Output: experiments/vllm_kv_cache/investigation/data/tokenized_traces_summary.json
        experiments/vllm_kv_cache/investigation/data/per_row_metrics.json
"""

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.ipc as ipc
import tiktoken

# --- Config ---
TRACE_DIR = Path("experiments/vllm_kv_cache/lmcache_traces")
OUTPUT_DIR = Path("experiments/vllm_kv_cache/investigation/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base."""
    return len(ENC.encode(text))


def load_all_rows():
    """Load all rows from 5 Arrow files."""
    all_rows = []
    for i in range(5):
        path = TRACE_DIR / f"data-0000{i}-of-00005.arrow"
        print(f"  Loading {path.name}...", end=" ", flush=True)
        reader = ipc.open_stream(str(path))
        table = reader.read_all()
        rows = table.to_pydict()
        n = table.num_rows
        print(f"{n} rows")
        # Convert columnar to row-wise
        for j in range(n):
            row = {col: rows[col][j] for col in rows}
            all_rows.append(row)
    return all_rows


def identify_l0_l1_l2(messages):
    """Identify L0/L1/L2 token boundaries in a message list.

    Correct identification based on actual trace structure:

    SWE-bench sessions:
      L0 = message[0] (system role) — shared across ALL sessions
      L1 = message[1] + message[2] (examples + runtime info) — shared within same project
      L2 = message[3:] (task description + conversation history) — session-specific

    GAIA/WildClaw sessions:
      L0 = system message(s)
      L1 = 0 (no project-level shared prefix)
      L2 = everything else

    For multi-turn (turn > 0):
      L0 + L1 + history (previous turns' messages) = prefix reusable from prior KV cache
      Only the last message pair (assistant + user) is truly new (incremental)
    """
    l0_tokens = 0
    l1_tokens = 0
    l2_tokens = 0

    # Detect session type
    has_system = len(messages) > 0 and messages[0].get("role") == "system"

    if has_system:
        # L0 = system message
        l0_tokens = count_tokens(messages[0].get("content", "") or "")

        # L1 = messages[1] + messages[2] if they exist and look like shared content
        # Heuristic: if there are >= 3 messages and msg[1] is user with examples,
        # then msg[1] and msg[2] are L1 (shared project-level content)
        if len(messages) >= 3 and messages[1].get("role") == "user":
            content1 = messages[1].get("content", "") or ""
            content2 = messages[2].get("content", "") or ""
            # Check if msg[1] looks like examples (starts with common patterns)
            is_example = any(content1.startswith(p) for p in [
                "Here's a running example",
                "Here is a running example",
                "Below are some examples",
            ])
            if is_example:
                l1_tokens = count_tokens(content1) + count_tokens(content2)
                # L2 = messages[3:]
                for msg in messages[3:]:
                    l2_tokens += count_tokens(msg.get("content", "") or "")
            else:
                # No clear L1/L2 split; treat all non-system as L2
                for msg in messages[1:]:
                    l2_tokens += count_tokens(msg.get("content", "") or "")
        elif len(messages) >= 2:
            # Only system + user; all user messages are L2
            for msg in messages[1:]:
                l2_tokens += count_tokens(msg.get("content", "") or "")
    else:
        # No system message; all L2
        for msg in messages:
            l2_tokens += count_tokens(msg.get("content", "") or "")

    return l0_tokens, l1_tokens, l2_tokens


def get_project_from_session_id(session_id: str) -> str:
    """Extract project name from session_id like 'swebench__django__django-12345__model'."""
    parts = session_id.split("__")
    if len(parts) >= 3 and parts[0] == "swebench":
        return parts[1]
    return "other"


def process_row(row, turn_index: int) -> dict:
    """Process a single row and return metrics."""
    messages = row["input"]
    session_id = row["session_id"]
    model = row["model"]
    output_length = row["output_length"]
    pre_gap = row["pre_gap"]

    l0_tokens, l1_tokens, l2_tokens = identify_l0_l1_l2(messages)

    total_tokens = l0_tokens + l1_tokens + l2_tokens
    num_messages = len(messages)
    project = get_project_from_session_id(session_id)

    return {
        "session_id": session_id,
        "model": model,
        "project": project,
        "turn_index": turn_index,
        "total_tokens": total_tokens,
        "l0_tokens": l0_tokens,
        "l1_tokens": l1_tokens,
        "l2_tokens": l2_tokens,
        "num_messages": num_messages,
        "output_length": output_length,
        "pre_gap": pre_gap,
    }


def aggregate_metrics(per_row):
    """Compute aggregate metrics from per-row data."""
    # A. L0/L1/L2 breakdown by project
    project_stats = defaultdict(lambda: {"l0": [], "l1": [], "l2": [], "total": [], "first_turn_total": []})
    for r in per_row:
        proj = r["project"]
        project_stats[proj]["l0"].append(r["l0_tokens"])
        project_stats[proj]["l1"].append(r["l1_tokens"])
        project_stats[proj]["l2"].append(r["l2_tokens"])
        project_stats[proj]["total"].append(r["total_tokens"])
        if r["turn_index"] == 0:
            project_stats[proj]["first_turn_total"].append(r["total_tokens"])

    project_breakdown = {}
    for proj, stats in sorted(project_stats.items(), key=lambda x: -len(x[1]["total"])):
        project_breakdown[proj] = {
            "num_requests": len(stats["total"]),
            "l0_mean": round(sum(stats["l0"]) / len(stats["l0"]), 1),
            "l1_mean": round(sum(stats["l1"]) / len(stats["l1"]), 1),
            "l2_mean": round(sum(stats["l2"]) / len(stats["l2"]), 1),
            "total_mean": round(sum(stats["total"]) / len(stats["total"]), 1),
            "first_turn_total_mean": round(sum(stats["first_turn_total"]) / len(stats["first_turn_total"]), 1) if stats["first_turn_total"] else 0,
            "l0_pct": round(sum(stats["l0"]) / sum(stats["total"]) * 100, 1) if sum(stats["total"]) > 0 else 0,
            "l0_l1_pct": round((sum(stats["l0"]) + sum(stats["l1"])) / sum(stats["total"]) * 100, 1) if sum(stats["total"]) > 0 else 0,
        }

    # B. Per-turn input growth
    turn_totals = defaultdict(list)
    for r in per_row:
        turn_totals[r["turn_index"]].append(r["total_tokens"])

    turn_growth = {}
    for turn in sorted(turn_totals.keys()):
        vals = sorted(turn_totals[turn])
        n = len(vals)
        turn_growth[turn] = {
            "count": n,
            "p25": vals[n // 4],
            "p50": vals[n // 2],
            "p75": vals[3 * n // 4],
            "mean": round(sum(vals) / n, 1),
        }

    # C. Session KV footprint distribution
    session_max_kv = defaultdict(int)
    session_first_kv = defaultdict(int)
    for r in per_row:
        sid = r["session_id"]
        if r["total_tokens"] > session_max_kv[sid]:
            session_max_kv[sid] = r["total_tokens"]
        if r["turn_index"] == 0:
            session_first_kv[sid] = r["total_tokens"]

    growth_ratios = []
    for sid in session_max_kv:
        if session_first_kv[sid] > 0:
            growth_ratios.append(session_max_kv[sid] / session_first_kv[sid])

    growth_ratios.sort()
    n_sessions = len(growth_ratios)

    kv_footprint = {
        "num_sessions": n_sessions,
        "max_kv_p25": sorted(session_max_kv.values())[n_sessions // 4] if n_sessions > 0 else 0,
        "max_kv_p50": sorted(session_max_kv.values())[n_sessions // 2] if n_sessions > 0 else 0,
        "max_kv_p75": sorted(session_max_kv.values())[3 * n_sessions // 4] if n_sessions > 0 else 0,
        "growth_ratio_p25": growth_ratios[n_sessions // 4] if n_sessions > 0 else 0,
        "growth_ratio_p50": growth_ratios[n_sessions // 2] if n_sessions > 0 else 0,
        "growth_ratio_p75": growth_ratios[3 * n_sessions // 4] if n_sessions > 0 else 0,
        "growth_ratio_mean": round(sum(growth_ratios) / len(growth_ratios), 2) if growth_ratios else 0,
        "sessions_exceeding_44k": sum(1 for v in session_max_kv.values() if v > 44000),
        "pct_exceeding_44k": round(sum(1 for v in session_max_kv.values() if v > 44000) / n_sessions * 100, 1) if n_sessions > 0 else 0,
    }

    # D. Cross-session prefix overlap
    # All SWE-bench sessions share L0. Same-project sessions share L0+L1.
    project_l1 = {}
    for proj, stats in project_stats.items():
        if stats["l1"]:
            project_l1[proj] = round(sum(stats["l1"]) / len(stats["l1"]), 1)

    # L0 is shared by all
    l0_values = [r["l0_tokens"] for r in per_row if r["l0_tokens"] > 0]
    l0_shared = round(sum(l0_values) / len(l0_values), 1) if l0_values else 0

    cross_session = {
        "l0_shared_tokens": l0_shared,
        "l0_shared_by_all": True,
        "project_l1_tokens": project_l1,
    }

    # E. Concurrent arrival patterns from pre_gap
    # Group by session, compute inter-turn gaps
    session_turns = defaultdict(list)
    for r in per_row:
        session_turns[r["session_id"]].append(r)

    all_gaps = [r["pre_gap"] for r in per_row if r["pre_gap"] > 0]
    all_gaps.sort()
    n_gaps = len(all_gaps)

    arrival_patterns = {
        "inter_turn_gap_p50": all_gaps[n_gaps // 2] if n_gaps > 0 else 0,
        "inter_turn_gap_p75": all_gaps[3 * n_gaps // 4] if n_gaps > 0 else 0,
        "inter_turn_gap_p90": all_gaps[int(n_gaps * 0.9)] if n_gaps > 0 else 0,
        "inter_turn_gap_mean": round(sum(all_gaps) / n_gaps, 3) if n_gaps > 0 else 0,
        "num_sessions": len(session_turns),
    }

    return {
        "total_rows": len(per_row),
        "total_sessions": len(session_turns),
        "A_project_breakdown": project_breakdown,
        "B_turn_growth": turn_growth,
        "C_kv_footprint": kv_footprint,
        "D_cross_session_overlap": cross_session,
        "E_arrival_patterns": arrival_patterns,
    }


def main():
    print("=" * 60)
    print("Phase 1A: Full-dataset Trace Tokenization")
    print("=" * 60)

    # Load data
    print("\n[1/4] Loading Arrow files...")
    t0 = time.time()
    all_rows = load_all_rows()
    print(f"  Total: {len(all_rows)} rows in {time.time()-t0:.1f}s")

    # Group by session and sort by turn order
    print("\n[2/4] Grouping by session...")
    session_rows = defaultdict(list)
    for row in all_rows:
        session_rows[row["session_id"]].append(row)

    # Sort each session's rows by pre_gap (ascending within same session)
    # Actually, arrow files are already in order, so we just assign turn_index
    # But we need to be careful: same session rows may be interleaved
    # Let's sort by the order they appear in the data
    per_row = []
    for session_id, rows in session_rows.items():
        # Sort by appearance order (they should already be ordered)
        for turn_idx, row in enumerate(rows):
            metrics = process_row(row, turn_idx)
            per_row.append(metrics)

    # Sort per_row for consistent output
    per_row.sort(key=lambda r: (r["session_id"], r["turn_index"]))

    print(f"  Processed {len(per_row)} rows across {len(session_rows)} sessions")

    # Validate: check L0 token count
    l0_values = [r["l0_tokens"] for r in per_row if r["l0_tokens"] > 0]
    l0_counter = Counter(l0_values)
    print(f"\n[VALIDATION] L0 token distribution:")
    for val, count in l0_counter.most_common(5):
        print(f"  {val} tokens: {count} rows")

    # Aggregate
    print("\n[3/4] Computing aggregate metrics...")
    summary = aggregate_metrics(per_row)

    # Print key findings
    print(f"\n{'='*60}")
    print("KEY FINDINGS")
    print(f"{'='*60}")
    print(f"Total rows: {summary['total_rows']}")
    print(f"Total sessions: {summary['total_sessions']}")

    print(f"\n--- A. L0/L1/L2 Breakdown (top 5 projects) ---")
    for proj, stats in list(summary["A_project_breakdown"].items())[:5]:
        print(f"  {proj}: L0={stats['l0_mean']} L1={stats['l1_mean']} total={stats['total_mean']} "
              f"(L0={stats['l0_pct']}%, L0+L1={stats['l0_l1_pct']}%)")

    print(f"\n--- B. Turn Growth ---")
    for turn in [0, 1, 5, 10, 20, 30]:
        if turn in summary["B_turn_growth"]:
            tg = summary["B_turn_growth"][turn]
            print(f"  Turn {turn}: p50={tg['p50']}, p75={tg['p75']} tokens ({tg['count']} sessions)")

    print(f"\n--- C. KV Footprint ---")
    kv = summary["C_kv_footprint"]
    print(f"  Max KV: p50={kv['max_kv_p50']}, p75={kv['max_kv_p75']} tokens")
    print(f"  Growth ratio: p50={kv['growth_ratio_p50']:.2f}x, mean={kv['growth_ratio_mean']:.2f}x")
    print(f"  Sessions exceeding 44K: {kv['sessions_exceeding_44k']} ({kv['pct_exceeding_44k']}%)")

    print(f"\n--- D. Cross-session Overlap ---")
    cs = summary["D_cross_session_overlap"]
    print(f"  L0 shared: {cs['l0_shared_tokens']} tokens (by all sessions)")
    for proj, l1 in list(cs["project_l1_tokens"].items())[:5]:
        print(f"  {proj} L1: {l1} tokens")

    print(f"\n--- E. Arrival Patterns ---")
    ap = summary["E_arrival_patterns"]
    print(f"  Inter-turn gap: p50={ap['inter_turn_gap_p50']:.3f}s, mean={ap['inter_turn_gap_mean']:.3f}s")

    # Save
    print(f"\n[4/4] Saving results...")
    summary_path = OUTPUT_DIR / "tokenized_traces_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {summary_path}")

    per_row_path = OUTPUT_DIR / "per_row_metrics.json"
    with open(per_row_path, "w") as f:
        json.dump(per_row, f, indent=1, ensure_ascii=False)
    print(f"  Saved: {per_row_path} ({len(per_row)} rows)")

    # Validation checks
    print(f"\n{'='*60}")
    print("VALIDATION CHECKS")
    print(f"{'='*60}")

    checks = []
    # Check 1: SWE-bench minimax L0 ≈ 6157
    sb_l0 = [r["l0_tokens"] for r in per_row
             if r["session_id"].startswith("swebench") and r["model"] == "minimax-m2.5" and r["l0_tokens"] > 0]
    l0_sb = sum(sb_l0) / len(sb_l0) if sb_l0 else 0
    check1 = abs(l0_sb - 6157) < 100
    checks.append(("SWE-bench minimax L0 ≈ 6157", check1, f"actual={l0_sb:.0f}"))
    print(f"  {'✅' if check1 else '❌'} SWE-bench minimax L0 ≈ 6157 (actual={l0_sb:.0f})")

    # Check 2: Session count ≈ 767
    check2 = abs(summary["total_sessions"] - 767) < 50
    checks.append(("Sessions ≈ 767", check2, f"actual={summary['total_sessions']}"))
    print(f"  {'✅' if check2 else '❌'} Sessions ≈ 767 (actual={summary['total_sessions']})")

    # Check 3: Growth ratio ~3x
    gr = kv["growth_ratio_p50"]
    check3 = 1.5 < gr < 8
    checks.append(("Growth ratio ~3x", check3, f"actual p50={gr:.2f}x"))
    print(f"  {'✅' if check3 else '❌'} Growth ratio ~3x (actual p50={gr:.2f}x)")

    # Check 4: Total rows ≈ 24880
    check4 = abs(summary["total_rows"] - 24880) < 100
    checks.append(("Total rows ≈ 24880", check4, f"actual={summary['total_rows']}"))
    print(f"  {'✅' if check4 else '❌'} Total rows ≈ 24880 (actual={summary['total_rows']})")

    # Check 5: L0+L1 > 50% of first turn for SWE-bench
    sb_first = [r for r in per_row if r["session_id"].startswith("swebench") and r["turn_index"] == 0]
    if sb_first:
        l0l1_pct = sum(r["l0_tokens"] + r["l1_tokens"] for r in sb_first) / sum(r["total_tokens"] for r in sb_first) * 100
        check5 = l0l1_pct > 50
        checks.append(("SWE-bench L0+L1 > 50%", check5, f"actual={l0l1_pct:.1f}%"))
        print(f"  {'✅' if check5 else '❌'} SWE-bench L0+L1 > 50% of first turn (actual={l0l1_pct:.1f}%)")

    all_pass = all(c[1] for c in checks)
    print(f"\n  Overall: {'✅ ALL CHECKS PASSED' if all_pass else '❌ SOME CHECKS FAILED'}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
