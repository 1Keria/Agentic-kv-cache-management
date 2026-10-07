# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.262**
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
| TTFT_ms | 2923.664 | 7454.468 | 10757.042 | 3441.639 | 256 |
| TPOT_ms | 254.507 | 409.986 | 504.083 | 251.544 | 256 |
| e2e_ms | 6521.640 | 15463.343 | 15524.070 | 7466.346 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.788 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.652 |
| cached/prompt | 736256 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 408.137 / 493.292 |
| req/s | 3.357 |
| output tok/s | 53.710 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2255.163 / 4059.643 |
| TPOT_ms p50 | 133.855 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7458.954 / 10126.391 |
| TPOT_ms p50 | 505.921 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2153.009 / 3977.712 |
| TPOT_ms p50 | 125.645 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.410 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 2958.824 / 7458.776 |
| TPOT_ms p50 | 266.359 |
| cached/prompt | 60160 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3324.459 / 10733.221 |
| TPOT_ms p50 | 386.631 |
| cached/prompt | 0 / 30741 |
