# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **79.492**
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
| TTFT_ms | 3306.912 | 7998.273 | 8701.739 | 3435.378 | 256 |
| TPOT_ms | 413.856 | 946.694 | 1055.202 | 454.637 | 256 |
| e2e_ms | 10107.121 | 22747.665 | 24670.296 | 10709.568 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.801 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.652 |
| cached/prompt | 748544 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 441.506 / 525.415 |
| req/s | 3.220 |
| output tok/s | 51.527 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 466.841 / 3683.400 |
| TPOT_ms p50 | 127.424 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 3708.994 / 6975.491 |
| TPOT_ms p50 | 1055.195 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 451.757 / 2864.778 |
| TPOT_ms p50 | 127.088 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.410 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3478.770 / 8003.108 |
| TPOT_ms p50 | 416.480 |
| cached/prompt | 60160 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3801.752 / 8007.569 |
| TPOT_ms p50 | 416.642 |
| cached/prompt | 0 / 30741 |
