# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.995**
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
| TTFT_ms | 3355.171 | 10779.132 | 11047.889 | 4247.795 | 256 |
| TPOT_ms | 158.284 | 503.189 | 512.738 | 275.611 | 256 |
| e2e_ms | 7416.712 | 13165.342 | 13183.846 | 8657.579 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.792 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.672 |
| cached/prompt | 740096 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 417.766 / 501.249 |
| req/s | 3.369 |
| output tok/s | 53.898 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2243.444 / 3462.117 |
| TPOT_ms p50 | 130.806 |
| cached/prompt | 685568 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10797.521 / 10964.887 |
| TPOT_ms p50 | 138.138 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2217.279 / 3280.031 |
| TPOT_ms p50 | 130.324 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.371 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 5074.452 / 10795.903 |
| TPOT_ms p50 | 345.193 |
| cached/prompt | 54528 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5591.793 / 10941.154 |
| TPOT_ms p50 | 472.349 |
| cached/prompt | 0 / 30741 |
