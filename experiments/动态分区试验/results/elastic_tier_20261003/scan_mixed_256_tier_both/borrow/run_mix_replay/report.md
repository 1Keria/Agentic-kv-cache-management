# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30104`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.243**
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
| TTFT_ms | 2661.713 | 14498.074 | 16608.724 | 4771.774 | 256 |
| TPOT_ms | 395.366 | 838.417 | 872.463 | 430.588 | 256 |
| e2e_ms | 9571.137 | 20708.725 | 23542.135 | 11661.176 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.802 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.648 |
| cached/prompt | 749312 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 393.096 / 478.885 |
| req/s | 3.151 |
| output tok/s | 50.417 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 438.856 / 3919.358 |
| TPOT_ms p50 | 131.651 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 3715.113 / 12266.466 |
| TPOT_ms p50 | 891.506 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 429.337 / 3623.818 |
| TPOT_ms p50 | 127.439 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.415 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3286.788 / 14599.983 |
| TPOT_ms p50 | 433.143 |
| cached/prompt | 60928 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5544.273 / 16463.161 |
| TPOT_ms p50 | 702.053 |
| cached/prompt | 0 / 30741 |
