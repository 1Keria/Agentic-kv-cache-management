# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **385.131**
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
| TTFT_ms | 666.594 | 5655.003 | 9013.014 | 2045.582 | 1261 |
| TPOT_ms | 332.114 | 558.848 | 844.659 | 339.316 | 1261 |
| e2e_ms | 7004.508 | 13674.036 | 19107.037 | 7474.644 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.851 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.821 |
| cached/prompt | 7589888 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.939 / 1.933 |
| req/s | 3.274 |
| output tok/s | 52.387 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 442.860 / 659.901 |
| TPOT_ms p50 | 125.548 |
| cached/prompt | 7538688 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 721.722 / 1048.697 |
| TPOT_ms p50 | 117.296 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.932 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 439.755 / 630.172 |
| TPOT_ms p50 | 126.062 |
| cached/prompt | 7521792 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.067 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 850.487 / 5893.909 |
| TPOT_ms p50 | 367.976 |
| cached/prompt | 51200 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 869.216 / 5769.239 |
| TPOT_ms p50 | 471.556 |
| cached/prompt | 0 / 174542 |
