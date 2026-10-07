# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **101.565**
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
| TTFT_ms | 7008.098 | 20075.918 | 21610.060 | 9733.002 | 256 |
| TPOT_ms | 126.834 | 427.558 | 558.908 | 191.992 | 256 |
| e2e_ms | 9716.843 | 21906.480 | 23442.649 | 12804.868 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.559 |
| per_req_hit p50/p90 | 0.000 / 0.791 |
| cold_miss_rate | 0.863 |
| cached/prompt | 522496 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 397.773 / 483.312 |
| req/s | 2.521 |
| output tok/s | 40.329 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.647 |
| per_req_hit p50/p90 | 0.792 / 0.985 |
| TTFT_ms p50/p90 | 2282.478 / 8001.598 |
| TPOT_ms p50 | 127.859 |
| cached/prompt | 509696 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 3561.004 / 16373.461 |
| TPOT_ms p50 | 356.545 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.670 |
| per_req_hit p50/p90 | 0.870 / 0.986 |
| TTFT_ms p50/p90 | 2231.671 / 7873.216 |
| TPOT_ms p50 | 126.085 |
| cached/prompt | 506880 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.087 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9444.884 / 20078.977 |
| TPOT_ms p50 | 126.796 |
| cached/prompt | 12800 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12875.645 / 21484.980 |
| TPOT_ms p50 | 141.351 |
| cached/prompt | 0 / 30741 |
