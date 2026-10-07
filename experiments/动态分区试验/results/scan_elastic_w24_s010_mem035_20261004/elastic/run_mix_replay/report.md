# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **104.598**
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
| TTFT_ms | 7357.642 | 19915.285 | 26173.108 | 9535.246 | 256 |
| TPOT_ms | 267.630 | 606.001 | 617.939 | 291.896 | 256 |
| e2e_ms | 12799.671 | 29610.717 | 31491.869 | 14205.583 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.557 |
| per_req_hit p50/p90 | 0.000 / 0.602 |
| cold_miss_rate | 0.867 |
| cached/prompt | 520704 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 397.423 / 482.788 |
| req/s | 2.447 |
| output tok/s | 39.160 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.651 |
| per_req_hit p50/p90 | 0.792 / 0.985 |
| TTFT_ms p50/p90 | 1009.116 / 7663.943 |
| TPOT_ms p50 | 130.529 |
| cached/prompt | 512256 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 19236.508 / 21458.878 |
| TPOT_ms p50 | 1043.509 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.673 |
| per_req_hit p50/p90 | 0.870 / 0.986 |
| TTFT_ms p50/p90 | 733.078 / 7041.969 |
| TPOT_ms p50 | 126.659 |
| cached/prompt | 509440 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.058 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 7588.871 / 19918.261 |
| TPOT_ms p50 | 274.898 |
| cached/prompt | 8448 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13135.552 / 25174.863 |
| TPOT_ms p50 | 397.172 |
| cached/prompt | 0 / 30741 |
