# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30135`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **344.772**
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
| TTFT_ms | 661.700 | 3747.584 | 5164.429 | 1436.782 | 1261 |
| TPOT_ms | 150.353 | 253.157 | 354.478 | 171.007 | 1261 |
| e2e_ms | 3783.064 | 6456.944 | 7687.073 | 4172.896 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.901 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8031232 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.638 / 1.155 |
| req/s | 3.658 |
| output tok/s | 58.520 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 466.883 / 2241.254 |
| TPOT_ms p50 | 129.161 |
| cached/prompt | 7725824 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.181 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 2277.087 / 4671.236 |
| TPOT_ms p50 | 223.981 |
| cached/prompt | 14848 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.955 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 458.323 / 2168.728 |
| TPOT_ms p50 | 128.065 |
| cached/prompt | 7710976 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.401 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 736.857 / 3972.780 |
| TPOT_ms p50 | 153.423 |
| cached/prompt | 305408 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1802.073 / 4731.321 |
| TPOT_ms p50 | 163.762 |
| cached/prompt | 0 / 174542 |
