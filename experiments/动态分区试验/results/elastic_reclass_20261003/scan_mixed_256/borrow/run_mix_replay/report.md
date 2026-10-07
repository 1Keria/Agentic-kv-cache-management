# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **79.638**
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
| TTFT_ms | 4331.608 | 11873.550 | 12205.492 | 4250.698 | 256 |
| TPOT_ms | 386.734 | 610.210 | 659.325 | 374.880 | 256 |
| e2e_ms | 12519.740 | 18498.501 | 21345.687 | 10248.776 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.796 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.660 |
| cached/prompt | 743168 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 931.428 / 1016.641 |
| req/s | 3.215 |
| output tok/s | 51.433 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 444.050 / 3711.785 |
| TPOT_ms p50 | 128.200 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 11729.243 / 14385.237 |
| TPOT_ms p50 | 618.320 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 435.511 / 3598.736 |
| TPOT_ms p50 | 127.732 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.373 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 4643.225 / 11876.101 |
| TPOT_ms p50 | 507.240 |
| cached/prompt | 54784 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5069.997 / 11880.812 |
| TPOT_ms p50 | 528.794 |
| cached/prompt | 0 / 30741 |
