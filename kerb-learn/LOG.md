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

_No round 2: that slot was cancelled when the loop moved to 5 versions per round (30 Oct 07:16Z); round 3 is the second learning round._

## Round 3 (started from the round 1 model (ImageNet start + unbroken-line loss, bigger view))

| round | change | check F1 | Mona Vale | Newport | Parramatta | threshold | minutes |
|---|---|---|---|---|---|---|---|
| 3 | learn from misses (in shadow) | 0.731 | 86% / 70% / 0.32 m | 71% / 52% / 0.49 m | 62% / 58% / 0.42 m | 0.6 | 151 |
| 3 | learn from misses (clear kerb) | 0.737 | 85% / 69% / 0.31 m | 71% / 51% / 0.49 m | 65% / 62% / 0.38 m | 0.6 | 176 |
| 3 | learn from extra lines | 0.749 | 86% / 72% / 0.31 m | 71% / 56% / 0.47 m | 62% / 63% / 0.4 m | 0.6 | 177 |
| 3 | learn from misses (under trees) | 0.734 | 85% / 69% / 0.34 m | 68% / 49% / 0.5 m | 64% / 62% / 0.43 m | 0.6 | 166 |
| 3 | learn from misses (faint kerb) | 0.713 | 84% / 66% / 0.34 m | 68% / 47% / 0.48 m | 60% / 54% / 0.4 m | 0.6 | 136 |

- learn from misses (in shadow): found by cause: under trees 73% (was 75%) of 15.5 km; in shadow 65% (was 66%) of 27.5 km; cars or clutter 82% (was 82%) of 12.2 km; faint kerb 52% (was 53%) of 3.8 km; clear kerb 84% (was 85%) of 55.3 km. Extra lines 37.2 km (was 34.9 km). Whole kerb lines found (held-out) 55%.
- learn from misses (clear kerb): found by cause: under trees 73% (was 75%) of 15.5 km; in shadow 67% (was 66%) of 27.5 km; cars or clutter 82% (was 82%) of 12.2 km; faint kerb 55% (was 53%) of 3.8 km; clear kerb 85% (was 85%) of 55.3 km. Extra lines 36.6 km (was 34.9 km). Whole kerb lines found (held-out) 60%.
- learn from extra lines: found by cause: under trees 73% (was 75%) of 15.5 km; in shadow 66% (was 66%) of 27.5 km; cars or clutter 82% (was 82%) of 12.2 km; faint kerb 52% (was 53%) of 3.8 km; clear kerb 84% (was 85%) of 55.3 km. Extra lines 32.6 km (was 34.9 km). Whole kerb lines found (held-out) 57%.
- learn from misses (under trees): found by cause: under trees 74% (was 75%) of 15.5 km; in shadow 67% (was 66%) of 27.5 km; cars or clutter 81% (was 82%) of 12.2 km; faint kerb 52% (was 53%) of 3.8 km; clear kerb 84% (was 85%) of 55.3 km. Extra lines 36.5 km (was 34.9 km). Whole kerb lines found (held-out) 56%.
- learn from misses (faint kerb): found by cause: under trees 72% (was 75%) of 15.5 km; in shadow 65% (was 66%) of 27.5 km; cars or clutter 79% (was 82%) of 12.2 km; faint kerb 56% (was 53%) of 3.8 km; clear kerb 82% (was 85%) of 55.3 km. Extra lines 42.6 km (was 34.9 km). Whole kerb lines found (held-out) 50%.

**Kept: learn from extra lines (check F1 0.749, was 0.740). Its biggest misses on the training boxes: in shadow 15.5 km, clear kerb 13.2 km, under trees 12.8 km; the next round trains on those.**

_Round 4 restarted 30 Oct ~10:50Z with two changes from Jacky's review: road centrelines and water areas (official NSW data) as extra map context, and a tidy step that straightens straight runs, smooths curves and joins short gaps._
