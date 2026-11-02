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

## Round 8

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.761 | 0.717 | 30% | 0.768 | 0.912 | 0.786 | 0.679 | 0.661 |
| more apartment and dense training areas | 0.763 | 0.712 | 31% | 0.759 | 0.910 | 0.787 | 0.710 | 0.648 |

Held-out (found/precise/median offset): monavale 88%/76%/0.28 m; newport 82%/70%/0.34 m; parramatta 67%/77%/0.33 m; paddington 85%/87%/0.27 m; kensington 80%/70%/0.12 m

```
Round 8. Question: does more apartment and dense training areas raise the scenario score?
Control: 0.761 (noise +-0.006). Changes: more apartment and dense training areas 0.763 (within noise).
Learnt: most movement in scenario 'none'; site share 30%, worst held-out F1 0.717.
Next: queue empty, add the next change to kerb-learn/queue.json.
```

## Round 9

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| Satlas: bigger view (384 px chips) | 0.757 | 0.706 | 30% | 0.765 | 0.911 | 0.786 | 0.675 | 0.649 |
| Satlas: train 300 min more | 0.759 | 0.713 | 32% | 0.778 | 0.915 | 0.793 | 0.644 | 0.666 |
| control | 0.759 | 0.713 | 29% | 0.774 | 0.913 | 0.787 | 0.666 | 0.657 |

Held-out (found/precise/median offset): monavale 88%/76%/0.28 m; newport 83%/70%/0.34 m; parramatta 67%/76%/0.32 m; paddington 84%/87%/0.27 m; kensington 79%/70%/0.12 m

```
Round 9. Question: does Satlas: bigger view (384 px chips) raise the scenario score?; does Satlas: train 300 min more raise the scenario score?
Control: 0.759 (noise +-0.006). Changes: Satlas: bigger view (384 px chips) 0.757 vs control 0.759 (within noise); Satlas: train 300 min more 0.759 vs control 0.759 (within noise).
Learnt: most movement in scenario 'none'; site share 29%, worst held-out F1 0.713.
Next: LiDAR + aerial (Jacky 1 Nov: 'lidar is a must'. Adds 3 LiDAR layers (ground minus 3 m median, slope, has-LiDAR) beside the photo; judged on the boxes with LiDAR against the aerial-only control).
```

## Round 10

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial | 0.760 | 0.722 | 28% | 0.775 | 0.911 | 0.789 | 0.658 | 0.666 |
| LiDAR only | 0.780 | 0.785 | 29% | 0.763 | 0.900 | 0.836 | 0.616 | 0.785 |
| control | 0.756 | 0.709 | 29% | 0.771 | 0.913 | 0.782 | 0.658 | 0.657 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial | 0.776 | 0.719 | 0% | 0.771 | 0.911 | 0.813 | 0.668 | 0.719 |
| LiDAR only | 0.780 | 0.785 | 0% | 0.763 | 0.900 | 0.836 | 0.616 | 0.785 |
| control | 0.772 | 0.709 | 0% | 0.767 | 0.912 | 0.805 | 0.665 | 0.709 |

Held-out (found/precise/median offset): monavale 88%/76%/0.28 m; newport 83%/70%/0.34 m; parramatta 67%/76%/0.32 m; paddington 85%/86%/0.27 m; kensington 79%/69%/0.12 m

```
Round 10. Question: does LiDAR + aerial raise the scenario score?; does LiDAR only raise the scenario score?
Control: 0.756 (noise +-0.006). Changes: LiDAR + aerial 0.776 vs control 0.772 on LiDAR boxes (within noise); LiDAR only 0.780 vs control 0.772 on LiDAR boxes (better, not usable alone).
Learnt: most movement in scenario 'none'; site share 29%, worst held-out F1 0.709.
Next: two-judge label cleaning (LiDAR step + photo edge) (Jacky 31 Oct 15:52Z: label quality is the main limit. Training labels drop a council 10 m piece unless both judges agree: photo edge (as labelcheck) and a LiDAR ground step of at least 7.5 cm across the line (ELVIS NSW orders, 10 training boxes; boxes without LiDAR use the photo judge only). Scoring reference unchanged: no LiDAR on the check and held-out boxes, so the filtered-set score is not possible).
```

