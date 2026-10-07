# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.695**
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
| TTFT_ms | 2809.061 | 10488.877 | 11014.658 | 3714.269 | 256 |
| TPOT_ms | 142.749 | 479.204 | 498.049 | 252.870 | 256 |
| e2e_ms | 6123.916 | 15100.251 | 16514.674 | 7760.184 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.802 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.652 |
| cached/prompt | 749312 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 401.060 / 485.226 |
| req/s | 3.338 |
| output tok/s | 53.407 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2189.055 / 3020.089 |
| TPOT_ms p50 | 126.717 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 10501.424 / 11719.030 |
| TPOT_ms p50 | 419.379 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2182.341 / 2844.955 |
| TPOT_ms p50 | 126.382 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.396 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3041.304 / 10493.692 |
| TPOT_ms p50 | 159.163 |
| cached/prompt | 58112 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3386.926 / 10619.857 |
| TPOT_ms p50 | 458.542 |
| cached/prompt | 0 / 30741 |
