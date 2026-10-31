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

## Round 3

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.745 | 0.705 | 26% | 0.765 | 0.910 | 0.759 | 0.652 | 0.637 |
| train 150 min more | 0.747 | 0.715 | 29% | 0.770 | 0.913 | 0.764 | 0.640 | 0.647 |

Held-out (found/precise/median offset): monavale 88%/74%/0.27 m; newport 83%/70%/0.33 m; parramatta 70%/73%/0.37 m; paddington 86%/86%/0.28 m; kensington 74%/67%/0.17 m

```
Round 3. Question: does train 150 min more raise the scenario score?
Control: 0.745 (noise +-0.006). Changes: train 150 min more 0.747 (within noise).
Learnt: most movement in scenario 'none'; site share 26%, worst held-out F1 0.705.
Next: second scale input (method item 6: a 3x wider, 0.3 m view of the street around each chip for shadow and medians (dense scenario is weakest)).
```

## Round 4

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.746 | 0.707 | 27% | 0.770 | 0.910 | 0.762 | 0.646 | 0.644 |
| trace at 0.1 m | 0.746 | 0.699 | 28% | 0.765 | 0.910 | 0.759 | 0.655 | 0.643 |

Held-out (found/precise/median offset): monavale 88%/75%/0.27 m; newport 82%/70%/0.34 m; parramatta 68%/76%/0.38 m; paddington 86%/88%/0.28 m; kensington 73%/69%/0.16 m

```
Round 4. Question: does trace at 0.1 m raise the scenario score?
Control: 0.746 (noise +-0.006). Changes: trace at 0.1 m 0.746 (within noise).
Learnt: most movement in scenario 'none'; site share 27%, worst held-out F1 0.707.
Next: second scale input (method item 6: a 3x wider, 0.3 m view of the street around each chip for shadow and medians (dense scenario is weakest)).
```

## Round 5

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.744 | 0.696 | 28% | 0.766 | 0.910 | 0.756 | 0.652 | 0.637 |
| resnet50 encoder | 0.743 | 0.714 | 26% | 0.770 | 0.909 | 0.767 | 0.623 | 0.647 |
| second scale input | 0.746 | 0.699 | 26% | 0.771 | 0.911 | 0.756 | 0.646 | 0.645 |

Held-out (found/precise/median offset): monavale 89%/74%/0.27 m; newport 84%/69%/0.34 m; parramatta 70%/72%/0.38 m; paddington 86%/86%/0.29 m; kensington 79%/62%/0.15 m

```
Round 5. Question: does resnet50 encoder raise the scenario score?; does second scale input raise the scenario score?
Control: 0.744 (noise +-0.006). Changes: resnet50 encoder 0.743 (within noise); second scale input 0.746 (within noise).
Learnt: most movement in scenario 'none'; site share 28%, worst held-out F1 0.696.
Next: queue empty, add the next change to kerb-learn/queue.json.
```

## Round 6

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| clDice line-continuity loss | 0.747 | 0.688 | 26% | 0.775 | 0.911 | 0.754 | 0.648 | 0.645 |
| control | 0.748 | 0.704 | 26% | 0.773 | 0.912 | 0.759 | 0.645 | 0.649 |
| learn from misses (all misses, no cause) | 0.745 | 0.712 | 26% | 0.782 | 0.914 | 0.765 | 0.624 | 0.641 |

Held-out (found/precise/median offset): monavale 88%/76%/0.27 m; newport 82%/70%/0.34 m; parramatta 68%/75%/0.38 m; paddington 86%/88%/0.28 m; kensington 76%/66%/0.15 m

```
Round 6. Question: does clDice line-continuity loss raise the scenario score?; does learn from misses (all misses, no cause) raise the scenario score?
Control: 0.748 (noise +-0.006). Changes: clDice line-continuity loss 0.747 (within noise); learn from misses (all misses, no cause) 0.745 (within noise).
Learnt: most movement in scenario 'none'; site share 26%, worst held-out F1 0.704.
Next: queue empty, add the next change to kerb-learn/queue.json.
```

## Round 7

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| Satlas Swin-v2-B aerial encoder | 0.757 | 0.715 | 28% | 0.769 | 0.913 | 0.787 | 0.654 | 0.662 |
| control | 0.746 | 0.696 | 28% | 0.770 | 0.911 | 0.757 | 0.643 | 0.647 |
| drop council lines with no photo edge | 0.747 | 0.714 | 28% | 0.774 | 0.911 | 0.762 | 0.645 | 0.641 |

Held-out (found/precise/median offset): monavale 88%/74%/0.28 m; newport 83%/71%/0.34 m; parramatta 68%/75%/0.33 m; paddington 86%/88%/0.27 m; kensington 80%/69%/0.12 m

```
Round 7. Question: does Satlas Swin-v2-B aerial encoder raise the scenario score?; does drop council lines with no photo edge raise the scenario score?
Control: 0.746 (noise +-0.006). Changes: Satlas Swin-v2-B aerial encoder 0.757 (kept); drop council lines with no photo edge 0.747 (within noise).
Learnt: most movement in scenario 'terraces'; site share 28%, worst held-out F1 0.715.
Next: more apartment and dense training areas (plateau since round 1 on model changes; apartments 0.65 and dense 0.65 are the weakest scenarios and had 2 and 4 training boxes. Adds 4 boxes busiest first from TOP.md: Wentworth Point (NSW 28), Melrose Park (Ermington, NSW 35), South Wharf (Vic 22), West Melbourne (Vic 94); none overlaps a check or held-out box).
```
