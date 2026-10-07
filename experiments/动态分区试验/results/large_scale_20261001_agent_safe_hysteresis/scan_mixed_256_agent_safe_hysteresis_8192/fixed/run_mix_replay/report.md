# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.251**
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
| TTFT_ms | 2956.200 | 9724.519 | 9883.463 | 3486.414 | 256 |
| TPOT_ms | 263.967 | 403.869 | 418.785 | 262.875 | 256 |
| e2e_ms | 6836.787 | 15518.427 | 15564.103 | 7692.418 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.763 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.695 |
| cached/prompt | 712704 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 949.311 / 1034.493 |
| req/s | 3.357 |
| output tok/s | 53.717 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.837 |
| per_req_hit p50/p90 | 0.925 / 0.987 |
| TTFT_ms p50/p90 | 989.718 / 4756.879 |
| TPOT_ms p50 | 132.590 |
| cached/prompt | 659200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9762.011 / 10985.563 |
| TPOT_ms p50 | 413.146 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.863 |
| per_req_hit p50/p90 | 0.937 / 0.987 |
| TTFT_ms p50/p90 | 787.776 / 4694.176 |
| TPOT_ms p50 | 128.932 |
| cached/prompt | 653568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.364 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 3140.197 / 9726.782 |
| TPOT_ms p50 | 317.225 |
| cached/prompt | 53504 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3346.825 / 9874.873 |
| TPOT_ms p50 | 380.679 |
| cached/prompt | 0 / 30741 |