## PC side run 1 Nov (Jacky's RTX 3070): LiDAR only, 300 min (6,300 steps)
On the 8 LiDAR boxes: scenario score 0.782 (round 10 LiDAR only at 150 min: 0.780) -> within noise, training longer does not help.
hilly 0.762, grid 0.899, terraces 0.839, apartments 0.630, dense 0.779; worst held-out 0.779; thresh 0.6.
olympicpark misses kerbs (recall 0.50, precision 0.86); nbcheck draws extras (precision 0.63, offset 0.41 m).
Next on the PC: LiDAR only + two-judge label cleaning (kerb-learn/pc/side-lidar-2judge.json).

## PC side run 1 Nov: LiDAR only + two-judge label cleaning (photo edge + LiDAR step), 150 min
Scenario score 0.758 vs LiDAR only 0.780: worse, F1 lower on all 8 LiDAR boxes (by 0.006-0.053), offsets worse on all 8, threshold fell 0.6 -> 0.4.
Cleaning dropped ~half the pieces but only ~8% of length (3-15% per box): it mostly removed short pieces the model needed. Dropped.
hilly 0.734, grid 0.870, terraces 0.819, apartments 0.621, dense 0.748.
Next on the PC: LiDAR only + the two train_new apartment boxes with LiDAR (Melrose Park, Wentworth Point; kerb-learn/pc/side-lidar-more.json).

## Round 11

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial, photo blanked on half the chips | 0.774 | 0.730 | 34% | 0.783 | 0.913 | 0.809 | 0.678 | 0.685 |
| LiDAR + aerial, photo blanked on half the chips, 300 min | 0.772 | 0.738 | 32% | 0.793 | 0.914 | 0.812 | 0.657 | 0.684 |
| control | 0.754 | 0.713 | 28% | 0.775 | 0.913 | 0.781 | 0.642 | 0.657 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial, photo blanked on half the chips | 0.798 | 0.768 | 0% | 0.783 | 0.913 | 0.848 | 0.678 | 0.768 |
| LiDAR + aerial, photo blanked on half the chips, 300 min | 0.795 | 0.761 | 0% | 0.793 | 0.914 | 0.849 | 0.657 | 0.761 |
| control | 0.771 | 0.713 | 0% | 0.772 | 0.912 | 0.805 | 0.651 | 0.713 |

Held-out (found/precise/median offset): monavale 90%/76%/0.27 m; newport 86%/73%/0.31 m; parramatta 73%/81%/0.3 m; paddington 86%/89%/0.28 m; kensington 82%/66%/0.12 m

```
Round 11. Question: does LiDAR + aerial, photo blanked on half the chips raise the scenario score?; does LiDAR + aerial, photo blanked on half the chips, 300 min raise the scenario score?
Control: 0.754 (noise +-0.006). Changes: LiDAR + aerial, photo blanked on half the chips 0.798 vs control 0.771 on LiDAR boxes (kept); LiDAR + aerial, photo blanked on half the chips, 300 min 0.795 vs control 0.771 on LiDAR boxes (kept).
Learnt: most movement in scenario 'apartments'; site share 34%, worst held-out F1 0.730.
Next: two-judge label cleaning (LiDAR step + photo edge) (Jacky 31 Oct 15:52Z: label quality is the main limit. Training labels drop a council 10 m piece unless both judges agree: photo edge (as labelcheck) and a LiDAR ground step of at least 7.5 cm across the line (ELVIS NSW orders, 10 training boxes; boxes without LiDAR use the photo judge only). Scoring reference unchanged: no LiDAR on the check and held-out boxes, so the filtered-set score is not possible).
```

