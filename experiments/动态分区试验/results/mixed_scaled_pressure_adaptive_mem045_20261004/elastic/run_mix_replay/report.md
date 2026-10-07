# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **181.364**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 633 |
| n_ok | 165 |
| n_err | 468 |
| error_breakdown | `{"RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)": 1, "APIConnectionError: Connection error.": 467}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 4438.866 | 4897.736 | 5036.799 | 3628.648 | 165 |
| TPOT_ms | 154.967 | 283.822 | 286.650 | 176.125 | 165 |
| e2e_ms | 6475.217 | 7540.211 | 9116.102 | 6446.649 | 165 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.558 |
| per_req_hit p50/p90 | 0.000 / 0.603 |
| cold_miss_rate | 0.788 |
| cached/prompt | 102144 / 182973 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.628 / 1.696 |
| req/s | 0.910 |
| output tok/s | 14.556 |

## OpenHands

| metric | value |
|---|---|
| n | 10 |
| token_weighted_hit | 0.791 |
| per_req_hit p50/p90 | 0.904 / 0.976 |
| TTFT_ms p50/p90 | 2875.940 / 4823.072 |
| TPOT_ms p50 | 252.989 |
| cached/prompt | 77312 / 97712 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 2 |
| token_weighted_hit | 0.160 |
| per_req_hit p50/p90 | 0.264 / 0.474 |
| TTFT_ms p50/p90 | 3223.124 / 3437.211 |
| TPOT_ms p50 | 286.209 |
| cached/prompt | 2816 / 17640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 8 |
| token_weighted_hit | 0.930 |
| per_req_hit p50/p90 | 0.922 / 0.978 |
| TTFT_ms p50/p90 | 2790.857 / 4848.750 |
| TPOT_ms p50 | 197.560 |
| cached/prompt | 74496 / 80072 |

## Request

| metric | value |
|---|---|
| n | 155 |
| token_weighted_hit | 0.291 |
| per_req_hit p50/p90 | 0.000 / 0.381 |
| TTFT_ms p50/p90 | 4455.054 / 4897.736 |
| TPOT_ms p50 | 154.949 |
| cached/prompt | 24832 / 85261 |

## Request turn0

| metric | value |
|---|---|
| n | 92 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 4717.480 / 4928.951 |
| TPOT_ms p50 | 136.424 |
| cached/prompt | 0 / 24620 |
