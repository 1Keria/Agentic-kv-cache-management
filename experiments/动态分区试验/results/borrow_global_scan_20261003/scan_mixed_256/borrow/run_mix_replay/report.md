# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **70.678**
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
| TTFT_ms | 3245.786 | 8494.046 | 8987.165 | 3339.713 | 256 |
| TPOT_ms | 261.805 | 469.223 | 550.853 | 285.771 | 256 |
| e2e_ms | 9404.782 | 10785.888 | 10906.126 | 7912.049 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.801 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.660 |
| cached/prompt | 747776 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 508.531 / 593.132 |
| req/s | 3.622 |
| output tok/s | 57.953 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 701.572 / 3496.806 |
| TPOT_ms p50 | 130.128 |
| cached/prompt | 685568 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6119.696 / 8051.225 |
| TPOT_ms p50 | 294.129 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 515.579 / 3000.760 |
| TPOT_ms p50 | 129.398 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.424 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3268.918 / 8529.804 |
| TPOT_ms p50 | 309.004 |
| cached/prompt | 62208 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3675.332 / 8681.574 |
| TPOT_ms p50 | 443.447 |
| cached/prompt | 0 / 30741 |
