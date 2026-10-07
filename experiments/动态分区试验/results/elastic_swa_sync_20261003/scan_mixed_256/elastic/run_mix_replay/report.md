# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.02**
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
| TTFT_ms | 4569.586 | 8037.203 | 10322.824 | 4269.878 | 256 |
| TPOT_ms | 283.298 | 634.805 | 668.958 | 319.783 | 256 |
| e2e_ms | 8929.695 | 17925.238 | 21025.569 | 9386.413 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.791 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.668 |
| cached/prompt | 739072 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 406.903 / 488.774 |
| req/s | 3.160 |
| output tok/s | 50.555 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.872 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 682.191 / 4760.997 |
| TPOT_ms p50 | 135.097 |
| cached/prompt | 686080 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 5797.097 / 7399.236 |
| TPOT_ms p50 | 384.813 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 650.727 / 3042.224 |
| TPOT_ms p50 | 133.058 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.361 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 5578.182 / 8042.284 |
| TPOT_ms p50 | 283.602 |
| cached/prompt | 52992 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5931.190 / 10316.913 |
| TPOT_ms p50 | 271.742 |
| cached/prompt | 0 / 30741 |
