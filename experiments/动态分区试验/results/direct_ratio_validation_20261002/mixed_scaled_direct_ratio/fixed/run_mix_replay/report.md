# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.944**
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
| TTFT_ms | 710.163 | 3211.709 | 5697.918 | 1335.728 | 1261 |
| TPOT_ms | 149.133 | 318.184 | 474.722 | 195.968 | 1261 |
| e2e_ms | 4208.992 | 7713.914 | 8268.090 | 4471.208 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.890 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.645 |
| cached/prompt | 7938816 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.680 / 589.043 |
| req/s | 3.553 |
| output tok/s | 56.843 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 464.888 / 2304.523 |
| TPOT_ms p50 | 126.524 |
| cached/prompt | 7629568 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 926.881 / 5295.269 |
| TPOT_ms p50 | 320.694 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 460.564 / 2246.573 |
| TPOT_ms p50 | 126.241 |
| cached/prompt | 7615488 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.406 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 792.294 / 3245.118 |
| TPOT_ms p50 | 156.002 |
| cached/prompt | 309248 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1662.453 / 3452.505 |
| TPOT_ms p50 | 274.400 |
| cached/prompt | 0 / 174542 |
