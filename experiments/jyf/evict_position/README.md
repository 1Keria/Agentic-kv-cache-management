# Eviction inference position experiment

Remote root: `/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/evict_position`.

This experiment trains a seconds Unified Hazard MLP from the existing frozen
frontier trace and compares **LRU**, **on-demand**, and **precompute with waiting**
in actual SGLang Full/SWA cache eviction. There is no 16-candidate shortlist.

## Reproduce

Use `/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python`. From this directory:

```bash
python train.py --trace-dir ../nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace --output-dir training
python prepare_workload.py
EP_MODE=precompute EP_TEST=1 EP_OUT=tests/precompute EP_CHECKPOINT=training/model.pt python test_cache.py
EP_MODE=on_demand EP_TEST=1 EP_OUT=tests/on_demand EP_CHECKPOINT=training/model.pt python test_cache.py
bash run_online.sh unique_run_name
python report.py online_runs/unique_run_name --output report_zh.md
```

Training and workload creation deliberately refuse to overwrite existing outputs.
Serving checks the port and all eight GPUs are free. It terminates only the server
process that it starts. Runs preserve API results, server logs, eight TP rank logs,
source snapshots, checkpoint/workload hashes, and effective server configuration.
Use `ONLINE_MODES='lru on_demand precompute'` to vary run order.

## Shared model

The copied `training_base.py` implements the original feature experiment, with
checkpoint export added. The selected 16 features occupy the original fixed 24
input columns; excluded columns are zero after train-only standardization.
Architecture is 24 → 128 → 128 → 9 logits. Nine finite conditional hazards plus
the remaining tail mass define ten buckets with finite edges
2/5/10/20/60/180/600/1800/7200 seconds. Seeds 41/42/43 train independently; the
checkpoint with smallest weighted validation censor NLL is selected. Cold and
warm total training weights are equal, with sqrt-token weighting within groups.
No serving-test outcomes are used for checkpoint selection.

The label is time from a frontier observation to the next stable-prefix demand,
including right censoring. It does not estimate unloaded request execution time.
Training retains the old prefix-digest split. The serving workload is additionally
filtered against training-replay sessions, source trajectories, and first-user
message hashes. Shared system prefixes can still overlap.

## Policy invariants

1. Enumerate all legal candidates using native Full/SWA lock-aware list iterators.
2. Rank zero chooses the lowest current value and broadcasts the complete frontier
   signature and selected index; every rank checks the same candidate universe.
3. Preserve native free/lock/tombstone behavior. After each victim, enumerate the
   new frontier, so newly exposed ancestors cannot be skipped.
4. On-demand computes missing curves at eviction; within an eviction, unchanged
   nodes reuse their curve and newly exposed nodes are predicted as necessary.
5. Precompute snapshots affected nodes and their ancestors, including internal
   nodes, at request-end. Structural changes during standalone match/insert or
   unfinished caching can occur before request-end, so those mutation boundaries
   also submit predictions. These are separately counted as `submit.source`.
6. Each node-side ticket holds an immutable snapshot timestamp and a shared batch
   future. At eviction an unfinished future is awaited; the model is never started
   there in precompute mode. A missing ticket is a fatal coverage error, not LRU.
7. Replaced tickets are independent of old futures. An old completion cannot
   overwrite the prediction for a newer snapshot.
8. Time conditioning is evaluated at use via log-survival ratios. This adjusts
   waiting time, not changes to other nodes' event counts/LRU positions. The
   prototype scans current candidates for exact greedy selection under its score.

## Value definition

`V = path_tokens / node_tokens × sum(p_k * D_k)`.

The decision bins are 0/2/5/10/20/60 seconds relative to the decision. Each `p_k`
comes from `S(age + left)/S(age) - S(age + right)/S(age)` using piecewise-linear
log survival. `D_k = 2 ** (-midpoint / 20)` and all later reuse has zero weight.
The horizon and half-life are fixed before online results, not tuned on test.
Predictions beyond the finite 7200-second support cause a clear error; the current
accelerated experiments do not require extrapolating the infinite tail.

The denominator is occupancy in the pool currently under pressure. Its fixed
bytes/token cancels in candidate ranking. This is a token-cost approximation,
not a measured nonlinear prefill cost or optimal tree-wide batch eviction.
Native forced tombstone cleanup is a structural necessity outside selectable
victim ranking and remains unchanged.

## Interpretation

This is closed-loop serving: later turns in a session wait for earlier turns, so
policies can change arrival times as well as cache state. Report actual token hit
rate, TTFT/E2E, completion rate, eviction/request-end time, waiting, submitted and
on-demand predictions, and TP consistency. Uncached prompt tokens include first
access and are not all eviction-induced recomputation. The decode cap is 32;
this is controlled cache pressure, not a full production agent workload.

The precompute predictor is trained on eviction-frontier observations, so changing
the inference landmark to request-end is a distribution shift. Internal Full nodes
use a virtual insertion LRU fraction before becoming leaves. These limitations are
explicit and shared checkpoint comparisons must be interpreted accordingly.
