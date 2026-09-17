# Hazard Curve Interpolation Validation

This experiment uses only the held-out test split. Lower scores are better.

## Empirical Kaplan–Meier within-bin fit

| K | weighting | method | mean abs survival error | event-weighted error |
|---|---|---|---:|---:|
| K=5 | object | log_survival | 0.051045 | 0.061679 |
| K=5 | object | linear_survival | 0.053073 | 0.064543 |
| K=5 | object | right_step | 0.117980 | 0.144467 |
| K=5 | token | log_survival | 0.052328 | 0.060088 |
| K=5 | token | linear_survival | 0.054941 | 0.063629 |
| K=5 | token | right_step | 0.122463 | 0.143103 |
| K=10 | object | log_survival | 0.013996 | 0.014352 |
| K=10 | object | linear_survival | 0.016097 | 0.018519 |
| K=10 | object | right_step | 0.067137 | 0.109034 |
| K=10 | token | log_survival | 0.014650 | 0.014135 |
| K=10 | token | linear_survival | 0.016682 | 0.017945 |
| K=10 | token | right_step | 0.068220 | 0.105721 |
| K=20 | object | log_survival | 0.005360 | 0.006499 |
| K=20 | object | linear_survival | 0.005732 | 0.007266 |
| K=20 | object | right_step | 0.033971 | 0.062317 |
| K=20 | token | log_survival | 0.004710 | 0.004862 |
| K=20 | token | linear_survival | 0.004999 | 0.005522 |
| K=20 | token | right_step | 0.032660 | 0.058284 |

## Model interpolation at all interior points

| K | method | token Brier | token Bernoulli NLL | token ECE10 |
|---|---|---:|---:|---:|
| k10 | linear_survival | 0.177828 | 0.515241 | 0.042147 |
| k10 | log_survival | 0.177698 | 0.514885 | 0.041008 |
| k10 | right_step | 0.183188 | 0.550388 | 0.062967 |
| k20 | linear_survival | 0.182017 | 0.524479 | 0.039291 |
| k20 | log_survival | 0.181998 | 0.524426 | 0.039033 |
| k20 | right_step | 0.183625 | 0.531802 | 0.047890 |
| k5 | linear_survival | 0.171906 | 0.506046 | 0.053800 |
| k5 | log_survival | 0.171717 | 0.506083 | 0.052479 |
| k5 | right_step | 0.185391 | 0.775890 | 0.091370 |

## Conditional Shift interpolation

