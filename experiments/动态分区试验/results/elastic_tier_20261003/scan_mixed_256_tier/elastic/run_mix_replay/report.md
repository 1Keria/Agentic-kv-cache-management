# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30103`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.718**
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
| TTFT_ms | 2918.280 | 7461.239 | 8163.480 | 3296.425 | 256 |
| TPOT_ms | 249.402 | 430.952 | 590.069 | 231.212 | 256 |
| e2e_ms | 7064.201 | 14493.816 | 17607.183 | 6995.824 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.783 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.660 |
| cached/prompt | 731136 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 384.023 / 468.762 |
| req/s | 3.521 |
| output tok/s | 56.327 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 1129.516 / 3955.333 |
| TPOT_ms p50 | 130.058 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 7503.793 / 8061.348 |
| TPOT_ms p50 | 439.479 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 711.529 / 3053.113 |
| TPOT_ms p50 | 127.911 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3277.345 / 7462.414 |
| TPOT_ms p50 | 253.246 |
| cached/prompt | 58368 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3678.782 / 7604.680 |
| TPOT_ms p50 | 265.823 |
| cached/prompt | 0 / 30741 |
