# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **109.909**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 256 |
| n_ok | 256 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 9811.544 | 20861.821 | 21548.418 | 10121.681 | 256 |
| TPOT_ms | 203.537 | 416.524 | 591.453 | 240.490 | 256 |
| e2e_ms | 13612.826 | 22956.495 | 23840.618 | 13969.523 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.335 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.922 |
| cached/prompt | 312832 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 392.732 / 477.771 |
| req/s | 2.329 |
| output tok/s | 37.267 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| TTFT_ms p50/p90 | 3964.016 / 10010.459 |
| TPOT_ms p50 | 131.054 |
| cached/prompt | 312832 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 20622.717 / 21791.063 |
| TPOT_ms p50 | 142.644 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.413 |
| per_req_hit p50/p90 | 0.111 / 0.966 |
| TTFT_ms p50/p90 | 3954.202 / 8740.749 |
| TPOT_ms p50 | 129.094 |
| cached/prompt | 312832 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11728.668 / 20865.175 |
| TPOT_ms p50 | 252.557 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14676.814 / 21004.338 |
| TPOT_ms p50 | 267.699 |
| cached/prompt | 0 / 30741 |
