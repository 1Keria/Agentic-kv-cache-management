# Log-survival interpolation calibration

Held-out samples: 23,786; events: 12,019; censored: 11,767.

| weighting | method | interior mean ECE10 | interior p90 | conditional mean ECE10 | conditional p90 |
|---|---|---:|---:|---:|---:|
| object | log_survival | 0.04185 | 0.05197 | 0.01566 | 0.04401 |
| token | log_survival | 0.03992 | 0.05442 | 0.01529 | 0.03872 |
| object | linear_survival | 0.04225 | 0.05248 | 0.01592 | 0.04401 |
| token | linear_survival | 0.04069 | 0.05654 | 0.01537 | 0.03890 |
| object | right_step | 0.05989 | 0.11698 | 0.01892 | 0.05580 |
| token | right_step | 0.06160 | 0.12681 | 0.01799 | 0.04292 |

ECE uses deciles of predicted risk and Kaplan–Meier observed risk inside each decile. Lower is better.

Limitations: the existing training loss used log-survival for partial censoring, so model-level results mildly favor log interpolation; trajectory IDs are not retained in the NPZ, so cluster-bootstrap confidence intervals are not available in this run.