## Round 12

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial + Melrose Park and Wentworth Point apartment boxes | 0.776 | 0.720 | 38% | 0.773 | 0.913 | 0.802 | 0.710 | 0.682 |
| LiDAR + aerial, photo blanked on 3/4 of the chips | 0.772 | 0.729 | 32% | 0.788 | 0.914 | 0.807 | 0.664 | 0.686 |
| control | 0.774 | 0.735 | 35% | 0.785 | 0.914 | 0.811 | 0.669 | 0.689 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| LiDAR + aerial + Melrose Park and Wentworth Point apartment boxes | 0.801 | 0.766 | 0% | 0.769 | 0.913 | 0.839 | 0.716 | 0.766 |
| LiDAR + aerial, photo blanked on 3/4 of the chips | 0.796 | 0.766 | 0% | 0.788 | 0.914 | 0.847 | 0.664 | 0.766 |
| control | 0.797 | 0.768 | 0% | 0.782 | 0.914 | 0.847 | 0.675 | 0.768 |

Held-out (found/precise/median offset): monavale 90%/77%/0.27 m; newport 86%/72%/0.32 m; parramatta 72%/82%/0.29 m; paddington 87%/90%/0.28 m; kensington 82%/66%/0.12 m

```
Round 12. Question: does LiDAR + aerial + Melrose Park and Wentworth Point apartment boxes raise the scenario score?; does LiDAR + aerial, photo blanked on 3/4 of the chips raise the scenario score?
Control: 0.774 (noise +-0.006). Changes: LiDAR + aerial + Melrose Park and Wentworth Point apartment boxes 0.801 vs control 0.797 on LiDAR boxes (within noise); LiDAR + aerial, photo blanked on 3/4 of the chips 0.796 vs control 0.797 on LiDAR boxes (within noise).
Learnt: most movement in scenario 'none'; site share 35%, worst held-out F1 0.735.
Next: queue empty, add the next change to kerb-learn/queue.json.
```

## Round 13

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| apartment boxes + kerb pixels weighted 6 | 0.778 | 0.719 | 36% | 0.772 | 0.913 | 0.803 | 0.723 | 0.677 |
| control | 0.776 | 0.739 | 36% | 0.790 | 0.915 | 0.814 | 0.672 | 0.689 |
| kerb pixels weighted 6 | 0.774 | 0.746 | 32% | 0.789 | 0.915 | 0.813 | 0.665 | 0.689 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| apartment boxes + kerb pixels weighted 6 | 0.804 | 0.766 | 0% | 0.772 | 0.913 | 0.845 | 0.723 | 0.766 |
| control | 0.802 | 0.774 | 0% | 0.786 | 0.915 | 0.849 | 0.685 | 0.774 |
| kerb pixels weighted 6 | 0.798 | 0.766 | 0% | 0.779 | 0.914 | 0.847 | 0.686 | 0.766 |

Held-out (found/precise/median offset): monavale 90%/78%/0.27 m; newport 86%/73%/0.32 m; parramatta 73%/83%/0.28 m; paddington 86%/90%/0.28 m; kensington 82%/67%/0.11 m

```
Round 13. Question: does apartment boxes + kerb pixels weighted 6 raise the scenario score?; does kerb pixels weighted 6 raise the scenario score?
Control: 0.776 (noise +-0.006). Changes: apartment boxes + kerb pixels weighted 6 0.804 vs control 0.802 on LiDAR boxes (within noise); kerb pixels weighted 6 0.798 vs control 0.802 on LiDAR boxes (within noise).
Learnt: most movement in scenario 'none'; site share 36%, worst held-out F1 0.739.
Next: hide car- and tree-sized patches (3 per chip), keep the kerb label (Jacky 1 Nov: guess hidden kerbs from the line around them, like a person does; masked-input training (photo + LiDAR blanked, label whole)).
```

