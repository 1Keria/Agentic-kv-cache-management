# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30100`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.649**
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
| TTFT_ms | 3291.557 | 7934.959 | 11028.154 | 3555.909 | 256 |
| TPOT_ms | 416.001 | 891.087 | 1000.307 | 422.936 | 256 |
| e2e_ms | 10119.895 | 21451.617 | 23716.431 | 10322.882 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.781 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.668 |
| cached/prompt | 729600 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 373.934 / 459.273 |
| req/s | 3.297 |
| output tok/s | 52.750 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.928 / 0.986 |
| TTFT_ms p50/p90 | 506.651 / 3636.706 |
| TPOT_ms p50 | 125.404 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 3641.600 / 6916.186 |
| TPOT_ms p50 | 1001.158 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 451.600 / 3455.176 |
| TPOT_ms p50 | 118.237 |
| cached/prompt | 669952 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.387 |
| per_req_hit p50/p90 | 0.000 / 0.642 |
| TTFT_ms p50/p90 | 3456.781 / 7939.880 |
| TPOT_ms p50 | 419.127 |
| cached/prompt | 56832 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3785.477 / 7942.691 |
| TPOT_ms p50 | 418.645 |
| cached/prompt | 0 / 30741 |
