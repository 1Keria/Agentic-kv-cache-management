# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.438**
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
| TTFT_ms | 2821.988 | 13958.290 | 14592.154 | 4470.003 | 256 |
| TPOT_ms | 292.608 | 688.423 | 841.731 | 361.061 | 256 |
| e2e_ms | 9669.587 | 16388.005 | 17664.376 | 10246.978 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.796 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.664 |
| cached/prompt | 743680 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 424.995 / 509.602 |
| req/s | 3.306 |
| output tok/s | 52.894 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2181.414 / 3876.540 |
| TPOT_ms p50 | 127.010 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 5742.762 / 12347.831 |
| TPOT_ms p50 | 842.801 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2124.267 / 2818.584 |
| TPOT_ms p50 | 125.650 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.377 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 5208.382 / 13960.720 |
| TPOT_ms p50 | 313.483 |
| cached/prompt | 55296 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5777.240 / 14198.604 |
| TPOT_ms p50 | 662.994 |
| cached/prompt | 0 / 30741 |
