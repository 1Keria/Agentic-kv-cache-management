# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.818**
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
| TTFT_ms | 3270.066 | 8654.537 | 10213.434 | 3616.108 | 256 |
| TPOT_ms | 339.798 | 946.321 | 1055.513 | 415.209 | 256 |
| e2e_ms | 10204.406 | 22198.780 | 25328.827 | 10259.451 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.784 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.656 |
| cached/prompt | 731904 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 985.588 / 1071.073 |
| req/s | 3.129 |
| output tok/s | 50.062 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.933 / 0.986 |
| TTFT_ms p50/p90 | 2179.837 / 3524.304 |
| TPOT_ms p50 | 121.148 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 4222.963 / 7600.517 |
| TPOT_ms p50 | 1056.244 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 2151.973 / 3246.556 |
| TPOT_ms p50 | 121.078 |
| cached/prompt | 673280 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.380 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 3406.894 / 8655.581 |
| TPOT_ms p50 | 405.105 |
| cached/prompt | 55808 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3762.894 / 8660.177 |
| TPOT_ms p50 | 425.407 |
| cached/prompt | 0 / 30741 |
