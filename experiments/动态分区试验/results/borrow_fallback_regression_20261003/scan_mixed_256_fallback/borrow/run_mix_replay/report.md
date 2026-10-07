# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **85.484**
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
| TTFT_ms | 3247.633 | 13676.162 | 16236.444 | 4441.451 | 256 |
| TPOT_ms | 455.743 | 730.475 | 756.229 | 427.952 | 256 |
| e2e_ms | 9039.949 | 24553.046 | 27299.141 | 11288.681 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.782 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.660 |
| cached/prompt | 730624 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 7470.934 / 7554.299 |
| req/s | 2.995 |
| output tok/s | 47.915 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.928 / 0.986 |
| TTFT_ms p50/p90 | 635.572 / 3524.745 |
| TPOT_ms p50 | 122.990 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 10813.071 / 14949.061 |
| TPOT_ms p50 | 739.202 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 625.189 / 2851.603 |
| TPOT_ms p50 | 121.753 |
| cached/prompt | 669952 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.394 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 3519.298 / 15982.136 |
| TPOT_ms p50 | 488.852 |
| cached/prompt | 57856 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3879.124 / 16233.340 |
| TPOT_ms p50 | 713.168 |
| cached/prompt | 0 / 30741 |
