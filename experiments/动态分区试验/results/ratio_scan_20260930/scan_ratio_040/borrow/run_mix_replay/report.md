# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.077**
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
| TTFT_ms | 3390.838 | 6807.255 | 7307.347 | 3668.420 | 256 |
| TPOT_ms | 133.409 | 321.259 | 471.879 | 194.760 | 256 |
| e2e_ms | 6020.603 | 10569.410 | 10586.484 | 6784.587 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.806 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.641 |
| cached/prompt | 752640 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 2181.138 / 2266.217 |
| req/s | 3.552 |
| output tok/s | 56.828 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2168.677 / 4938.470 |
| TPOT_ms p50 | 126.848 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 7209.475 / 7474.914 |
| TPOT_ms p50 | 329.598 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2162.716 / 4705.638 |
| TPOT_ms p50 | 126.025 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 5253.299 / 7161.107 |
| TPOT_ms p50 | 141.829 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5827.670 / 7215.011 |
| TPOT_ms p50 | 296.529 |
| cached/prompt | 0 / 30741 |
