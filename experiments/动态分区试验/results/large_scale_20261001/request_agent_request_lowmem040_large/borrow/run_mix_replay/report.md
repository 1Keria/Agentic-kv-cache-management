# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **382.492**
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
| TTFT_ms | 2284.531 | 6751.965 | 10203.682 | 2987.416 | 1261 |
| TPOT_ms | 232.290 | 701.783 | 857.741 | 352.716 | 1261 |
| e2e_ms | 9202.096 | 15283.980 | 20200.574 | 8630.864 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.848 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.747 |
| cached/prompt | 7559936 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.098 / 1.952 |
| req/s | 3.297 |
| output tok/s | 52.749 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.970 / 0.990 |
| TTFT_ms p50/p90 | 466.867 / 702.279 |
| TPOT_ms p50 | 125.930 |
| cached/prompt | 7385088 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 647.087 / 1573.031 |
| TPOT_ms p50 | 135.641 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.913 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 464.456 / 697.295 |
| TPOT_ms p50 | 125.910 |
| cached/prompt | 7368192 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.230 |
| per_req_hit p50/p90 | 0.000 / 0.355 |
| TTFT_ms p50/p90 | 3328.244 / 6862.772 |
| TPOT_ms p50 | 311.718 |
| cached/prompt | 174848 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 4488.884 / 7015.810 |
| TPOT_ms p50 | 551.409 |
| cached/prompt | 0 / 174542 |
