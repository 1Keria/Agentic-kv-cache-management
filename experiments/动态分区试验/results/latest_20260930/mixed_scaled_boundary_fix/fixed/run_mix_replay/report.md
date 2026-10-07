# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.909**
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
| TTFT_ms | 704.163 | 3086.425 | 5278.248 | 1200.717 | 1261 |
| TPOT_ms | 164.068 | 361.804 | 423.367 | 213.789 | 1261 |
| e2e_ms | 4745.893 | 7258.222 | 8376.820 | 4621.336 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.658 |
| cached/prompt | 7770880 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.653 / 21.205 |
| req/s | 3.553 |
| output tok/s | 56.848 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.917 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 444.312 / 1842.863 |
| TPOT_ms p50 | 128.550 |
| cached/prompt | 7481856 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.343 |
| TTFT_ms p50/p90 | 1105.225 / 3883.562 |
| TPOT_ms p50 | 354.303 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.926 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 439.603 / 1541.767 |
| TPOT_ms p50 | 128.348 |
| cached/prompt | 7476224 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.380 |
| per_req_hit p50/p90 | 0.000 / 0.615 |
| TTFT_ms p50/p90 | 783.070 / 3158.967 |
| TPOT_ms p50 | 181.169 |
| cached/prompt | 289024 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 793.331 / 3427.075 |
| TPOT_ms p50 | 312.883 |
| cached/prompt | 0 / 174542 |
