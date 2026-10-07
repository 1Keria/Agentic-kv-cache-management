# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **353.447**
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
| TTFT_ms | 751.043 | 3493.991 | 4336.014 | 1412.790 | 1261 |
| TPOT_ms | 141.819 | 249.351 | 447.166 | 167.222 | 1261 |
| e2e_ms | 3528.023 | 6365.829 | 7791.522 | 4088.350 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.891 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.641 |
| cached/prompt | 7948800 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.685 / 589.455 |
| req/s | 3.568 |
| output tok/s | 57.084 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 478.150 / 2277.887 |
| TPOT_ms p50 | 126.693 |
| cached/prompt | 7640576 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 1774.716 / 3724.470 |
| TPOT_ms p50 | 211.746 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 476.792 / 2244.921 |
| TPOT_ms p50 | 125.247 |
| cached/prompt | 7637760 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.405 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 894.618 / 3536.576 |
| TPOT_ms p50 | 146.403 |
| cached/prompt | 308224 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1595.394 / 3952.132 |
| TPOT_ms p50 | 162.329 |
| cached/prompt | 0 / 174542 |
