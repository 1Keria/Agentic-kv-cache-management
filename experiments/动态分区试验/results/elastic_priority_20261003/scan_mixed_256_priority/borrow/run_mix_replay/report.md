# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30101`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **78.992**
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
| TTFT_ms | 3971.468 | 7837.690 | 9858.503 | 3877.657 | 256 |
| TPOT_ms | 145.054 | 386.106 | 485.811 | 211.366 | 256 |
| e2e_ms | 9077.914 | 9825.116 | 12286.718 | 7259.511 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.788 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.691 |
| cached/prompt | 736256 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1008.783 / 1093.841 |
| req/s | 3.241 |
| output tok/s | 51.853 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2637.592 / 4491.875 |
| TPOT_ms p50 | 118.656 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7686.104 / 10343.722 |
| TPOT_ms p50 | 151.820 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2323.750 / 3970.377 |
| TPOT_ms p50 | 118.037 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.323 |
| per_req_hit p50/p90 | 0.000 / 0.547 |
| TTFT_ms p50/p90 | 4561.004 / 7838.416 |
| TPOT_ms p50 | 158.888 |
| cached/prompt | 47360 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5044.102 / 7846.130 |
| TPOT_ms p50 | 252.617 |
| cached/prompt | 0 / 30741 |
