# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.168**
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
| TTFT_ms | 648.028 | 4182.469 | 9491.906 | 1752.741 | 1261 |
| TPOT_ms | 204.714 | 982.122 | 1717.253 | 428.534 | 1261 |
| e2e_ms | 6029.349 | 17531.183 | 33275.805 | 8609.288 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.880 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.672 |
| cached/prompt | 7847936 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.055 / 1.993 |
| req/s | 3.317 |
| output tok/s | 53.071 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 468.993 / 824.457 |
| TPOT_ms p50 | 126.161 |
| cached/prompt | 7559424 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 778.348 / 2287.888 |
| TPOT_ms p50 | 146.499 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 468.007 / 783.986 |
| TPOT_ms p50 | 126.147 |
| cached/prompt | 7542528 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.379 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 960.669 / 4431.576 |
| TPOT_ms p50 | 349.692 |
| cached/prompt | 288512 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1768.537 / 5233.852 |
| TPOT_ms p50 | 626.387 |
| cached/prompt | 0 / 174542 |
