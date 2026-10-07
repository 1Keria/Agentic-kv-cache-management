# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **78.823**
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
| TTFT_ms | 4319.918 | 7942.127 | 10019.392 | 4029.082 | 256 |
| TPOT_ms | 261.930 | 596.494 | 676.473 | 318.164 | 256 |
| e2e_ms | 9252.721 | 17025.717 | 19562.976 | 9119.705 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.795 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.656 |
| cached/prompt | 742656 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 954.812 / 1038.851 |
| req/s | 3.248 |
| output tok/s | 51.964 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2111.860 / 3907.921 |
| TPOT_ms p50 | 127.829 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7793.080 / 10447.925 |
| TPOT_ms p50 | 578.434 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 1362.765 / 3214.352 |
| TPOT_ms p50 | 124.397 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.366 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 4754.084 / 7944.336 |
| TPOT_ms p50 | 280.803 |
| cached/prompt | 53760 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5088.602 / 7951.964 |
| TPOT_ms p50 | 280.943 |
| cached/prompt | 0 / 30741 |
