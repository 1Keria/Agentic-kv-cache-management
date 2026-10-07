# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **363.897**
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
| TTFT_ms | 819.663 | 5083.610 | 12725.578 | 2067.437 | 1261 |
| TPOT_ms | 194.513 | 609.142 | 837.507 | 269.380 | 1261 |
| e2e_ms | 4329.961 | 14865.749 | 18670.878 | 6377.515 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.822 |
| per_req_hit p50/p90 | 0.000 / 0.955 |
| cold_miss_rate | 0.776 |
| cached/prompt | 7326464 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.634 / 1.215 |
| req/s | 3.465 |
| output tok/s | 55.444 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.968 / 0.991 |
| TTFT_ms p50/p90 | 469.380 / 2935.197 |
| TPOT_ms p50 | 130.122 |
| cached/prompt | 7221504 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 888.531 / 3305.262 |
| TPOT_ms p50 | 493.034 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.894 |
| per_req_hit p50/p90 | 0.969 / 0.992 |
| TTFT_ms p50/p90 | 465.138 / 2770.395 |
| TPOT_ms p50 | 129.669 |
| cached/prompt | 7215872 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.138 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 931.910 / 5184.350 |
| TPOT_ms p50 | 206.844 |
| cached/prompt | 104960 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1753.195 / 6434.785 |
| TPOT_ms p50 | 278.337 |
| cached/prompt | 0 / 174542 |
