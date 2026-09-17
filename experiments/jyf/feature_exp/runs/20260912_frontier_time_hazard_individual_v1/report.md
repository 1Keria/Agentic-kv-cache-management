# Wall-clock real-frontier feature ablation

Each row uses the same fixed-width two-layer 128-hidden-unit hazard MLP and a 10-seed hazard ensemble. Prefix digests are split 70/15/15.
The label is seconds from frontier `wall_s` to the next demand `wall_s`; K=10 finite edges are 2/5/10/20/60/180/600/1800/7200 seconds.
Training uses censor-aware discrete-hazard NLL, sqrt-token weights, and equal total cold/warm weight.

Rows: 26785; unique digests: 1652; left-truncated warm rows excluded: 3100.

## all

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| both_minus_age_seconds | 0.93508 | 0.26227 | 0.9535 | 0.29493 | 0.9478 | 0.33077 | 0.9306 |
| both_minus_idle_seconds | 1.04022 | 0.32180 | 0.9333 | 0.32841 | 0.9343 | 0.37707 | 0.9092 |
| both_minus_recent_gap_events | 0.93171 | 0.26438 | 0.9530 | 0.28274 | 0.9506 | 0.32943 | 0.9303 |
| both_minus_recent_gap_seconds | 0.93767 | 0.27076 | 0.9496 | 0.28426 | 0.9501 | 0.33254 | 0.9290 |
| both_minus_gap_ewma_events | 0.92755 | 0.26505 | 0.9527 | 0.28239 | 0.9509 | 0.32996 | 0.9299 |
| both_minus_gap_ewma_seconds | 0.93127 | 0.26439 | 0.9525 | 0.28180 | 0.9508 | 0.33202 | 0.9294 |
| both_minus_gap_std_events | 0.93713 | 0.26497 | 0.9520 | 0.28005 | 0.9517 | 0.33531 | 0.9276 |
| both_minus_gap_std_seconds | 0.93702 | 0.26475 | 0.9518 | 0.28245 | 0.9511 | 0.33082 | 0.9300 |
| both_minus_hits | 0.94814 | 0.28278 | 0.9466 | 0.29245 | 0.9465 | 0.33466 | 0.9281 |
| both_minus_node_tokens | 0.96881 | 0.27193 | 0.9501 | 0.29787 | 0.9453 | 0.36281 | 0.9124 |
| both_minus_path_tokens | 0.94832 | 0.26607 | 0.9524 | 0.28929 | 0.9484 | 0.34396 | 0.9247 |
| both_minus_lru | 0.93108 | 0.26611 | 0.9526 | 0.27924 | 0.9522 | 0.32773 | 0.9322 |
| both_minus_traffic | 0.95432 | 0.27606 | 0.9490 | 0.29679 | 0.9462 | 0.33661 | 0.9290 |

## cold

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| both_minus_age_seconds | 0.85568 | 0.20390 | 0.9241 | 0.28886 | 0.9199 | 0.51559 | 0.8043 |
| both_minus_idle_seconds | 0.84641 | 0.20437 | 0.9260 | 0.28578 | 0.9220 | 0.50658 | 0.8107 |
| both_minus_recent_gap_events | 0.81848 | 0.19247 | 0.9355 | 0.26682 | 0.9310 | 0.51159 | 0.8094 |
| both_minus_recent_gap_seconds | 0.81959 | 0.19255 | 0.9358 | 0.26666 | 0.9317 | 0.51181 | 0.8105 |
| both_minus_gap_ewma_events | 0.81763 | 0.19285 | 0.9352 | 0.26812 | 0.9304 | 0.51026 | 0.8089 |
| both_minus_gap_ewma_seconds | 0.81573 | 0.19236 | 0.9357 | 0.26576 | 0.9316 | 0.51127 | 0.8096 |
| both_minus_gap_std_events | 0.82381 | 0.19350 | 0.9348 | 0.26810 | 0.9308 | 0.51298 | 0.8084 |
| both_minus_gap_std_seconds | 0.82399 | 0.19477 | 0.9347 | 0.26811 | 0.9308 | 0.51300 | 0.8080 |
| both_minus_hits | 0.82108 | 0.19354 | 0.9348 | 0.26653 | 0.9315 | 0.51232 | 0.8093 |
| both_minus_node_tokens | 0.91105 | 0.21049 | 0.9270 | 0.32008 | 0.9109 | 0.59949 | 0.7489 |
| both_minus_path_tokens | 0.82084 | 0.19347 | 0.9352 | 0.26918 | 0.9309 | 0.51544 | 0.8048 |
| both_minus_lru | 0.82158 | 0.19339 | 0.9363 | 0.26283 | 0.9349 | 0.50859 | 0.8147 |
| both_minus_traffic | 0.86608 | 0.22061 | 0.9063 | 0.30487 | 0.9139 | 0.52933 | 0.8120 |

## warm

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| both_minus_age_seconds | 0.98283 | 0.29738 | 0.9344 | 0.29858 | 0.9328 | 0.21962 | 0.9554 |
| both_minus_idle_seconds | 1.15679 | 0.39242 | 0.9007 | 0.35405 | 0.9108 | 0.29918 | 0.9284 |
| both_minus_recent_gap_events | 0.99982 | 0.30763 | 0.9315 | 0.29232 | 0.9343 | 0.21987 | 0.9537 |
| both_minus_recent_gap_seconds | 1.00868 | 0.31779 | 0.9242 | 0.29485 | 0.9329 | 0.22473 | 0.9517 |
| both_minus_gap_ewma_events | 0.99367 | 0.30848 | 0.9309 | 0.29097 | 0.9359 | 0.22152 | 0.9538 |
| both_minus_gap_ewma_seconds | 1.00077 | 0.30771 | 0.9303 | 0.29145 | 0.9343 | 0.22422 | 0.9524 |
| both_minus_gap_std_events | 1.00529 | 0.30796 | 0.9288 | 0.28723 | 0.9369 | 0.22846 | 0.9503 |
| both_minus_gap_std_seconds | 1.00500 | 0.30684 | 0.9291 | 0.29108 | 0.9352 | 0.22125 | 0.9544 |
| both_minus_hits | 1.02456 | 0.33646 | 0.9194 | 0.30804 | 0.9258 | 0.22781 | 0.9517 |
| both_minus_node_tokens | 1.00355 | 0.30888 | 0.9315 | 0.28452 | 0.9398 | 0.22047 | 0.9555 |
| both_minus_path_tokens | 1.02499 | 0.30974 | 0.9306 | 0.30138 | 0.9306 | 0.24082 | 0.9481 |
| both_minus_lru | 0.99695 | 0.30984 | 0.9312 | 0.28911 | 0.9359 | 0.21896 | 0.9548 |
| both_minus_traffic | 1.00740 | 0.30941 | 0.9289 | 0.29194 | 0.9334 | 0.22070 | 0.9543 |

