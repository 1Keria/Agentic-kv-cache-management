# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.853**
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
| TTFT_ms | 2828.338 | 7676.194 | 8097.703 | 3116.616 | 256 |
| TPOT_ms | 141.927 | 396.326 | 405.836 | 222.955 | 256 |
| e2e_ms | 6074.555 | 11593.727 | 12648.958 | 6683.902 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.796 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.664 |
| cached/prompt | 743424 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1045.315 / 1129.838 |
| req/s | 3.375 |
| output tok/s | 53.999 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2247.527 / 3917.343 |
| TPOT_ms p50 | 121.139 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7930.089 / 10607.752 |
| TPOT_ms p50 | 310.843 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2221.918 / 3720.865 |
| TPOT_ms p50 | 118.790 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.356 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 2900.561 / 7881.195 |
| TPOT_ms p50 | 246.863 |
| cached/prompt | 52224 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3367.836 / 8091.936 |
| TPOT_ms p50 | 372.942 |
| cached/prompt | 0 / 30741 |
