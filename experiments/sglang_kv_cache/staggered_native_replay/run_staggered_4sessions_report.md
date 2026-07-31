# Staggered replay report

- model: `/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- base_url: `http://127.0.0.1:8004`
- mode: `native_sglang_no_prefix_family`
- dry_run: `False`
- wall_clock_s: **14.5250**

## A. Integrity

| metric | value |
|---|---|
| n_sessions | 4 |
| n_turns_planned | 24 |
| n_requests_ok | 18 |
| n_requests_err | 1 |
| error_breakdown | `{"context_too_long": 1}` |

## B. Session-start (turn0, primary)

| metric | value |
|---|---|
| ttft p50 / p90 / mean / max (ms) | 962.326 / 1094.117 / 950.197 / 1094.117 |
| token_weighted_cache_hit | 23.93% |
| per_req_hit_rate p50 | 25.30% |
| cold_miss_rate | 33.33% |
| SLO violation @100ms | 100.00% |
| SLO violation @200ms | 100.00% |
| SLO violation @500ms | 100.00% |
| cached / prompt tokens | 15646 / 65393 |

## C. Within-session (turn≥1)

| metric | value |
|---|---|
| ttft p50 / p90 / mean (ms) | 89.7880 / 129.468 / 133.227 |
| token_weighted_cache_hit | 98.72% |
| per_req_hit_rate p50 | 98.90% |
| ttft_speedup_vs_session_start | 10.7180× |
| SLO violation @500ms | 6.67% |

## D. Global (all OK requests)

| metric | value |
|---|---|
| ttft p50 / p90 / mean (ms) | 96.4880 / 831.029 / 269.388 |
| e2e p50 / p90 (ms) | 665.488 / 1525.410 |
| token_weighted_cache_hit | 86.62% |
| per_req_hit_rate p50 / p90 | 98.60% / 99.60% |
| avoided_prefill_tokens | 350138 |
| completion_tokens_sum | 1152 |

## E. Schedule / concurrency

- start_jitter_ms p50/p90/max: 0.8160 / 0.8240 / 0.8240

| idx | session | t_start | turn0 TTFT | turn0 hit | jitter_ms | ok/err | window |
|---|---|---|---|---|---|---|---|
| 0 | `…ch__astropy__astropy-12907__minimax` | 0.000 | 794.148 | 0.00% | 0.2300 | 6/0 | 0.0002→8.6161 |
| 1 | `…ench__django__django-15103__minimax` | 2.0000 | — | — | 0.8160 | 0/1 | 2.0008→2.0008 |
| 2 | `…ebench__sympy__sympy-19346__minimax` | 4.0000 | 962.326 | 30.04% | 0.6210 | 6/0 | 4.0006→14.4839 |
| 3 | `…h__pytest-dev__pytest-7982__minimax` | 6.0000 | 1094.117 | 25.33% | 0.8240 | 6/0 | 6.0008→14.5249 |

## F. Prefix Family (optional)

| metric | value |
|---|---|
| source | `/tmp/agentkv_pf_shadow_summary.json` |
| historical_depth | — |
| physical_depth | — |
| fork_gap | — |
| retained_shared_ratio | — |

## Errors

| session | turn | class | error |
|---|---|---|---|
| `…ango__django-15103__minimax` | 0 | `context_too_long` | BadRequestError: Error code: 400 - {'object': 'error', 'message': "The input (48320 tokens) is longer than the model'... |

