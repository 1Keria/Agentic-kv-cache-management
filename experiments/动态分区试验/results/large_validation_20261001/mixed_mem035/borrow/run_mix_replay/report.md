# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **498.782**
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
| TTFT_ms | 14549.975 | 19711.726 | 22821.785 | 13435.558 | 1261 |
| TPOT_ms | 135.769 | 236.986 | 617.468 | 162.558 | 1261 |
| e2e_ms | 17742.517 | 22969.166 | 26191.350 | 16036.479 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.643 |
| per_req_hit p50/p90 | 0.000 / 0.192 |
| cold_miss_rate | 0.876 |
| cached/prompt | 5729536 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.648 / 51.538 |
| req/s | 2.528 |
| output tok/s | 40.451 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.703 |
| per_req_hit p50/p90 | 0.912 / 0.989 |
| TTFT_ms p50/p90 | 583.390 / 17343.918 |
| TPOT_ms p50 | 128.154 |
| cached/prompt | 5729536 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.211 / 0.227 |
| TTFT_ms p50/p90 | 13893.013 / 17105.394 |
| TPOT_ms p50 | 143.987 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.708 |
| per_req_hit p50/p90 | 0.923 / 0.989 |
| TTFT_ms p50/p90 | 557.545 / 17433.911 |
| TPOT_ms p50 | 127.966 |
| cached/prompt | 5718272 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15828.316 / 20168.553 |
| TPOT_ms p50 | 136.507 |
| cached/prompt | 0 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 16835.954 / 20833.797 |
| TPOT_ms p50 | 138.998 |
| cached/prompt | 0 / 174542 |
