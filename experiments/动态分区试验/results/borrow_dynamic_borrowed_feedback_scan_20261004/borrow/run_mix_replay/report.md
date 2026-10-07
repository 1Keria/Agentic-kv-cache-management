# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **82.621**
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
| TTFT_ms | 3301.305 | 14066.665 | 14433.092 | 4485.902 | 256 |
| TPOT_ms | 533.607 | 849.714 | 881.188 | 488.923 | 256 |
| e2e_ms | 11833.731 | 27530.791 | 28163.769 | 12308.675 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.785 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.668 |
| cached/prompt | 733184 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 996.916 / 1082.264 |
| req/s | 3.099 |
| output tok/s | 49.576 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.933 / 0.986 |
| TTFT_ms p50/p90 | 798.235 / 3094.338 |
| TPOT_ms p50 | 130.796 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 4266.755 / 12120.033 |
| TPOT_ms p50 | 881.770 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 640.394 / 2757.331 |
| TPOT_ms p50 | 130.268 |
| cached/prompt | 673280 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.389 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3471.786 / 14287.211 |
| TPOT_ms p50 | 634.909 |
| cached/prompt | 57088 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3793.006 / 14297.690 |
| TPOT_ms p50 | 774.124 |
| cached/prompt | 0 / 30741 |
