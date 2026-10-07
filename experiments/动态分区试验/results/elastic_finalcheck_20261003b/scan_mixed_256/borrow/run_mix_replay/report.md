# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **80.002**
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
| TTFT_ms | 3269.147 | 11784.534 | 12218.437 | 4258.439 | 256 |
| TPOT_ms | 466.679 | 852.820 | 901.794 | 434.591 | 256 |
| e2e_ms | 12212.801 | 25592.544 | 26439.882 | 11211.891 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.785 |
| per_req_hit p50/p90 | 0.000 / 0.891 |
| cold_miss_rate | 0.664 |
| cached/prompt | 732928 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1602.495 / 1687.302 |
| req/s | 3.200 |
| output tok/s | 51.199 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.928 / 0.986 |
| TTFT_ms p50/p90 | 576.108 / 3850.981 |
| TPOT_ms p50 | 122.641 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 4833.185 / 10577.654 |
| TPOT_ms p50 | 901.781 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.945 / 0.986 |
| TTFT_ms p50/p90 | 540.874 / 3346.314 |
| TPOT_ms p50 | 119.120 |
| cached/prompt | 669952 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.410 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3440.954 / 12006.162 |
| TPOT_ms p50 | 573.374 |
| cached/prompt | 60160 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3765.630 / 12210.224 |
| TPOT_ms p50 | 609.223 |
| cached/prompt | 0 / 30741 |
