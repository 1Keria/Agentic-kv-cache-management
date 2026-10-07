# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **356.813**
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
| TTFT_ms | 774.285 | 3125.350 | 5808.360 | 1431.024 | 1261 |
| TPOT_ms | 159.902 | 344.539 | 397.363 | 200.500 | 1261 |
| e2e_ms | 4824.519 | 6884.908 | 7872.754 | 4639.027 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.877 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.653 |
| cached/prompt | 7823360 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.715 / 564.612 |
| req/s | 3.534 |
| output tok/s | 56.545 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.925 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 463.507 / 2289.828 |
| TPOT_ms p50 | 126.712 |
| cached/prompt | 7542272 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 1729.975 / 5133.232 |
| TPOT_ms p50 | 312.683 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.933 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 459.404 / 2248.709 |
| TPOT_ms p50 | 126.530 |
| cached/prompt | 7536640 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.369 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 915.237 / 3131.621 |
| TPOT_ms p50 | 169.451 |
| cached/prompt | 281088 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2154.993 / 3235.635 |
| TPOT_ms p50 | 218.356 |
| cached/prompt | 0 / 174542 |