## Round 14

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.772 | 0.743 | 33% | 0.794 | 0.915 | 0.811 | 0.652 | 0.687 |
| hide car- and tree-sized patches (3 per chip), keep the kerb label | 0.774 | 0.736 | 34% | 0.794 | 0.914 | 0.813 | 0.663 | 0.684 |
| hide car- and tree-sized patches (6 per chip), keep the kerb label | 0.773 | 0.714 | 34% | 0.784 | 0.912 | 0.806 | 0.672 | 0.690 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| control | 0.797 | 0.770 | 0% | 0.787 | 0.914 | 0.849 | 0.663 | 0.770 |
| hide car- and tree-sized patches (3 per chip), keep the kerb label | 0.801 | 0.776 | 0% | 0.790 | 0.913 | 0.853 | 0.672 | 0.776 |
| hide car- and tree-sized patches (6 per chip), keep the kerb label | 0.800 | 0.777 | 0% | 0.780 | 0.914 | 0.851 | 0.676 | 0.777 |

Held-out (found/precise/median offset): monavale 89%/80%/0.28 m; newport 85%/74%/0.31 m; parramatta 71%/84%/0.28 m; paddington 85%/92%/0.28 m; kensington 81%/69%/0.1 m

```
Round 14. Question: does hide car- and tree-sized patches (3 per chip), keep the kerb label raise the scenario score?; does hide car- and tree-sized patches (6 per chip), keep the kerb label raise the scenario score?
Control: 0.772 (noise +-0.006). Changes: hide car- and tree-sized patches (3 per chip), keep the kerb label 0.801 vs control 0.797 on LiDAR boxes (within noise); hide car- and tree-sized patches (6 per chip), keep the kerb label 0.800 vs control 0.797 on LiDAR boxes (within noise).
Learnt: most movement in scenario 'none'; site share 33%, worst held-out F1 0.743.
Next: queue empty, add the next change to kerb-learn/queue.json.
```

## Round 15

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| apartment boxes + hide 3 patches per chip, 300 min | 0.781 | 0.725 | 38% | 0.782 | 0.913 | 0.809 | 0.707 | 0.694 |
| control | 0.779 | 0.722 | 36% | 0.775 | 0.913 | 0.802 | 0.723 | 0.684 |

On the boxes with LiDAR only (nbcheck, cbcheck, wocheck, olympicpark, monavale, newport, parramatta, paddington; 250 m sites not counted):

| model | scenario score | worst held-out F1 | 250 m sites ok | hilly | grid | terraces | apartments | dense |
|---|---|---|---|---|---|---|---|---|
| apartment boxes + hide 3 patches per chip, 300 min | 0.806 | 0.767 | 0% | 0.778 | 0.913 | 0.851 | 0.720 | 0.767 |
| control | 0.804 | 0.768 | 0% | 0.768 | 0.913 | 0.838 | 0.732 | 0.768 |

Held-out (found/precise/median offset): monavale 90%/74%/0.27 m; newport 86%/72%/0.32 m; parramatta 73%/82%/0.29 m; paddington 88%/88%/0.28 m; kensington 84%/64%/0.11 m

```
Round 15. Question: does apartment boxes + hide 3 patches per chip, 300 min raise the scenario score?
Control: 0.779 (noise +-0.006). Changes: apartment boxes + hide 3 patches per chip, 300 min 0.806 vs control 0.804 on LiDAR boxes (within noise).
Learnt: most movement in scenario 'none'; site share 36%, worst held-out F1 0.722.
Next: fill hidden kerb gaps along the road (Jacky 1 Nov: guess hidden kerbs like a person. kerbfill.py: along each block frontage the kerb sits at the verge width measured on the visible kerb (carried across the gap from the kerb before to the kerb after); gaps 2-40 m with kerb seen on both sides are drawn in the same kerb layer. Synthetic test (council kerbs with 4-30 m pieces cut out, 8 NSW check/held-out boxes): found 0.871 -> 0.939, precise 1.000 -> 0.981. Post-processing only; scored with minutes 0 on the best model (pc/side-fill-eval.json)).
```
