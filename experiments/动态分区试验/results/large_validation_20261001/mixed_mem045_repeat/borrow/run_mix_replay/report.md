# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.919**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1261 |
| n_ok | 1261 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 689.999 | 3123.899 | 5956.394 | 1336.287 | 1261 |
| TPOT_ms | 142.108 | 310.784 | 467.827 | 181.310 | 1261 |
| e2e_ms | 3665.353 | 7907.724 | 8281.257 | 4237.240 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.894 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.634 |
| cached/prompt | 7969792 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.707 / 3769.322 |
| req/s | 3.614 |
| output tok/s | 57.824 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.939 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 464.402 / 1513.019 |
| TPOT_ms p50 | 124.462 |
| cached/prompt | 7661056 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| TTFT_ms p50/p90 | 854.332 / 5829.723 |
| TPOT_ms p50 | 231.673 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.948 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 458.678 / 1237.202 |
| TPOT_ms p50 | 123.552 |
| cached/prompt | 7652608 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.405 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 749.218 / 4236.116 |
| TPOT_ms p50 | 149.764 |
| cached/prompt | 308736 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 774.678 / 5523.815 |
| TPOT_ms p50 | 182.204 |
| cached/prompt | 0 / 174542 |
