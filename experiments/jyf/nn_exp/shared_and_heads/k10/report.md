# 10-bucket Unified MLP vs Shared Cold/Warm Heads

## Output definition

The model emits a softmax distribution over 10 mutually exclusive next-reuse-distance buckets, measured in future cache-access events:

`(0,1]`, `(1,2]`, `(2,5]`, `(5,10]`, `(10,20]`, `(20,50]`, `(50,100]`, `(100,200]`, `(200,500]`, `(500,+inf)`.

Observed reuse uses exact-bucket cross entropy. A sample censored after event distance `c` uses `-log(sum p[k])` over all buckets still possible after `c`. Cold and warm losses are averaged with equal group weight. Train/validation/test are split 70/15/15 by prefix digest. Results are three-seed ensembles (41/42/43).

## Overall test

| Metric | Unified | Shared + heads | Winner |
|---|---:|---:|---|
| Exact bucket accuracy | 0.3551 | 0.3177 | Unified |
| Multiclass Brier | 0.8131 | 0.8415 | Unified |
| Token multiclass Brier | 0.7958 | 0.8131 | Unified |
| Exact NLL | 1.7891 | 1.8789 | Unified |
| Censor-aware NLL | 1.2803 | 1.3440 | Unified |

There are 3,289 exact-reuse test exposures and 2,139 right-censored test exposures.

## Derived cumulative predictions

| Scope | Horizon | Metric | Unified | Shared + heads |
|---|---:|---|---:|---:|
| Overall | 5 | AUC / Brier | 0.8739 / 0.13878 | 0.8452 / 0.15483 |
| Overall | 20 | AUC / Brier | 0.8739 / 0.14303 | 0.8613 / 0.14993 |
| Overall | 100 | AUC / Brier | 0.8925 / 0.13026 | 0.8856 / 0.13387 |
| Cold | 5 | AUC / token-Brier | 0.8214 / 0.08772 | 0.7905 / 0.09655 |
| Cold | 20 | AUC / token-Brier | 0.7809 / 0.14592 | 0.7554 / 0.15646 |
| Cold | 100 | AUC / token-Brier | 0.7970 / 0.12985 | 0.7932 / 0.13528 |

Unified also wins all reported warm-subset ranking and calibration metrics.

## Model dimensions

- Unified: `16 -> 64 -> 32 -> 10`, 3,498 parameters.
- Shared heads: shared `16 -> 56 -> 28`, then cold `28 -> 10` and warm `28 -> 10`, 3,128 parameters.

## Conclusion

Use the 10-bucket Unified MLP. Explicit `is_cold` and history-presence masks are sufficient for this trace; splitting the output mapping reduces effective training data and consistently hurts generalization. Keep cold handling in the input representation and optional grace-period policy rather than in a separate neural head.
