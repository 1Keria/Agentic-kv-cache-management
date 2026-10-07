# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.626**
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
| TTFT_ms | 2827.065 | 7297.550 | 10508.639 | 3382.463 | 256 |
| TPOT_ms | 167.628 | 393.281 | 402.351 | 229.837 | 256 |
| e2e_ms | 6294.632 | 13178.535 | 13237.368 | 7059.853 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.785 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.652 |
| cached/prompt | 733184 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 392.970 / 477.951 |
| req/s | 3.341 |
| output tok/s | 53.455 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2263.084 / 4720.841 |
| TPOT_ms p50 | 128.291 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7220.335 / 9893.165 |
| TPOT_ms p50 | 390.717 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2233.895 / 3495.073 |
| TPOT_ms p50 | 124.380 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.389 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 2961.668 / 7299.758 |
| TPOT_ms p50 | 168.805 |
| cached/prompt | 57088 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3359.606 / 10488.649 |
| TPOT_ms p50 | 370.797 |
| cached/prompt | 0 / 30741 |
