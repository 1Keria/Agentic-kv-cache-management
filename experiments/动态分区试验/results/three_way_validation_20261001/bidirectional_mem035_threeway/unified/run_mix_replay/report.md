# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **451.136**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 275 |
| n_ok | 275 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2670.912 | 17124.696 | 21537.625 | 6075.145 | 275 |
| TPOT_ms | 140.345 | 292.136 | 665.760 | 178.919 | 275 |
| e2e_ms | 5126.112 | 21129.487 | 25971.396 | 8937.848 | 275 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.605 |
| per_req_hit p50/p90 | 0.171 / 0.987 |
| cold_miss_rate | 0.491 |
| cached/prompt | 5616640 / 9285414 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.048 / 1.484 |
| req/s | 0.610 |
| output tok/s | 9.753 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.689 |
| per_req_hit p50/p90 | 0.937 / 0.989 |
| TTFT_ms p50/p90 | 535.110 / 14178.072 |
| TPOT_ms p50 | 128.341 |
| cached/prompt | 5616640 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 4426.378 / 11444.455 |
| TPOT_ms p50 | 135.221 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.695 |
| per_req_hit p50/p90 | 0.948 / 0.989 |
| TTFT_ms p50/p90 | 532.090 / 15053.355 |
| TPOT_ms p50 | 128.152 |
| cached/prompt | 5608192 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 64 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13651.233 / 18379.697 |
| TPOT_ms p50 | 195.251 |
| cached/prompt | 0 / 1129582 |

## Request turn0

| metric | value |
|---|---|
| n | 16 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13504.879 / 16384.628 |
| TPOT_ms p50 | 244.712 |
| cached/prompt | 0 / 271218 |
