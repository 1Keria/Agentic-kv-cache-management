# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse_calibrated`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **603.533**
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
| TTFT_ms | 11912.400 | 18693.118 | 21325.628 | 11772.343 | 1277 |
| TPOT_ms | 149.033 | 350.553 | 859.150 | 214.075 | 1277 |
| e2e_ms | 15209.908 | 23038.572 | 25554.463 | 15197.540 | 1277 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.402 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.933 |
| cached/prompt | 3693568 / 9195538 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.026 / 1.909 |
| req/s | 2.116 |
| output tok/s | 33.854 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.453 |
| per_req_hit p50/p90 | 0.000 / 0.983 |
| TTFT_ms p50/p90 | 7210.655 / 11650.553 |
| TPOT_ms p50 | 140.732 |
| cached/prompt | 3693568 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 10873.828 / 13239.435 |
| TPOT_ms p50 | 129.450 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.457 |
| per_req_hit p50/p90 | 0.000 / 0.984 |
| TTFT_ms p50/p90 | 7028.461 / 11408.320 |
| TPOT_ms p50 | 141.356 |
| cached/prompt | 3690752 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1066 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12640.013 / 18998.109 |
| TPOT_ms p50 | 149.137 |
| cached/prompt | 0 / 1039706 |

## Request turn0

| metric | value |
|---|---|
| n | 552 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13471.639 / 19859.023 |
| TPOT_ms p50 | 162.171 |
| cached/prompt | 0 / 243357 |
