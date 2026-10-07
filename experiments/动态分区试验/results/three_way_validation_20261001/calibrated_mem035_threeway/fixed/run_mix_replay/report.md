# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse_calibrated`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **652.049**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1277 |
| n_ok | 1277 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 12008.036 | 18416.144 | 21466.445 | 12019.314 | 1277 |
| TPOT_ms | 146.848 | 296.931 | 769.050 | 198.604 | 1277 |
| e2e_ms | 15155.240 | 21760.209 | 26672.881 | 15196.975 | 1277 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.263 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.964 |
| cached/prompt | 2414080 / 9195538 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.123 / 2.108 |
| req/s | 1.958 |
| output tok/s | 31.335 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.296 |
| per_req_hit p50/p90 | 0.000 / 0.973 |
| TTFT_ms p50/p90 | 6786.130 / 10826.842 |
| TPOT_ms p50 | 179.166 |
| cached/prompt | 2414080 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.214 |
| TTFT_ms p50/p90 | 9634.346 / 11419.172 |
| TPOT_ms p50 | 135.926 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.298 |
| per_req_hit p50/p90 | 0.000 / 0.974 |
| TTFT_ms p50/p90 | 6479.816 / 10688.144 |
| TPOT_ms p50 | 184.806 |
| cached/prompt | 2408448 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1066 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13337.475 / 18774.474 |
| TPOT_ms p50 | 145.179 |
| cached/prompt | 0 / 1039706 |

## Request turn0

| metric | value |
|---|---|
| n | 552 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15400.979 / 19821.093 |
| TPOT_ms p50 | 161.379 |
| cached/prompt | 0 / 243357 |
