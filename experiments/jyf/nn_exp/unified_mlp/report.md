# Unified MLP vs Shared Trunk + Cold/Warm Heads

## Setup

- Source: complete frozen real-frontier trace, 2000 successful turns / 533 sessions.
- Horizons: reuse within 5, 20, and 100 future cache-access events.
- Split: 70/15/15 by stable prefix digest.
- Right censoring: unobservable horizon cells are masked from loss and metrics.
- Training loss: masked BCE, with cold and warm groups receiving equal weight.
- Features and training settings are identical between architectures.
- Seeds: 41, 42, 43; reported predictions are a three-seed ensemble.

Unified MLP has 3,267 parameters. Shared trunk plus two heads has 2,722 parameters.

## Overall test results

| Horizon | Architecture | AUC | AP | Brier | token-Brier | NLL |
|---:|---|---:|---:|---:|---:|---:|
| 5 | Unified | 0.8812 | 0.8001 | 0.13373 | 0.15300 | 0.41821 |
| 5 | Shared + heads | 0.8663 | 0.7790 | 0.14219 | 0.15744 | 0.43843 |
| 20 | Unified | 0.8823 | 0.8724 | 0.13679 | 0.14375 | 0.43199 |
| 20 | Shared + heads | 0.8758 | 0.8655 | 0.14107 | 0.14485 | 0.44340 |
| 100 | Unified | 0.9030 | 0.9371 | 0.12260 | 0.10076 | 0.38063 |
| 100 | Shared + heads | 0.8938 | 0.9308 | 0.12849 | 0.10591 | 0.39673 |

Unified wins every overall metric at every horizon.

## Cold-only test results

| Horizon | Architecture | AUC | AP | Brier | token-Brier | NLL |
|---:|---|---:|---:|---:|---:|---:|
| 5 | Unified | 0.8081 | 0.4581 | 0.07374 | **0.09110** | **0.26144** |
| 5 | Shared + heads | 0.7923 | **0.4660** | **0.07341** | 0.09164 | 0.26442 |
| 20 | Unified | 0.7871 | 0.5219 | 0.14024 | 0.14073 | 0.43715 |
| 20 | Shared + heads | **0.7887** | **0.5379** | **0.13899** | **0.13500** | **0.43068** |
| 100 | Unified | **0.8026** | **0.7096** | **0.18262** | **0.13292** | 0.54307 |
| 100 | Shared + heads | 0.7950 | 0.7009 | 0.18465 | 0.13581 | **0.54205** |

The cold subset is mixed rather than showing a consistent two-head advantage. The meaningful two-head gain is concentrated at horizon 20; Unified is better on most horizon-100 metrics and cold token-Brier at horizons 5 and 100.

## Warm-only result

Unified wins AUC, AP, Brier, token-Brier, and NLL at all three horizons. Splitting the output head reduces the amount of data available to each mapping and hurts warm generalization.

## Decision

Use one Unified MLP with explicit missingness representation:

- `is_cold`
- `history_length`
- gap-present masks
- zero-filled normalized history values only when the corresponding mask is zero

There is no evidence here that completely separate cold/warm heads justify their additional routing complexity. Keep a short cold grace-period rule as an operational safety guard, but let the same MLP score both cold and warm candidates.

The next useful experiment is not a larger network. It is an eviction replay using Unified scores versus LRU and the grace-period rule, evaluated by recomputed tokens and evicted-then-soon-reused tokens.
