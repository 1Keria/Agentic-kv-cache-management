# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **361.728**
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
| TTFT_ms | 1693.810 | 5135.562 | 12818.487 | 2283.500 | 1261 |
| TPOT_ms | 219.266 | 595.435 | 831.912 | 281.730 | 1261 |
| e2e_ms | 5285.887 | 14829.669 | 20895.212 | 6791.172 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.814 |
| per_req_hit p50/p90 | 0.000 / 0.949 |
| cold_miss_rate | 0.772 |
| cached/prompt | 7262208 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.664 / 35.243 |
| req/s | 3.486 |
| output tok/s | 55.777 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.876 |
| per_req_hit p50/p90 | 0.965 / 0.991 |
| TTFT_ms p50/p90 | 466.834 / 2652.367 |
| TPOT_ms p50 | 136.361 |
| cached/prompt | 7146496 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 977.282 / 3495.387 |
| TPOT_ms p50 | 297.459 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.884 |
| per_req_hit p50/p90 | 0.966 / 0.991 |
| TTFT_ms p50/p90 | 464.909 / 2463.497 |
| TPOT_ms p50 | 136.060 |
| cached/prompt | 7138048 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.152 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1959.254 / 5152.248 |
| TPOT_ms p50 | 233.685 |
| cached/prompt | 115712 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2017.574 / 7130.170 |
| TPOT_ms p50 | 284.028 |
| cached/prompt | 0 / 174542 |
