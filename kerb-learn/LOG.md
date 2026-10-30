# Kerb photo model: learning log

Each round starts from the best model so far and trains on its mistakes. Check F1 = balance of found and precise on the check boxes (inside the training councils), used to keep or drop a model. Held-out boxes (never trained on, Parramatta a council never seen): found / precise / median offset within 1 m. Bar: 85% found, 0.3 m, every held-out box.

## Round 1 (started from the ImageNet encoder)

| round | change | check F1 | Mona Vale | Newport | Parramatta | threshold | minutes |
|---|---|---|---|---|---|---|---|
| 1 | ImageNet start | 0.735 | 82% / 73% / 0.29 m | 68% / 56% / 0.51 m | 59% / 66% / 0.38 m | 0.6 | 227 |
| 1 | ImageNet start + unbroken-line loss | 0.714 | 85% / 67% / 0.31 m | 70% / 47% / 0.5 m | 63% / 59% / 0.39 m | 0.6 | 228 |
| 1 | ImageNet start + unbroken-line loss, bigger view | 0.740 | 86% / 70% / 0.3 m | 72% / 53% / 0.5 m | 64% / 63% / 0.4 m | 0.6 | 186 |

- ImageNet start: found by cause: under trees 66% of 15.5 km; in shadow 59% of 27.5 km; cars or clutter 80% of 12.2 km; faint kerb 51% of 3.8 km; clear kerb 83% of 55.3 km. Extra lines 30.1 km. Whole kerb lines found (held-out) 54%.
- ImageNet start + unbroken-line loss: found by cause: under trees 72% of 15.5 km; in shadow 64% of 27.5 km; cars or clutter 82% of 12.2 km; faint kerb 52% of 3.8 km; clear kerb 84% of 55.3 km. Extra lines 40.4 km. Whole kerb lines found (held-out) 57%.
- ImageNet start + unbroken-line loss, bigger view: found by cause: under trees 75% of 15.5 km; in shadow 66% of 27.5 km; cars or clutter 82% of 12.2 km; faint kerb 53% of 3.8 km; clear kerb 85% of 55.3 km. Extra lines 34.9 km. Whole kerb lines found (held-out) 59%.

**Kept: ImageNet start + unbroken-line loss, bigger view (check F1 0.740). Its biggest misses on the training boxes: in shadow 16.3 km, clear kerb 13.5 km, under trees 12.8 km; the next round trains on those.**

## Round 2 (started from the round 1 model (ImageNet start + unbroken-line loss, bigger view))

| round | change | check F1 | Mona Vale | Newport | Parramatta | threshold | minutes |
|---|---|---|---|---|---|---|---|


**Nothing kept: no variant beat check F1 0.740 by 0.005; the round 1 model stays and the next round tries the next causes.**

**Stopped after round 2: no results this round (jobs failed).** Best: ImageNet start + unbroken-line loss, bigger view (round 1), held-out mean found 74.1%, model: run 40986680973 artifact learn-40986680973-1-2.
