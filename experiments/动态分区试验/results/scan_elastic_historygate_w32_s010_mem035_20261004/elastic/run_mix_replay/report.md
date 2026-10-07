# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30138`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **100.633**
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
| TTFT_ms | 8441.166 | 18849.056 | 21088.655 | 9492.455 | 256 |
| TPOT_ms | 127.832 | 310.619 | 587.145 | 185.354 | 256 |
| e2e_ms | 12316.374 | 20750.631 | 22956.186 | 12458.117 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.589 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| cold_miss_rate | 0.879 |
| cached/prompt | 550144 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1072.368 / 1157.169 |
| req/s | 2.544 |
| output tok/s | 40.703 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.695 |
| per_req_hit p50/p90 | 0.873 / 0.986 |
| TTFT_ms p50/p90 | 1783.460 / 7698.092 |
| TPOT_ms p50 | 132.812 |
| cached/prompt | 547328 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6224.570 / 17945.692 |
| TPOT_ms p50 | 454.625 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.723 |
| per_req_hit p50/p90 | 0.911 / 0.986 |
| TTFT_ms p50/p90 | 1058.026 / 7524.907 |
| TPOT_ms p50 | 131.356 |
| cached/prompt | 547328 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.019 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10432.960 / 20866.410 |
| TPOT_ms p50 | 126.513 |
| cached/prompt | 2816 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14557.820 / 20996.368 |
| TPOT_ms p50 | 124.500 |
| cached/prompt | 0 / 30741 |
