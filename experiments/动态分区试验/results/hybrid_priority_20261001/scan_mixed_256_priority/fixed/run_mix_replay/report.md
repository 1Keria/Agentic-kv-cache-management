# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.42**
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
| TTFT_ms | 3076.896 | 5986.534 | 8151.529 | 3275.893 | 256 |
| TPOT_ms | 155.286 | 276.992 | 286.057 | 190.418 | 256 |
| e2e_ms | 7090.988 | 7962.757 | 10434.642 | 6322.581 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.797 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.676 |
| cached/prompt | 744192 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1028.591 / 1112.728 |
| req/s | 3.350 |
| output tok/s | 53.598 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2278.195 / 4956.070 |
| TPOT_ms p50 | 120.503 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 5991.197 / 8652.984 |
| TPOT_ms p50 | 142.127 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2262.866 / 4159.717 |
| TPOT_ms p50 | 120.017 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.361 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 3146.015 / 6123.464 |
| TPOT_ms p50 | 247.124 |
| cached/prompt | 52992 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3363.470 / 6134.554 |
| TPOT_ms p50 | 252.928 |
| cached/prompt | 0 / 30741 |
