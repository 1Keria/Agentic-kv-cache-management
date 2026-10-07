# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.325**
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
| TTFT_ms | 3340.607 | 3990.663 | 4504.040 | 2840.140 | 256 |
| TPOT_ms | 231.278 | 312.914 | 423.551 | 210.122 | 256 |
| e2e_ms | 6017.159 | 8370.282 | 9134.092 | 6202.090 | 256 |

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
| s_time_drift_ms p50/p90 (session start) | 958.468 / 1043.897 |
| req/s | 3.399 |
| output tok/s | 54.378 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2306.981 / 3796.598 |
| TPOT_ms p50 | 126.888 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 3829.586 / 4189.891 |
| TPOT_ms p50 | 320.846 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2268.737 / 3447.404 |
| TPOT_ms p50 | 121.751 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3347.070 / 3990.675 |
| TPOT_ms p50 | 255.194 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3756.470 / 3995.797 |
| TPOT_ms p50 | 288.047 |
| cached/prompt | 0 / 30741 |
