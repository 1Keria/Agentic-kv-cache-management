# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **100.687**
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
| TTFT_ms | 8418.511 | 20426.403 | 20640.786 | 10417.499 | 256 |
| TPOT_ms | 129.589 | 377.760 | 698.682 | 205.743 | 256 |
| e2e_ms | 13925.710 | 22419.960 | 22444.784 | 13709.393 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.602 |
| per_req_hit p50/p90 | 0.000 / 0.831 |
| cold_miss_rate | 0.859 |
| cached/prompt | 562176 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 400.893 / 485.087 |
| req/s | 2.542 |
| output tok/s | 40.680 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.700 |
| per_req_hit p50/p90 | 0.858 / 0.986 |
| TTFT_ms p50/p90 | 3003.820 / 7713.165 |
| TPOT_ms p50 | 129.601 |
| cached/prompt | 551168 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 6670.112 / 17434.551 |
| TPOT_ms p50 | 577.222 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.724 |
| per_req_hit p50/p90 | 0.872 / 0.986 |
| TTFT_ms p50/p90 | 2269.251 / 7607.000 |
| TPOT_ms p50 | 129.125 |
| cached/prompt | 548352 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.075 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9444.329 / 20513.495 |
| TPOT_ms p50 | 129.136 |
| cached/prompt | 11008 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 18181.233 / 20637.738 |
| TPOT_ms p50 | 122.846 |
| cached/prompt | 0 / 30741 |
