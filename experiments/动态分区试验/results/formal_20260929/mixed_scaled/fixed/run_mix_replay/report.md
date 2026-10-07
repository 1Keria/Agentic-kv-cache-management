# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.421**
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
| TTFT_ms | 761.133 | 3436.650 | 4416.032 | 1435.980 | 1261 |
| TPOT_ms | 144.880 | 377.522 | 498.781 | 195.482 | 1261 |
| e2e_ms | 4606.880 | 6965.451 | 8736.637 | 4563.684 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.887 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.661 |
| cached/prompt | 7907840 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.686 / 1045.527 |
| req/s | 3.619 |
| output tok/s | 57.907 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 467.805 / 2248.062 |
| TPOT_ms p50 | 126.022 |
| cached/prompt | 7623424 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 927.174 / 4277.963 |
| TPOT_ms p50 | 217.608 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.944 |
| per_req_hit p50/p90 | 0.972 / 0.991 |
| TTFT_ms p50/p90 | 465.082 / 2168.474 |
| TPOT_ms p50 | 125.795 |
| cached/prompt | 7620608 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.373 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 862.786 / 3663.968 |
| TPOT_ms p50 | 146.529 |
| cached/prompt | 284416 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1372.849 / 3982.446 |
| TPOT_ms p50 | 184.286 |
| cached/prompt | 0 / 174542 |
