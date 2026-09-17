# Hazard curve graphs

Each panel conditions on surviving to the bucket's left boundary.

- Black steps: held-out Kaplan–Meier empirical survival.
- Blue: log-survival interpolation (piecewise-constant hazard).
- Orange: linear-survival interpolation.
- Purple: no interpolation; probability changes only at the right edge.
- `object` gives every prefix equal weight; `token` weights by estimated incremental tokens.
- Infinite tail buckets are omitted because they have no finite right edge.
