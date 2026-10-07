# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **71.792**
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
| TTFT_ms | 2727.068 | 5431.833 | 6009.734 | 3301.765 | 256 |
| TPOT_ms | 142.048 | 356.234 | 366.446 | 211.011 | 256 |
| e2e_ms | 5105.279 | 10456.377 | 10495.432 | 6677.948 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.806 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.641 |
| cached/prompt | 752896 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 406.340 / 490.583 |
| req/s | 3.566 |
| output tok/s | 57.054 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.877 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2276.975 / 5200.446 |
| TPOT_ms p50 | 121.018 |
| cached/prompt | 690176 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.153 |
| per_req_hit p50/p90 | 0.146 / 0.210 |
| TTFT_ms p50/p90 | 5946.595 / 6495.901 |
| TPOT_ms p50 | 274.664 |
| cached/prompt | 4608 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2264.639 / 4886.664 |
| TPOT_ms p50 | 120.805 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.427 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 4569.341 / 5433.680 |
| TPOT_ms p50 | 150.782 |
| cached/prompt | 62720 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5051.772 / 5455.818 |
| TPOT_ms p50 | 336.379 |
| cached/prompt | 0 / 30741 |
