# Expanded long-window conditional calibration

ECE10 uses Kaplan-Meier observed risk. Normalized ECE is ECE / observed risk.

| weighting | method | slice | checks | observed risk | predicted risk | mean ECE10 | normalized ECE |
|---|---|---|---:|---:|---:|---:|---:|
| object | log_survival | all | 186 | 0.18998 | 0.18513 | 0.02669 | 0.141 |
| object | log_survival | interior_only | 155 | 0.18796 | 0.18250 | 0.02663 | 0.142 |
| object | log_survival | observed_risk_ge_5pct | 116 | 0.30168 | 0.29278 | 0.04027 | 0.133 |
| object | log_survival | observed_risk_ge_10pct | 86 | 0.38438 | 0.37517 | 0.04838 | 0.126 |
| object | log_survival | long_horizon_ge_600s | 75 | 0.15604 | 0.15665 | 0.02022 | 0.130 |
| token | log_survival | all | 186 | 0.19450 | 0.18294 | 0.02528 | 0.130 |
| token | log_survival | interior_only | 155 | 0.19257 | 0.18049 | 0.02527 | 0.131 |
| token | log_survival | observed_risk_ge_5pct | 117 | 0.30765 | 0.28884 | 0.03848 | 0.125 |
| token | log_survival | observed_risk_ge_10pct | 86 | 0.38895 | 0.37403 | 0.04078 | 0.105 |
| token | log_survival | long_horizon_ge_600s | 75 | 0.16047 | 0.15311 | 0.01916 | 0.119 |
| object | linear_survival | all | 186 | 0.18998 | 0.18447 | 0.02680 | 0.141 |
| object | linear_survival | interior_only | 155 | 0.18796 | 0.18170 | 0.02676 | 0.142 |
| object | linear_survival | observed_risk_ge_5pct | 116 | 0.30168 | 0.29192 | 0.04047 | 0.134 |
| object | linear_survival | observed_risk_ge_10pct | 86 | 0.38438 | 0.37425 | 0.04866 | 0.127 |
| object | linear_survival | long_horizon_ge_600s | 75 | 0.15604 | 0.15626 | 0.02012 | 0.129 |
| token | linear_survival | all | 186 | 0.19450 | 0.18242 | 0.02562 | 0.132 |
| token | linear_survival | interior_only | 155 | 0.19257 | 0.17987 | 0.02567 | 0.133 |
| token | linear_survival | observed_risk_ge_5pct | 117 | 0.30765 | 0.28809 | 0.03903 | 0.127 |
| token | linear_survival | observed_risk_ge_10pct | 86 | 0.38895 | 0.37317 | 0.04147 | 0.107 |
| token | linear_survival | long_horizon_ge_600s | 75 | 0.16047 | 0.15303 | 0.01919 | 0.120 |
| object | right_step | all | 186 | 0.18998 | 0.17063 | 0.03544 | 0.187 |
| object | right_step | interior_only | 155 | 0.18796 | 0.16509 | 0.03713 | 0.198 |
| object | right_step | observed_risk_ge_5pct | 116 | 0.30168 | 0.27230 | 0.05392 | 0.179 |
| object | right_step | observed_risk_ge_10pct | 86 | 0.38438 | 0.35097 | 0.06436 | 0.167 |
| object | right_step | long_horizon_ge_600s | 75 | 0.15604 | 0.15180 | 0.02122 | 0.136 |
| token | right_step | all | 186 | 0.19450 | 0.16966 | 0.03554 | 0.183 |
| token | right_step | interior_only | 155 | 0.19257 | 0.16456 | 0.03758 | 0.195 |
| token | right_step | observed_risk_ge_5pct | 117 | 0.30765 | 0.26905 | 0.05485 | 0.178 |
| token | right_step | observed_risk_ge_10pct | 86 | 0.38895 | 0.35006 | 0.06039 | 0.155 |
| token | right_step | long_horizon_ge_600s | 75 | 0.16047 | 0.15145 | 0.01972 | 0.123 |
