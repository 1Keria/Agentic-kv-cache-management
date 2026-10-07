# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **347.889**
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
| TTFT_ms | 623.447 | 2946.450 | 5681.505 | 1177.824 | 1261 |
| TPOT_ms | 182.326 | 402.763 | 473.579 | 226.792 | 1261 |
| e2e_ms | 4558.917 | 7780.426 | 10105.599 | 4806.494 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.901 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.633 |
| cached/prompt | 8036352 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.730 / 607.409 |
| req/s | 3.625 |
| output tok/s | 57.995 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 442.881 / 1142.098 |
| TPOT_ms p50 | 126.890 |
| cached/prompt | 7719424 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.227 |
| TTFT_ms p50/p90 | 955.766 / 4763.898 |
| TPOT_ms p50 | 334.486 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 439.318 / 901.594 |
| TPOT_ms p50 | 126.648 |
| cached/prompt | 7702528 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.416 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 682.099 / 3076.361 |
| TPOT_ms p50 | 221.846 |
| cached/prompt | 316928 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 721.101 / 3130.874 |
| TPOT_ms p50 | 300.961 |
| cached/prompt | 0 / 174542 |
