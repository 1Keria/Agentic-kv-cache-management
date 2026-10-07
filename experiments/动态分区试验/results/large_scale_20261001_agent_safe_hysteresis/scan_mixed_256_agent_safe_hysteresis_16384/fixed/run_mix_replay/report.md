# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.729**
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
| TTFT_ms | 2828.699 | 8297.293 | 8552.606 | 3228.875 | 256 |
| TPOT_ms | 240.976 | 290.606 | 368.720 | 205.159 | 256 |
| e2e_ms | 6489.260 | 13084.097 | 13971.112 | 6511.421 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.763 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.684 |
| cached/prompt | 712960 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1585.809 / 1669.221 |
| req/s | 3.520 |
| output tok/s | 56.318 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.841 |
| per_req_hit p50/p90 | 0.925 / 0.987 |
| TTFT_ms p50/p90 | 1616.756 / 3468.387 |
| TPOT_ms p50 | 135.499 |
| cached/prompt | 662016 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8424.520 / 9636.763 |
| TPOT_ms p50 | 293.972 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.867 |
| per_req_hit p50/p90 | 0.937 / 0.987 |
| TTFT_ms p50/p90 | 1120.174 / 2905.085 |
| TPOT_ms p50 | 131.314 |
| cached/prompt | 656384 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.347 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 2954.003 / 8384.092 |
| TPOT_ms p50 | 251.482 |
| cached/prompt | 50944 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3390.601 / 8538.162 |
| TPOT_ms p50 | 266.385 |
| cached/prompt | 0 / 30741 |
