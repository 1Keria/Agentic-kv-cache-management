# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **123.837**
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
| TTFT_ms | 13049.964 | 22184.349 | 25509.111 | 11719.242 | 256 |
| TPOT_ms | 256.457 | 520.409 | 715.623 | 260.707 | 256 |
| e2e_ms | 16292.326 | 28383.460 | 29895.908 | 15890.556 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.269 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.941 |
| cached/prompt | 251648 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 400.190 / 485.431 |
| req/s | 2.067 |
| output tok/s | 33.076 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.320 |
| per_req_hit p50/p90 | 0.000 / 0.942 |
| TTFT_ms p50/p90 | 4326.094 / 16302.332 |
| TPOT_ms p50 | 129.689 |
| cached/prompt | 251648 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 22452.959 / 22993.863 |
| TPOT_ms p50 | 381.056 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.332 |
| per_req_hit p50/p90 | 0.000 / 0.948 |
| TTFT_ms p50/p90 | 4213.095 / 8038.606 |
| TPOT_ms p50 | 128.797 |
| cached/prompt | 251648 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13784.737 / 23119.294 |
| TPOT_ms p50 | 264.029 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14985.566 / 25486.244 |
| TPOT_ms p50 | 272.950 |
| cached/prompt | 0 / 30741 |
