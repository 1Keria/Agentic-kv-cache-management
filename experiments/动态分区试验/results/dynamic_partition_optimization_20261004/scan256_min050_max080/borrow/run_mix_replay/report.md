# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **78.48**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 256 |
| n_ok | 256 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2994.822 | 7346.930 | 10640.249 | 3556.011 | 256 |
| TPOT_ms | 146.075 | 394.901 | 404.227 | 222.854 | 256 |
| e2e_ms | 6680.899 | 13338.095 | 13396.417 | 7121.670 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.783 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.656 |
| cached/prompt | 731136 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 448.186 / 530.861 |
| req/s | 3.262 |
| output tok/s | 52.192 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2208.111 / 4209.771 |
| TPOT_ms p50 | 141.382 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7355.740 / 10023.043 |
| TPOT_ms p50 | 393.039 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2159.437 / 4058.433 |
| TPOT_ms p50 | 139.433 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.375 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 3010.666 / 7352.381 |
| TPOT_ms p50 | 165.255 |
| cached/prompt | 55040 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3407.213 / 10618.769 |
| TPOT_ms p50 | 372.347 |
| cached/prompt | 0 / 30741 |
