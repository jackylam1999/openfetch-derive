# Kerb photo model: automatic tuning log

found / precise / offset per held-out box at the chosen threshold (1 m tolerance). Bar: 85% found, 0.3 m offset, every box.

| round | change tried | mean found | Mona Vale | Newport | Parramatta | threshold | minutes |
|---|---|---|---|---|---|---|---|
| 1 | starting settings | 48.4% | 64% / 76% / 0.33 m | 53% / 57% / 0.49 m | 28% / 70% / 0.4 m | 0.6 | 124 |
| 1 | more training areas | 57.2% | 75% / 72% / 0.33 m | 60% / 51% / 0.5 m | 36% / 61% / 0.41 m | 0.4 | 128 |
| 1 | train longer | 49.5% | 66% / 75% / 0.33 m | 53% / 56% / 0.49 m | 29% / 62% / 0.39 m | 0.6 | 199 |
| 2 | train longer | 57.2% | 76% / 76% / 0.31 m | 57% / 56% / 0.5 m | 39% / 66% / 0.4 m | 0.5 | 200 |
| 2 | bridge short gaps | 60.6% | 76% / 69% / 0.34 m | 60% / 47% / 0.49 m | 46% / 55% / 0.44 m | 0.4 | 128 |
| 2 | wider network | 43.2% | 61% / 78% / 0.31 m | 46% / 53% / 0.51 m | 22% / 66% / 0.41 m | 0.6 | 127 |

Round 2's log push failed (fixed 30 Oct); rows above copied from its run log. From round 3 the best version is the one with the best
balance of found and precise (mean F1), not found alone: "bridge short gaps" found more by drawing many extra lines (Newport 47% precise).
Best after round 2 by that measure: train longer (8 areas, 192 min), F1 0.605.
