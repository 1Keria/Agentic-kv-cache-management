# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.11**
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
| TTFT_ms | 3323.292 | 9538.787 | 10462.554 | 4540.847 | 256 |
| TPOT_ms | 245.182 | 287.740 | 397.435 | 215.392 | 256 |
| e2e_ms | 7164.318 | 12982.735 | 14851.897 | 7987.116 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.787 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.656 |
| cached/prompt | 735232 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 402.525 / 486.989 |
| req/s | 3.550 |
| output tok/s | 56.802 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.858 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2123.544 / 2922.447 |
| TPOT_ms p50 | 127.578 |
| cached/prompt | 675584 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10366.396 / 10992.246 |
| TPOT_ms p50 | 297.055 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.892 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2071.340 / 2353.253 |
| TPOT_ms p50 | 125.997 |
| cached/prompt | 675584 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.406 |
| per_req_hit p50/p90 | 0.000 / 0.642 |
| TTFT_ms p50/p90 | 5899.025 / 10319.798 |
| TPOT_ms p50 | 250.801 |
| cached/prompt | 59648 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6554.263 / 10366.972 |
| TPOT_ms p50 | 274.635 |
| cached/prompt | 0 / 30741 |
