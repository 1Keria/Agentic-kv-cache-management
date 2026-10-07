# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.086**
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
| TTFT_ms | 3319.667 | 13309.487 | 13460.037 | 4674.634 | 256 |
| TPOT_ms | 402.688 | 614.391 | 745.682 | 380.395 | 256 |
| e2e_ms | 9041.551 | 21036.095 | 21775.145 | 10760.951 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.794 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.660 |
| cached/prompt | 741632 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1018.154 / 1103.398 |
| req/s | 3.157 |
| output tok/s | 50.514 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.866 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2112.805 / 4146.863 |
| TPOT_ms p50 | 130.650 |
| cached/prompt | 681984 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 4177.080 / 11401.182 |
| TPOT_ms p50 | 747.789 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.897 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2085.564 / 3396.491 |
| TPOT_ms p50 | 129.173 |
| cached/prompt | 679168 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.406 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 4988.721 / 13415.325 |
| TPOT_ms p50 | 469.885 |
| cached/prompt | 59648 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5496.724 / 13423.497 |
| TPOT_ms p50 | 590.997 |
| cached/prompt | 0 / 30741 |
