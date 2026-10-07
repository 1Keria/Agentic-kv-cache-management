# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **364.081**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1261 |
| n_ok | 1261 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 671.093 | 3787.587 | 9038.207 | 1633.425 | 1261 |
| TPOT_ms | 173.048 | 352.618 | 481.218 | 208.898 | 1261 |
| e2e_ms | 3808.149 | 8750.918 | 10996.820 | 4975.788 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.837 |
| per_req_hit p50/p90 | 0.000 / 0.959 |
| cold_miss_rate | 0.740 |
| cached/prompt | 7464192 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.680 / 599.086 |
| req/s | 3.463 |
| output tok/s | 55.416 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.894 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 484.128 / 2811.181 |
| TPOT_ms p50 | 130.790 |
| cached/prompt | 7288320 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 917.604 / 10655.761 |
| TPOT_ms p50 | 213.123 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.902 |
| per_req_hit p50/p90 | 0.970 / 0.992 |
| TTFT_ms p50/p90 | 481.255 / 2502.924 |
| TPOT_ms p50 | 129.844 |
| cached/prompt | 7279872 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.231 |
| per_req_hit p50/p90 | 0.000 / 0.429 |
| TTFT_ms p50/p90 | 763.189 / 3941.717 |
| TPOT_ms p50 | 181.448 |
| cached/prompt | 175872 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 758.350 / 5915.722 |
| TPOT_ms p50 | 205.507 |
| cached/prompt | 0 / 174542 |
