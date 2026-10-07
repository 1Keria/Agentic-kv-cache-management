# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse_calibrated`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **620.925**
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
| TTFT_ms | 14421.677 | 19757.746 | 25201.554 | 13719.350 | 1277 |
| TPOT_ms | 144.994 | 372.246 | 631.991 | 207.895 | 1277 |
| e2e_ms | 17599.399 | 23764.837 | 30070.427 | 17045.678 | 1277 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.432 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.930 |
| cached/prompt | 3976960 / 9195538 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.060 / 1.998 |
| req/s | 2.057 |
| output tok/s | 32.906 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.486 |
| per_req_hit p50/p90 | 0.000 / 0.987 |
| TTFT_ms p50/p90 | 8028.110 / 13682.588 |
| TPOT_ms p50 | 147.867 |
| cached/prompt | 3967744 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 12632.373 / 13505.180 |
| TPOT_ms p50 | 150.932 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.491 |
| per_req_hit p50/p90 | 0.000 / 0.987 |
| TTFT_ms p50/p90 | 7710.021 / 13783.921 |
| TPOT_ms p50 | 146.416 |
| cached/prompt | 3962112 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1066 |
| token_weighted_hit | 0.009 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15135.560 / 21428.353 |
| TPOT_ms p50 | 144.851 |
| cached/prompt | 9216 / 1039706 |

## Request turn0

| metric | value |
|---|---|
| n | 552 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 16117.244 / 20113.910 |
| TPOT_ms p50 | 181.814 |
| cached/prompt | 0 / 243357 |
