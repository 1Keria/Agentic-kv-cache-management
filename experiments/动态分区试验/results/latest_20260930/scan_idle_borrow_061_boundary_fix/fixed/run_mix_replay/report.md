# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.898**
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
| TTFT_ms | 3194.307 | 4529.032 | 8010.240 | 3168.957 | 256 |
| TPOT_ms | 144.861 | 413.024 | 421.829 | 242.850 | 256 |
| e2e_ms | 6362.965 | 9998.715 | 10021.727 | 7054.559 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.806 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.641 |
| cached/prompt | 752640 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 4929.131 / 5012.926 |
| req/s | 3.373 |
| output tok/s | 53.967 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2141.685 / 4224.453 |
| TPOT_ms p50 | 128.089 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.467 |
| TTFT_ms p50/p90 | 7916.401 / 8165.891 |
| TPOT_ms p50 | 341.047 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 1502.011 / 4097.001 |
| TPOT_ms p50 | 122.509 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.418 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3238.470 / 4529.276 |
| TPOT_ms p50 | 149.723 |
| cached/prompt | 61440 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3735.999 / 7870.601 |
| TPOT_ms p50 | 389.226 |
| cached/prompt | 0 / 30741 |
