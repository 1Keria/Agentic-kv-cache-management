# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **68.327**
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
| TTFT_ms | 2726.938 | 4157.322 | 4451.560 | 2344.031 | 256 |
| TPOT_ms | 253.692 | 386.514 | 404.696 | 243.891 | 256 |
| e2e_ms | 6263.874 | 9295.191 | 9327.183 | 6246.288 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.807 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.641 |
| cached/prompt | 754176 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 410.071 / 495.409 |
| req/s | 3.747 |
| output tok/s | 59.947 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2156.802 / 4108.741 |
| TPOT_ms p50 | 125.447 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.467 |
| TTFT_ms p50/p90 | 3552.820 / 4001.421 |
| TPOT_ms p50 | 327.045 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2140.128 / 4085.172 |
| TPOT_ms p50 | 118.710 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.429 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3114.144 / 4157.372 |
| TPOT_ms p50 | 297.894 |
| cached/prompt | 62976 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3550.039 / 4175.918 |
| TPOT_ms p50 | 358.855 |
| cached/prompt | 0 / 30741 |
