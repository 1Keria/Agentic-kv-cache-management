# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **132.236**
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
| TTFT_ms | 12249.635 | 38210.432 | 42966.615 | 16185.956 | 256 |
| TPOT_ms | 148.496 | 765.730 | 774.381 | 277.080 | 256 |
| e2e_ms | 15694.807 | 43841.565 | 44823.631 | 20619.229 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.387 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.922 |
| cached/prompt | 361472 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 417.417 / 501.848 |
| req/s | 1.936 |
| output tok/s | 30.975 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.459 |
| per_req_hit p50/p90 | 0.000 / 0.977 |
| TTFT_ms p50/p90 | 4178.782 / 11477.727 |
| TPOT_ms p50 | 123.580 |
| cached/prompt | 361472 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 39902.062 / 40905.916 |
| TPOT_ms p50 | 283.975 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.474 |
| per_req_hit p50/p90 | 0.000 / 0.977 |
| TTFT_ms p50/p90 | 4119.380 / 8747.159 |
| TPOT_ms p50 | 122.280 |
| cached/prompt | 358656 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12258.657 / 39898.349 |
| TPOT_ms p50 | 177.741 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 27819.946 / 42854.501 |
| TPOT_ms p50 | 303.643 |
| cached/prompt | 0 / 30741 |
