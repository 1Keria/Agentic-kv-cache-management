# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **362.534**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1261 |
| n_ok | 1261 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 880.602 | 3697.442 | 8013.415 | 1698.046 | 1261 |
| TPOT_ms | 189.355 | 482.229 | 676.046 | 241.083 | 1261 |
| e2e_ms | 4193.314 | 12435.864 | 13691.674 | 5555.367 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.815 |
| per_req_hit p50/p90 | 0.000 / 0.955 |
| cold_miss_rate | 0.762 |
| cached/prompt | 7264768 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.592 / 1.296 |
| req/s | 3.478 |
| output tok/s | 55.653 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.968 / 0.991 |
| TTFT_ms p50/p90 | 470.812 / 2875.952 |
| TPOT_ms p50 | 128.185 |
| cached/prompt | 7134464 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 909.427 / 3440.579 |
| TPOT_ms p50 | 225.537 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.883 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 469.205 / 2834.446 |
| TPOT_ms p50 | 127.161 |
| cached/prompt | 7131648 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.000 / 0.296 |
| TTFT_ms p50/p90 | 1269.961 / 3770.880 |
| TPOT_ms p50 | 198.847 |
| cached/prompt | 130304 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1501.006 / 5065.186 |
| TPOT_ms p50 | 251.615 |
| cached/prompt | 0 / 174542 |
