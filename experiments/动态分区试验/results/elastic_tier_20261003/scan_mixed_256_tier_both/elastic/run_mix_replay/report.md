# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30104`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **83.733**
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
| TTFT_ms | 2963.855 | 8036.565 | 8774.247 | 3317.754 | 256 |
| TPOT_ms | 274.228 | 737.244 | 882.210 | 364.470 | 256 |
| e2e_ms | 7503.044 | 19838.680 | 22369.386 | 9149.282 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.797 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.652 |
| cached/prompt | 744448 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1015.217 / 1099.566 |
| req/s | 3.057 |
| output tok/s | 48.917 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 580.752 / 2803.710 |
| TPOT_ms p50 | 141.356 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 6093.951 / 8746.450 |
| TPOT_ms p50 | 883.250 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 486.726 / 2369.164 |
| TPOT_ms p50 | 141.253 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.378 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 3148.600 / 8037.389 |
| TPOT_ms p50 | 283.226 |
| cached/prompt | 55552 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3354.876 / 8043.079 |
| TPOT_ms p50 | 272.155 |
| cached/prompt | 0 / 30741 |
