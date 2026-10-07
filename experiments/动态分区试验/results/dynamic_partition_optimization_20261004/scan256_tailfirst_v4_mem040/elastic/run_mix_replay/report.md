# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.358**
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
| TTFT_ms | 2811.756 | 9837.975 | 10033.012 | 3404.767 | 256 |
| TPOT_ms | 166.510 | 396.683 | 420.185 | 230.886 | 256 |
| e2e_ms | 6431.815 | 14475.787 | 15553.010 | 7098.939 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.794 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.648 |
| cached/prompt | 741632 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1193.818 / 1278.608 |
| req/s | 3.443 |
| output tok/s | 55.084 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.865 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2224.082 / 3929.918 |
| TPOT_ms p50 | 128.923 |
| cached/prompt | 681216 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9877.496 / 11091.419 |
| TPOT_ms p50 | 405.410 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.892 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2191.898 / 3241.357 |
| TPOT_ms p50 | 126.111 |
| cached/prompt | 675584 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.411 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 2899.673 / 9860.387 |
| TPOT_ms p50 | 246.257 |
| cached/prompt | 60416 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3346.983 / 9999.306 |
| TPOT_ms p50 | 372.991 |
| cached/prompt | 0 / 30741 |
