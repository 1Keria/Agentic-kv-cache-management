# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.405**
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
| TTFT_ms | 2902.897 | 10225.724 | 10447.758 | 4378.308 | 256 |
| TPOT_ms | 236.699 | 401.868 | 414.654 | 241.885 | 256 |
| e2e_ms | 5131.393 | 15064.179 | 16720.804 | 8248.466 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.798 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.656 |
| cached/prompt | 745472 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 528.942 / 612.475 |
| req/s | 3.536 |
| output tok/s | 56.571 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 602.437 / 3955.583 |
| TPOT_ms p50 | 122.388 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 10262.956 / 12937.117 |
| TPOT_ms p50 | 419.662 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 574.283 / 2926.681 |
| TPOT_ms p50 | 121.243 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.370 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 5601.762 / 10226.788 |
| TPOT_ms p50 | 251.972 |
| cached/prompt | 54272 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6122.640 / 10437.407 |
| TPOT_ms p50 | 390.530 |
| cached/prompt | 0 / 30741 |
