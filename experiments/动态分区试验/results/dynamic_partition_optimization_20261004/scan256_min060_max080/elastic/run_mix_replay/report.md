# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **79.401**
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
| TTFT_ms | 4278.920 | 9426.234 | 10922.004 | 4490.753 | 256 |
| TPOT_ms | 163.573 | 308.608 | 394.621 | 203.915 | 256 |
| e2e_ms | 7028.710 | 11386.176 | 13202.115 | 7753.401 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.791 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.668 |
| cached/prompt | 739072 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1688.856 / 1773.461 |
| req/s | 3.224 |
| output tok/s | 51.587 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.865 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2287.533 / 5139.356 |
| TPOT_ms p50 | 125.441 |
| cached/prompt | 681216 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9430.861 / 12085.151 |
| TPOT_ms p50 | 142.246 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.892 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 1225.479 / 5033.947 |
| TPOT_ms p50 | 125.124 |
| cached/prompt | 675584 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.394 |
| per_req_hit p50/p90 | 0.000 / 0.636 |
| TTFT_ms p50/p90 | 5161.632 / 9563.226 |
| TPOT_ms p50 | 236.963 |
| cached/prompt | 57856 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5624.417 / 9570.252 |
| TPOT_ms p50 | 285.721 |
| cached/prompt | 0 / 30741 |
