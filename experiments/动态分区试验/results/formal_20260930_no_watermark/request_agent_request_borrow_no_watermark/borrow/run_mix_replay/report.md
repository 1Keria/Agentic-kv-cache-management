# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **379.428**
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
| TTFT_ms | 493.947 | 3604.822 | 6440.143 | 1290.274 | 1261 |
| TPOT_ms | 321.696 | 913.682 | 1491.428 | 458.741 | 1261 |
| e2e_ms | 6653.000 | 16684.780 | 29181.024 | 8630.126 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.892 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.659 |
| cached/prompt | 7952640 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.021 / 1.938 |
| req/s | 3.323 |
| output tok/s | 53.175 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 459.726 / 749.080 |
| TPOT_ms p50 | 125.501 |
| cached/prompt | 7650048 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 716.605 / 1367.746 |
| TPOT_ms p50 | 127.759 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.991 |
| TTFT_ms p50/p90 | 457.564 / 711.781 |
| TPOT_ms p50 | 125.380 |
| cached/prompt | 7633152 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.628 |
| TTFT_ms p50/p90 | 542.453 / 4039.067 |
| TPOT_ms p50 | 497.024 |
| cached/prompt | 302592 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 746.798 / 4821.803 |
| TPOT_ms p50 | 731.266 |
| cached/prompt | 0 / 174542 |
