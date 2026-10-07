# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.198**
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
| TTFT_ms | 2796.191 | 9117.371 | 9641.554 | 3480.728 | 256 |
| TPOT_ms | 181.873 | 397.683 | 420.996 | 236.328 | 256 |
| e2e_ms | 6639.645 | 13748.557 | 15149.824 | 7261.969 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.792 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.648 |
| cached/prompt | 739328 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 428.541 / 513.649 |
| req/s | 3.360 |
| output tok/s | 53.755 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.862 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 1640.521 / 4072.319 |
| TPOT_ms p50 | 138.913 |
| cached/prompt | 678400 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9129.390 / 10340.784 |
| TPOT_ms p50 | 406.689 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 925.478 / 3089.132 |
| TPOT_ms p50 | 132.979 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.415 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 2936.077 / 9120.609 |
| TPOT_ms p50 | 246.552 |
| cached/prompt | 60928 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3341.184 / 9263.981 |
| TPOT_ms p50 | 374.139 |
| cached/prompt | 0 / 30741 |
