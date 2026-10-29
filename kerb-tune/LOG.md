# Kerb photo model: automatic tuning log

found / precise / offset per held-out box at the chosen threshold (1 m tolerance). Bar: 85% found, 0.3 m offset, every box.

| round | change tried | mean found | Mona Vale | Newport | Parramatta | threshold | minutes |
|---|---|---|---|---|---|---|---|
| 1 | starting settings | 48.4% | 64% / 76% / 0.33 m | 53% / 57% / 0.49 m | 28% / 70% / 0.4 m | 0.6 | 124 |
| 1 | more training areas | 57.2% | 75% / 72% / 0.33 m | 60% / 51% / 0.5 m | 36% / 61% / 0.41 m | 0.4 | 128 |
| 1 | train longer | 49.5% | 66% / 75% / 0.33 m | 53% / 56% / 0.49 m | 29% / 62% / 0.39 m | 0.6 | 199 |
