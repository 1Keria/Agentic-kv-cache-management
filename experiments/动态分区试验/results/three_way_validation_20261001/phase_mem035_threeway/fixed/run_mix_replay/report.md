# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **638.261**
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
| TTFT_ms | 10222.128 | 19113.124 | 22583.306 | 10681.550 | 1261 |
| TPOT_ms | 143.089 | 388.841 | 628.620 | 201.046 | 1261 |
| e2e_ms | 13072.410 | 22305.182 | 25784.085 | 13898.292 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.260 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.968 |
| cached/prompt | 2319104 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.956 / 1.907 |
| req/s | 1.976 |
| output tok/s | 31.611 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.284 |
| per_req_hit p50/p90 | 0.000 / 0.974 |
| TTFT_ms p50/p90 | 7158.255 / 10418.620 |
| TPOT_ms p50 | 162.976 |
| cached/prompt | 2319104 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 7394.249 / 8218.149 |
| TPOT_ms p50 | 176.750 |
| cached/prompt | 0 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.287 |
| per_req_hit p50/p90 | 0.000 / 0.975 |
| TTFT_ms p50/p90 | 7119.864 / 10448.913 |
| TPOT_ms p50 | 161.541 |
| cached/prompt | 2319104 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10653.648 / 19355.352 |
| TPOT_ms p50 | 140.959 |
| cached/prompt | 0 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11882.556 / 20529.369 |
| TPOT_ms p50 | 157.767 |
| cached/prompt | 0 / 174542 |
