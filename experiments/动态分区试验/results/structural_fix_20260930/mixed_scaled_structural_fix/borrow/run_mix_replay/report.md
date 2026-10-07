# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **352.95**
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
| TTFT_ms | 750.148 | 3253.695 | 4602.889 | 1300.225 | 1261 |
| TPOT_ms | 143.404 | 266.954 | 323.965 | 170.765 | 1261 |
| e2e_ms | 3607.363 | 6259.555 | 7706.726 | 4032.460 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.890 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.642 |
| cached/prompt | 7936512 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.623 / 1.051 |
| req/s | 3.573 |
| output tok/s | 57.164 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 470.730 / 2262.263 |
| TPOT_ms p50 | 124.794 |
| cached/prompt | 7629568 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 1439.081 / 2961.831 |
| TPOT_ms p50 | 249.415 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 458.753 / 2223.859 |
| TPOT_ms p50 | 123.282 |
| cached/prompt | 7626752 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.403 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 835.785 / 3256.357 |
| TPOT_ms p50 | 149.120 |
| cached/prompt | 306944 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 909.586 / 3137.824 |
| TPOT_ms p50 | 191.425 |
| cached/prompt | 0 / 174542 |
