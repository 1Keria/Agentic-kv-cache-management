# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **363.879**
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
| TTFT_ms | 675.578 | 3427.138 | 5964.449 | 1425.700 | 1261 |
| TPOT_ms | 174.487 | 391.326 | 479.318 | 221.094 | 1261 |
| e2e_ms | 4935.415 | 8183.944 | 8538.342 | 4963.203 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.840 |
| per_req_hit p50/p90 | 0.000 / 0.962 |
| cold_miss_rate | 0.658 |
| cached/prompt | 7491328 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.705 / 3138.642 |
| req/s | 3.465 |
| output tok/s | 55.447 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.882 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 464.734 / 2610.758 |
| TPOT_ms p50 | 124.576 |
| cached/prompt | 7196416 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 863.913 / 7335.072 |
| TPOT_ms p50 | 282.123 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.891 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 463.607 / 2470.886 |
| TPOT_ms p50 | 124.010 |
| cached/prompt | 7190784 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.387 |
| per_req_hit p50/p90 | 0.000 / 0.615 |
| TTFT_ms p50/p90 | 722.939 / 4273.138 |
| TPOT_ms p50 | 184.020 |
| cached/prompt | 294912 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 784.228 / 5419.069 |
| TPOT_ms p50 | 282.149 |
| cached/prompt | 0 / 174542 |
