# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **357.634**
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
| TTFT_ms | 703.083 | 2998.039 | 5711.270 | 1316.520 | 1261 |
| TPOT_ms | 181.356 | 446.850 | 529.854 | 224.302 | 1261 |
| e2e_ms | 4606.111 | 8087.529 | 9250.509 | 4905.354 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.868 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.659 |
| cached/prompt | 7743232 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.672 / 534.484 |
| req/s | 3.526 |
| output tok/s | 56.415 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.914 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 469.322 / 2162.160 |
| TPOT_ms p50 | 126.147 |
| cached/prompt | 7451904 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 891.877 / 4792.650 |
| TPOT_ms p50 | 305.935 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.922 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 456.631 / 1948.876 |
| TPOT_ms p50 | 125.597 |
| cached/prompt | 7446272 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.383 |
| per_req_hit p50/p90 | 0.000 / 0.615 |
| TTFT_ms p50/p90 | 802.868 / 3020.339 |
| TPOT_ms p50 | 192.914 |
| cached/prompt | 291328 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 825.364 / 3183.923 |
| TPOT_ms p50 | 283.308 |
| cached/prompt | 0 / 174542 |
