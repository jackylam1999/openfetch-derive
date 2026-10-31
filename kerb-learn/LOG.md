# Kerb photo model: log (method v2)

Scenario score = mean over scenarios of the mean box F1 (found and precise within 1 m). Site share = share of 250 m tiles with 85%+ found and median offset 0.3 m or less.

## Round 1

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| noise seed 11 | 0.719 | 0.666 | 25% | 0.742 | 0.904 | 0.737 | 0.620 | 0.591 |
| noise seed 22 | 0.725 | 0.665 | 27% | 0.741 | 0.904 | 0.736 | 0.653 | 0.591 |
| noise seed 33 | 0.721 | 0.662 | 25% | 0.736 | 0.906 | 0.737 | 0.633 | 0.595 |

Held-out (found/precise/median offset): monavale 88%/70%/0.28 m; newport 84%/67%/0.33 m; parramatta 70%/69%/0.37 m; paddington 85%/83%/0.29 m; kensington 68%/66%/0.2 m

```
Round 0. Question: how much does the score move when nothing changes? Three seeds: 0.719, 0.725, 0.721. Noise floor 0.006; a change must beat the control by 0.006 from now on.
```

## Round 2

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.738 | 0.703 | 26% | 0.756 | 0.908 | 0.755 | 0.641 | 0.629 |
| flip-average at prediction | 0.745 | 0.718 | 27% | 0.763 | 0.910 | 0.766 | 0.644 | 0.641 |
| scale and colour jitter | 0.731 | 0.665 | 26% | 0.752 | 0.907 | 0.736 | 0.644 | 0.616 |

Held-out (found/precise/median offset): monavale 87%/74%/0.27 m; newport 81%/70%/0.33 m; parramatta 69%/75%/0.37 m; paddington 86%/88%/0.29 m; kensington 73%/71%/0.17 m

```
Round 2. Question: does flip-average at prediction raise the scenario score?; does scale and colour jitter raise the scenario score?
Control: 0.738 (noise +-0.006). Changes: flip-average at prediction 0.745 (kept); scale and colour jitter 0.731 (dropped).
Learnt: most movement in scenario 'dense'; site share 27%, worst held-out F1 0.718.
Next: train 150 min more (under-trained or at capacity?).
```
