# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_080`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11509.272**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2000 |
| n_ok | 2000 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 313.803 | 718.942 | 3318.422 | 464.047 | 2000 |
| TPOT_ms | 8.642 | 15.220 | 26.898 | 10.371 | 2000 |
| e2e_ms | 2181.863 | 8192.014 | 21753.385 | 3788.235 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.970 / 0.995 |
| cold_miss_rate | 0.185 |
| cached/prompt | 72427008 / 77425770 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.865 / 1.672 |
| req/s | 0.174 |
| output tok/s | 56.953 |

## OpenHands

| metric | value |
|---|---|
| n | 1600 |
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.981 / 0.995 |
| TTFT_ms p50/p90 | 334.001 / 712.258 |
| TPOT_ms p50 | 8.335 |
| cached/prompt | 72368128 / 77123736 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 49 |
| token_weighted_hit | 0.155 |
| per_req_hit p50/p90 | 0.156 / 0.522 |
| TTFT_ms p50/p90 | 1915.781 / 3610.829 |
| TPOT_ms p50 | 20.591 |
| cached/prompt | 127488 / 821591 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 1551 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 329.357 / 618.078 |
| TPOT_ms p50 | 8.253 |
| cached/prompt | 72240640 / 76302145 |

## Request

| metric | value |
|---|---|
| n | 400 |
| token_weighted_hit | 0.195 |
| per_req_hit p50/p90 | 0.000 / 0.328 |
| TTFT_ms p50/p90 | 167.091 / 780.820 |
| TPOT_ms p50 | 11.404 |
| cached/prompt | 58880 / 302034 |

## Request turn0

| metric | value |
|---|---|
| n | 189 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 169.908 / 1707.273 |
| TPOT_ms p50 | 15.800 |
| cached/prompt | 0 / 59101 |
