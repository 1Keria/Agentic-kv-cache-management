# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **567.52**
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
| TTFT_ms | 10781.565 | 16715.746 | 19347.120 | 10589.340 | 1261 |
| TPOT_ms | 148.199 | 350.782 | 923.537 | 204.423 | 1261 |
| e2e_ms | 13737.200 | 20682.207 | 23780.828 | 13860.109 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.448 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.924 |
| cached/prompt | 3994112 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.972 / 1.841 |
| req/s | 2.222 |
| output tok/s | 35.551 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.490 |
| per_req_hit p50/p90 | 0.000 / 0.987 |
| TTFT_ms p50/p90 | 6063.650 / 10163.856 |
| TPOT_ms p50 | 146.883 |
| cached/prompt | 3994112 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| TTFT_ms p50/p90 | 8520.585 / 9519.345 |
| TPOT_ms p50 | 146.883 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.494 |
| per_req_hit p50/p90 | 0.000 / 0.987 |
| TTFT_ms p50/p90 | 5746.600 / 10450.395 |
| TPOT_ms p50 | 145.738 |
| cached/prompt | 3985664 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11560.555 / 17185.417 |
| TPOT_ms p50 | 149.145 |
| cached/prompt | 0 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13414.146 / 17872.009 |
| TPOT_ms p50 | 165.504 |
| cached/prompt | 0 / 174542 |
