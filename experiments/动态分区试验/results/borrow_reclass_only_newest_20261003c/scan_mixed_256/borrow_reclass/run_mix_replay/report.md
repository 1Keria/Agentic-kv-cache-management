# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.868**
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
| TTFT_ms | 3647.432 | 9071.314 | 9482.770 | 4011.469 | 256 |
| TPOT_ms | 246.420 | 354.038 | 478.137 | 230.403 | 256 |
| e2e_ms | 8706.715 | 14031.300 | 17132.983 | 7697.921 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.787 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.645 |
| cached/prompt | 735488 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 397.688 / 482.900 |
| req/s | 3.288 |
| output tok/s | 52.602 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.933 / 0.987 |
| TTFT_ms p50/p90 | 807.179 / 4914.691 |
| TPOT_ms p50 | 128.662 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9110.676 / 9436.761 |
| TPOT_ms p50 | 316.084 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.945 / 0.987 |
| TTFT_ms p50/p90 | 606.891 / 4858.593 |
| TPOT_ms p50 | 127.486 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.427 |
| per_req_hit p50/p90 | 0.000 / 0.661 |
| TTFT_ms p50/p90 | 3859.541 / 9073.130 |
| TPOT_ms p50 | 252.219 |
| cached/prompt | 62720 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 4783.566 / 9452.959 |
| TPOT_ms p50 | 281.510 |
| cached/prompt | 0 / 30741 |
