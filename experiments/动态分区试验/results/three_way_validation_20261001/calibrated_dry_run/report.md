# Mix workload replay report

- model: `dry-run`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse_calibrated`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **0.036**
- dry_run: True

## Integrity

| metric | value |
|---|---|
| n_issued | 1277 |
| n_ok | 0 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | — | — | — | — | None |
| TPOT_ms | — | — | — | — | None |
| e2e_ms | — | — | — | — | None |

## KV

| metric | value |
|---|---|
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| cold_miss_rate | — |
| cached/prompt | None / None |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | — / — |
| req/s | — |
| output tok/s | — |

## Agent

| metric | value |
|---|---|
| n | 0 |
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| TTFT_ms p50/p90 | — / — |
| TPOT_ms p50 | — |
| cached/prompt | None / None |

## Agent within-session (turn>=1)

| metric | value |
|---|---|
| n | 0 |
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| TTFT_ms p50/p90 | — / — |
| TPOT_ms p50 | — |
| cached/prompt | None / None |

## Request

| metric | value |
|---|---|
| n | 0 |
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| TTFT_ms p50/p90 | — / — |
| TPOT_ms p50 | — |
| cached/prompt | None / None |
