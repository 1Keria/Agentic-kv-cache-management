# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.553**
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
| TTFT_ms | 2821.552 | 9591.600 | 10574.021 | 3299.302 | 256 |
| TPOT_ms | 251.858 | 428.106 | 437.563 | 257.485 | 256 |
| e2e_ms | 5673.034 | 14223.119 | 17305.416 | 7419.067 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.794 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.688 |
| cached/prompt | 741632 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 408.601 / 494.191 |
| req/s | 3.301 |
| output tok/s | 52.816 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2267.715 / 3417.128 |
| TPOT_ms p50 | 125.256 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9601.509 / 10819.772 |
| TPOT_ms p50 | 420.639 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2263.649 / 3201.775 |
| TPOT_ms p50 | 122.986 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.343 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 2932.278 / 9595.490 |
| TPOT_ms p50 | 268.837 |
| cached/prompt | 50432 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3342.563 / 9748.318 |
| TPOT_ms p50 | 405.744 |
| cached/prompt | 0 / 30741 |
