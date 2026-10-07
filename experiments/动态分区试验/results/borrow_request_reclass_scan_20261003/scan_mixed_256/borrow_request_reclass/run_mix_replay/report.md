# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.249**
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
| TTFT_ms | 3166.613 | 8645.791 | 8776.792 | 3478.552 | 256 |
| TPOT_ms | 399.635 | 866.427 | 916.694 | 395.173 | 256 |
| e2e_ms | 10210.876 | 22548.196 | 23108.391 | 9801.316 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.783 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.664 |
| cached/prompt | 731136 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 964.711 / 1049.983 |
| req/s | 3.448 |
| output tok/s | 55.166 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.928 / 0.986 |
| TTFT_ms p50/p90 | 515.400 / 2612.277 |
| TPOT_ms p50 | 126.897 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 4232.827 / 7602.856 |
| TPOT_ms p50 | 917.051 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 469.146 / 2442.851 |
| TPOT_ms p50 | 122.552 |
| cached/prompt | 669952 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3304.389 / 8648.360 |
| TPOT_ms p50 | 402.848 |
| cached/prompt | 58368 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3799.278 / 8657.338 |
| TPOT_ms p50 | 423.596 |
| cached/prompt | 0 / 30741 |
