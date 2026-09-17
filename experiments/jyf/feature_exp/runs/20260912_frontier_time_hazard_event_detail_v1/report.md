# Wall-clock real-frontier feature ablation

Each row uses the same fixed-width two-layer 128-hidden-unit hazard MLP and a 10-seed hazard ensemble. Prefix digests are split 70/15/15.
The label is seconds from frontier `wall_s` to the next demand `wall_s`; K=10 finite edges are 2/5/10/20/60/180/600/1800/7200 seconds.
Training uses censor-aware discrete-hazard NLL, sqrt-token weights, and equal total cold/warm weight.

Rows: 26785; unique digests: 1652; left-truncated warm rows excluded: 3100.

## all

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| time_plus_age_events | 0.95929 | 0.28402 | 0.9438 | 0.29630 | 0.9439 | 0.34242 | 0.9238 |
| time_plus_idle_events | 0.98543 | 0.30989 | 0.9365 | 0.31819 | 0.9363 | 0.35035 | 0.9195 |
| time_plus_recent_gap_events | 0.96414 | 0.28103 | 0.9463 | 0.29091 | 0.9466 | 0.33936 | 0.9274 |
| time_plus_gap_ewma_events | 0.96423 | 0.28178 | 0.9460 | 0.29350 | 0.9452 | 0.34464 | 0.9251 |
| time_plus_gap_std_events | 0.98320 | 0.29907 | 0.9403 | 0.31087 | 0.9375 | 0.35362 | 0.9220 |
| time_plus_event_gap_stats | 0.95899 | 0.27741 | 0.9480 | 0.28774 | 0.9481 | 0.33598 | 0.9298 |
| both_minus_age_events | 0.94830 | 0.27587 | 0.9489 | 0.28880 | 0.9478 | 0.33741 | 0.9268 |
| both_minus_idle_events | 0.93397 | 0.26306 | 0.9528 | 0.28243 | 0.9513 | 0.33076 | 0.9308 |
| both_minus_event_gap_stats | 0.97044 | 0.29420 | 0.9406 | 0.30533 | 0.9401 | 0.34871 | 0.9205 |
| both_no_gap_present | 0.93242 | 0.27037 | 0.9507 | 0.28202 | 0.9513 | 0.32993 | 0.9299 |

## cold

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| time_plus_age_events | 0.82624 | 0.19408 | 0.9351 | 0.26835 | 0.9316 | 0.51587 | 0.8081 |
| time_plus_idle_events | 0.83250 | 0.20031 | 0.9346 | 0.27960 | 0.9286 | 0.50502 | 0.8082 |
| time_plus_recent_gap_events | 0.83606 | 0.19373 | 0.9390 | 0.26747 | 0.9331 | 0.51497 | 0.8096 |
| time_plus_gap_ewma_events | 0.83562 | 0.19211 | 0.9398 | 0.26511 | 0.9337 | 0.51506 | 0.8097 |
| time_plus_gap_std_events | 0.83832 | 0.19458 | 0.9387 | 0.26849 | 0.9328 | 0.51299 | 0.8110 |
| time_plus_event_gap_stats | 0.83641 | 0.19352 | 0.9385 | 0.26635 | 0.9331 | 0.51337 | 0.8092 |
| both_minus_age_events | 0.82957 | 0.19418 | 0.9365 | 0.26870 | 0.9299 | 0.51530 | 0.8081 |
| both_minus_idle_events | 0.82572 | 0.19434 | 0.9348 | 0.26841 | 0.9314 | 0.51372 | 0.8084 |
| both_minus_event_gap_stats | 0.82460 | 0.19508 | 0.9332 | 0.27091 | 0.9301 | 0.51499 | 0.8084 |
| both_no_gap_present | 0.81506 | 0.19264 | 0.9345 | 0.26591 | 0.9324 | 0.50810 | 0.8106 |

## warm

| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| time_plus_age_events | 1.03931 | 0.33812 | 0.9134 | 0.31311 | 0.9175 | 0.23810 | 0.9395 |
| time_plus_idle_events | 1.07740 | 0.37579 | 0.9013 | 0.34139 | 0.9013 | 0.25732 | 0.9315 |
| time_plus_recent_gap_events | 1.04117 | 0.33354 | 0.9174 | 0.30500 | 0.9250 | 0.23375 | 0.9491 |
| time_plus_gap_ewma_events | 1.04158 | 0.33570 | 0.9170 | 0.31057 | 0.9204 | 0.24214 | 0.9435 |
| time_plus_gap_std_events | 1.07034 | 0.36192 | 0.9081 | 0.33636 | 0.9031 | 0.25777 | 0.9336 |
| time_plus_event_gap_stats | 1.03271 | 0.32787 | 0.9213 | 0.30060 | 0.9279 | 0.22929 | 0.9506 |
| both_minus_age_events | 1.01971 | 0.32500 | 0.9242 | 0.30089 | 0.9288 | 0.23042 | 0.9500 |
| both_minus_idle_events | 0.99908 | 0.30439 | 0.9309 | 0.29086 | 0.9352 | 0.22073 | 0.9543 |
| both_minus_event_gap_stats | 1.05815 | 0.35381 | 0.9083 | 0.32602 | 0.9107 | 0.24871 | 0.9347 |
| both_no_gap_present | 1.00301 | 0.31712 | 0.9274 | 0.29171 | 0.9347 | 0.22277 | 0.9518 |