| K | age | horizon | method | token Brier | token NLL | token ECE10 |
|---|---:|---:|---|---:|---:|---:|
| k10 | 1800 | 1800 | linear_survival | 0.004540 | 0.026093 | 0.003241 |
| k10 | 1800 | 1800 | log_survival | 0.004602 | 0.026167 | 0.003012 |
| k10 | 1800 | 1800 | right_step | 0.004760 | 0.098633 | 0.004760 |
| k10 | 1800 | 3600 | linear_survival | 0.004697 | 0.025737 | 0.003134 |
| k10 | 1800 | 3600 | log_survival | 0.004824 | 0.026009 | 0.003343 |
| k10 | 1800 | 3600 | right_step | 0.004853 | 0.100563 | 0.004853 |
| k10 | 1800 | 600 | linear_survival | 0.000016 | 0.000801 | 0.000793 |
| k10 | 1800 | 600 | log_survival | 0.000036 | 0.000923 | 0.000903 |
| k10 | 1800 | 600 | right_step | 0.000000 | 0.000000 | 0.000000 |
| k10 | 20 | 20 | linear_survival | 0.074769 | 0.285425 | 0.054694 |
| k10 | 20 | 20 | log_survival | 0.074619 | 0.284019 | 0.054001 |
| k10 | 20 | 20 | right_step | 0.081199 | 1.682710 | 0.081199 |
| k10 | 20 | 5 | linear_survival | 0.046602 | 0.233229 | 0.040864 |
| k10 | 20 | 5 | log_survival | 0.046560 | 0.231643 | 0.040556 |
| k10 | 20 | 5 | right_step | 0.047543 | 0.985255 | 0.047543 |
| k10 | 20 | 60 | linear_survival | 0.073499 | 0.261938 | 0.033418 |
| k10 | 20 | 60 | log_survival | 0.073499 | 0.261938 | 0.033418 |
| k10 | 20 | 60 | right_step | 0.073501 | 0.261948 | 0.033336 |
| k10 | 5 | 20 | linear_survival | 0.210983 | 0.607512 | 0.036820 |
| k10 | 5 | 20 | log_survival | 0.210985 | 0.607517 | 0.036787 |
| k10 | 5 | 20 | right_step | 0.210993 | 0.607493 | 0.039950 |
| k10 | 5 | 5 | linear_survival | 0.150943 | 0.470411 | 0.026592 |
| k10 | 5 | 5 | log_survival | 0.150943 | 0.470411 | 0.026592 |
| k10 | 5 | 5 | right_step | 0.150943 | 0.470411 | 0.026592 |
| k10 | 5 | 60 | linear_survival | 0.215292 | 0.616993 | 0.035360 |
| k10 | 5 | 60 | log_survival | 0.215292 | 0.616993 | 0.035360 |
| k10 | 5 | 60 | right_step | 0.215291 | 0.616992 | 0.035261 |
| k10 | 600 | 1800 | linear_survival | 0.000018 | 0.001341 | 0.001332 |
| k10 | 600 | 1800 | log_survival | 0.000038 | 0.001464 | 0.001443 |
| k10 | 600 | 1800 | right_step | 0.000001 | 0.000540 | 0.000540 |
| k10 | 600 | 3600 | linear_survival | 0.004617 | 0.025714 | 0.003128 |
| k10 | 600 | 3600 | log_survival | 0.004715 | 0.025885 | 0.003034 |
| k10 | 600 | 3600 | right_step | 0.004846 | 0.041638 | 0.004642 |
| k10 | 600 | 600 | linear_survival | 0.000000 | 0.000270 | 0.000270 |
| k10 | 600 | 600 | log_survival | 0.000000 | 0.000270 | 0.000270 |
| k10 | 600 | 600 | right_step | 0.000000 | 0.000000 | 0.000000 |
| k20 | 1800 | 1800 | linear_survival | 0.004530 | 0.026580 | 0.003677 |
| k20 | 1800 | 1800 | log_survival | 0.004549 | 0.026529 | 0.003463 |
| k20 | 1800 | 1800 | right_step | 0.004757 | 0.045332 | 0.004668 |
| k20 | 1800 | 3600 | linear_survival | 0.004600 | 0.025860 | 0.003671 |
| k20 | 1800 | 3600 | log_survival | 0.004718 | 0.026111 | 0.003907 |
| k20 | 1800 | 3600 | right_step | 0.004850 | 0.046216 | 0.004758 |
| k20 | 1800 | 600 | linear_survival | 0.000000 | 0.000108 | 0.000108 |
| k20 | 1800 | 600 | log_survival | 0.000000 | 0.000108 | 0.000108 |
| k20 | 1800 | 600 | right_step | 0.000000 | 0.000217 | 0.000217 |
| k20 | 20 | 20 | linear_survival | 0.071696 | 0.258192 | 0.033870 |
| k20 | 20 | 20 | log_survival | 0.071695 | 0.258186 | 0.033857 |
| k20 | 20 | 20 | right_step | 0.072194 | 0.262335 | 0.039701 |
| k20 | 20 | 5 | linear_survival | 0.045044 | 0.191409 | 0.026497 |
| k20 | 20 | 5 | log_survival | 0.045010 | 0.190973 | 0.026049 |
| k20 | 20 | 5 | right_step | 0.047543 | 0.985255 | 0.047543 |
| k20 | 20 | 60 | linear_survival | 0.074052 | 0.264961 | 0.033997 |
| k20 | 20 | 60 | log_survival | 0.074052 | 0.264961 | 0.033997 |
| k20 | 20 | 60 | right_step | 0.074061 | 0.265024 | 0.034115 |
| k20 | 5 | 20 | linear_survival | 0.213696 | 0.613273 | 0.042813 |
| k20 | 5 | 20 | log_survival | 0.213702 | 0.613286 | 0.043166 |
| k20 | 5 | 20 | right_step | 0.213803 | 0.613366 | 0.045479 |
| k20 | 5 | 5 | linear_survival | 0.152185 | 0.473409 | 0.029625 |
| k20 | 5 | 5 | log_survival | 0.152115 | 0.473166 | 0.029899 |
| k20 | 5 | 5 | right_step | 0.157513 | 0.493850 | 0.071943 |
| k20 | 5 | 60 | linear_survival | 0.217920 | 0.622420 | 0.037353 |
| k20 | 5 | 60 | log_survival | 0.217920 | 0.622420 | 0.037353 |
| k20 | 5 | 60 | right_step | 0.217920 | 0.622420 | 0.037594 |
| k20 | 600 | 1800 | linear_survival | 0.000001 | 0.000426 | 0.000426 |
| k20 | 600 | 1800 | log_survival | 0.000001 | 0.000426 | 0.000426 |
| k20 | 600 | 1800 | right_step | 0.000001 | 0.000426 | 0.000426 |
| k20 | 600 | 3600 | linear_survival | 0.004567 | 0.026107 | 0.003485 |
| k20 | 600 | 3600 | log_survival | 0.004630 | 0.026190 | 0.003334 |
| k20 | 600 | 3600 | right_step | 0.004848 | 0.042892 | 0.004699 |
| k20 | 600 | 600 | linear_survival | 0.000000 | 0.000209 | 0.000209 |
| k20 | 600 | 600 | log_survival | 0.000000 | 0.000209 | 0.000209 |
| k20 | 600 | 600 | right_step | 0.000000 | 0.000209 | 0.000209 |
| k5 | 20 | 20 | linear_survival | 0.074521 | 0.281691 | 0.054550 |
| k5 | 20 | 20 | log_survival | 0.074361 | 0.280227 | 0.053825 |
| k5 | 20 | 20 | right_step | 0.081199 | 1.682710 | 0.081199 |
| k5 | 20 | 5 | linear_survival | 0.046559 | 0.230779 | 0.040889 |
| k5 | 20 | 5 | log_survival | 0.046513 | 0.229114 | 0.040568 |
| k5 | 20 | 5 | right_step | 0.047543 | 0.985255 | 0.047543 |
| k5 | 20 | 60 | linear_survival | 0.073205 | 0.259184 | 0.031688 |
| k5 | 20 | 60 | log_survival | 0.073205 | 0.259184 | 0.031688 |
| k5 | 20 | 60 | right_step | 0.073210 | 0.259221 | 0.031688 |
| k5 | 5 | 20 | linear_survival | 0.204423 | 0.593767 | 0.042251 |
| k5 | 5 | 20 | log_survival | 0.204422 | 0.593767 | 0.042598 |
| k5 | 5 | 20 | right_step | 0.204503 | 0.593901 | 0.043631 |
| k5 | 5 | 5 | linear_survival | 0.159345 | 0.503248 | 0.089602 |
| k5 | 5 | 5 | log_survival | 0.154810 | 0.487011 | 0.071791 |
| k5 | 5 | 5 | right_step | 0.196924 | 4.080911 | 0.196924 |
| k5 | 5 | 60 | linear_survival | 0.208932 | 0.603861 | 0.037335 |
| k5 | 5 | 60 | log_survival | 0.208932 | 0.603861 | 0.037335 |
| k5 | 5 | 60 | right_step | 0.208933 | 0.603863 | 0.037308 |

## Interpretation guardrails

- Existing MLP endpoints are reused; this is a post-hoc interpolation test.
- The original training loss used partial-censor log-survival interpolation, so the model-level comparison mildly favors log-survival. The Kaplan–Meier comparison does not share that training dependency.
- Tail mass beyond the final finite edge cannot be interpolated and is excluded from age+horizon pairs beyond that edge.
