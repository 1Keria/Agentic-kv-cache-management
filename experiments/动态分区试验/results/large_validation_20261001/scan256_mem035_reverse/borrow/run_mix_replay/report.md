# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **105.465**
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
| TTFT_ms | 9000.679 | 22311.703 | 27880.691 | 10541.629 | 256 |
| TPOT_ms | 255.916 | 407.512 | 663.097 | 271.778 | 256 |
| e2e_ms | 13199.017 | 28333.973 | 32575.275 | 14890.074 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.519 |
| per_req_hit p50/p90 | 0.000 / 0.211 |
| cold_miss_rate | 0.883 |
| cached/prompt | 484608 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1127.199 / 1212.324 |
| req/s | 2.427 |
| output tok/s | 38.837 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.607 |
| per_req_hit p50/p90 | 0.440 / 0.977 |
| TTFT_ms p50/p90 | 2312.456 / 7748.904 |
| TPOT_ms p50 | 124.469 |
| cached/prompt | 477440 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 22514.636 / 23211.636 |
| TPOT_ms p50 | 525.297 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.631 |
| per_req_hit p50/p90 | 0.749 / 0.979 |
| TTFT_ms p50/p90 | 1423.057 / 6441.183 |
| TPOT_ms p50 | 120.450 |
| cached/prompt | 477440 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.049 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13214.432 / 22508.075 |
| TPOT_ms p50 | 264.965 |
| cached/prompt | 7168 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15145.452 / 22730.828 |
| TPOT_ms p50 | 347.363 |
| cached/prompt | 0 / 30741 |
