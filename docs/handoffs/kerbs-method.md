# Kerb training method v2 (30 Oct 2026)

For the thread that owns the kerb photo model loop (openfetch-derive, branch claude/project-thread-gdrxtc, kerblearn.py +
kerbloop.py + kerb-learn workflows). Written on Fable so a cheaper model can run the rounds by following this file and reading
almost nothing else. Jacky's rules (30 Oct): cross-checkable areas, several scenarios and scales, a method instead of blind
retraining, a takeaway from every round that shapes the next, few tokens, fast.

## 1 What the log says after four rounds (kerb-learn/LOG.md, state.json)

| box | kind | found | precise | median offset | found within 0.5 m | whole lines |
|---|---|---|---|---|---|---|
| cbcheck (Canterbury-Bankstown) | check | 95% | 86% | 0.21 m | 85% | 91% |
| nbcheck (Northern Beaches) | check | 78% | 66% | 0.36 m | 54% | 77% |
| wocheck (Woollahra) | check | 66% | 74% | 0.29 m | 50% | 51% |
| Mona Vale | held out | 87% | 72% | 0.31 m | 64% | 80% |
| Newport | held out | 72% | 60% | 0.47 m | 40% | 59% |
| Parramatta CBD | held out, council never trained on | 63% | 65% | 0.42 m | 37% | 39% |

Facts that decide the method:
1. **Only structural changes ever helped**: pretrained encoder (round 1), bigger view (+0.005), road and water context (+0.024).
   All nine "learn from misses (cause)" variants in rounds 3 and 4 scored at or below the model they started from. The loop's main
   search space (hard-example mining by photo-guessed cause) is empty, yet it fills 4 of 5 runners every round.
2. **The keep bar (0.005 F1) is below the noise**: nobody has run the same settings twice, so a "gain" of 0.009 (round 3) may be
   seed noise. Every verdict so far rests on one sample.
3. **The offset, not the finding, is the harder bar.** Lines are found within 2 m at 93-97% in Newport and Mona Vale, but the
   median offset is 0.31-0.47 m against a 0.3 m target. A near-constant offset per box points at the labels, not the model:
   council lines sit at the gutter lip or kerb foot (gutter 0.3-0.45 m wide), the photo edge the model learns is the kerb top.
   The two Canterbury-Bankstown and Woollahra sets were edge-fitted (align()); Northern Beaches and Parramatta were not, and
   Parramatta's GDA94 shift is assumed, not measured.
4. **The scene mix is wrong for the goal.** Every training box is suburban. Parramatta CBD (statewide rank 6) is half in shadow
   (25 of 50 km) with medians, multi-lane roads and kerb ramps, and no training box looks like it. The busiest areas statewide
   (Sydney, Waterloo, Zetland, Chatswood) are dense too, and have no council kerb data at all, so Parramatta CBD is the only
   proxy we have for the places that matter most.
5. **The check score is one council's score.** Check F1 averages three boxes; cbcheck (flat grid, 20 km of kerb) dominates at 0.90
   while wocheck sits at 0.70. A model can win the round by fitting Canterbury-Bankstown better.
6. **Machine time**: a round is 5 jobs x ~3 h on 4-core runners, about 15 runner-hours, for one useful answer. Two restarts (rounds
   2 and 4) threw away whole rounds because a code push cancels and restarts the run.
7. **Scale**: everything is scored per 1 km box. A Rhino user exports a 200-500 m site; one bad site in a good square kilometre is
   what they see.

## 2 Rules of the method

**R1 One question per round, with a control.** A round is: control (best model, same settings, trained on) + at most two
hypotheses, each a single change. A hypothesis is kept only if it beats the control by more than the noise floor (R2) on the
scenario score (R5). Never more than three training jobs per round.

**R2 Measure the noise first.** Round 0 runs the current best settings three times with different seeds and no change. The
spread of the scenario score (and of each box) is the noise floor; the keep bar becomes 2x that spread, written into state.json
as `min_gain`. Until this is done no round verdict counts.

**R3 Cross-checkable boxes, busiest first, every scenario twice.** Boxes come from tools/priority/TOP.md inside the four
councils with kerb data. Each scenario has at least two training boxes in different councils, one check box, and the held-out
boxes cover at least three scenarios:

| scenario | what it tests | train (council, rank) | check / held out |
|---|---|---|---|
| dense centre: shadow, medians, multi-lane, ramps | the busiest places | Bankstown centre (C-B 50), North Parramatta (Parra 73) | held out: Parramatta CBD (6) |
| apartment precincts, new streets | wide clean kerbs, car parks | Wentworth Point (Parra 28), Rydalmere (Parra 59) | check: Sydney Olympic Park (213) |
| flat suburban grid | the common case | Greenacre (57), Yagoona (76), Roselands (94) | check: cbcheck as now |
| hilly, leafy, coastal | trees, roll-top kerbs, bends | Carlingford (29), Epping (33), Dee Why (182), Bellevue Hill (24) | held out: Mona Vale, Newport |
| dense terraces, narrow streets | parked cars both sides | Double Bay (106), Woollahra (215) | held out: Paddington (160) |
| industrial, wide roads | long straight kerbs, trucks | Milperra (150), Villawood (217) | check: wocheck stays as the Woollahra check |

Parramatta council stops being "never seen": its suburban boxes train the model, its CBD box stays held out, because the CBD
scene is the goal, not the council name. For a true unseen-council test, once per milestone (not every round) run the control with
Woollahra boxes dropped and score Paddington: the smallest council, so the cheapest to leave out. Existing boxes stay; the table
adds about 12 boxes (fetch once, bump the cache key, run the data job before any training job so five jobs do not fetch the
same photos).

**R4 Decide what a kerb line is, then align every reference to it.** Before round 1: at Mona Vale, compare the council lines
with the LiDAR kerb step from the LiDAR pilot (docs/research/kerbs-pilot) and with the photo edge; measure the constant
offset per council between the model's lines and the council lines (median east/north shift, not just distance). Pick one
definition (recommended: the kerb face, the step the LiDAR shows and the edge the photo shows) and shift each council's
reference onto it by its own measured gutter offset. Run align() for Northern Beaches and Parramatta too and record the edge
gain. Expected effect: median offset drops by 0.1-0.2 m in every box at no training cost. This is the cheapest gain on the table.

**R5 Score by scenario and by site, not by kilometre.** Report per box: found and precise within 1 m, found within 0.5 m, median
offset, whole lines. The round score is the mean of per-scenario F1 (each scenario once, whatever its kerb length), and the
verdict also needs the worst held-out box not to fall. Add a site view: cut each box into 16 tiles of 250 m and report the share
of tiles with found >= 85% and offset <= 0.3 m. That share is what a user experiences, and it is the number to tell Jacky.

**R6 Probe, then promote.** Train every variant for 40 minutes first (one job, all three variants in sequence, scored on the check
boxes). Only a variant within the noise floor of the control, or better, gets its full 150-minute job. If round 1 shows the
40-minute ranking matches the full ranking, keep probing; if not, drop R6 and run three full jobs. Either way a round uses two or
three runners, not five.

**R7 Queue changes, never restart.** The run reads kerb-learn/queue.json at each plan step: a list of named hypotheses with their
settings, in order. The thread edits only that file while a run is live; code edits wait for a round boundary and go in with
the next run. The workflow must stop triggering on pushes to kerbloop.py; start it by hand. A restart costs a whole round.

**R8 Every round writes a takeaway in this shape** (kerbloop.py record writes it, the thread does not type it):

```
Round N. Question: does <change> raise the scenario score?
Control: <score> (noise +-<floor>). Change: <score>. Verdict: kept / dropped / within noise.
Learnt: <one line, from the per-scenario table: which scenario moved, which did not>.
Next: <the queue head, with why it is next>.
```

**R9 The running thread reads one screen per round.** Add `kerbloop.py brief state.json` that prints at most 25 lines: best
model, the scenario table, the last verdict, the queue head, and the stop rule distance. The thread reads that, never result.json,
never the full log, and opens at most one joined picture sheet per round (tools/sheet.js). It messages Jacky only at a milestone:
target met, plateau, cap, or a decision needed. This is what lets Opus or Sonnet run the loop.

## 3 The hypothesis queue (ordered by expected gain per runner-hour)

1. **Reference alignment** (R4, data only, no training): offset. Kill if the median offset does not move on any box.
2. **Test-time flips and rotations** (average 4-8 predictions): precision and offset, cheap, inference only. Kill if F1 < control.
3. **Scale and colour jitter in training** (0.8-1.25 resampling, stronger brightness and hue shifts): held-out gap and shadow.
   Kill if Parramatta CBD and wocheck do not move.
4. **Continue training the control** (same settings, another 150 min): the old loop's best move was "train longer". Cheap, tells
   whether the model is under-trained or at capacity.
5. **Dense-scene boxes** (R3 table): Parramatta CBD. This is a data change, so it is a separate round with its own control.
6. **Second scale as input** (a 0.3 m downsampled copy of the photo as extra channels): shadow and medians need context beyond
   a 25 m chip. Kill if shadow found does not rise.
7. **Larger encoder (resnet50)** only after 4 shows the model is at capacity. Costs 2x per round.
8. **Self-training on the busiest unlabelled suburbs** (Sydney, Zetland, Chatswood: predict, keep confident lines, train on them):
   the only route to the places with no council data. Last, because it needs 1-7 settled first.

Dropped for good: learn-from-misses by photo-guessed cause (nine tries, no gain). Keep the cause breakdown as a report only.

## 4 Phases and stop rules

- **Phase 0 (one round of runner time, no new learning):** noise floor (R2), per-council offset vectors and the Mona Vale
  three-way check (R4), the brief command and queue file (R7, R9), new boxes fetched (R3). Deliver: min_gain in state.json,
  aligned references, a first scenario table for the current best model.
- **Phase 1 (rounds 1-3):** queue items 1-4. Expect: offset under 0.3 m on Mona Vale and wocheck, Newport near it.
- **Phase 2 (rounds 4-6):** items 5-6 with the dense boxes in. Expect: Parramatta CBD found >= 75%.
- **Phase 3:** item 7-8 only if the plateau rule fires in phase 2.
- **Stop:** target (found >= 85%, offset <= 0.3 m, precision >= 70% on every held-out box) met; or two rounds in a row within
  noise of the control (plateau: move to the next phase, or report if in phase 3); or round 10. At every stop, report to Jacky
  the scenario table and the site share (R5), not kilometres.
- **Cross-check before any rollout:** Mona Vale three-way agreement (council, LiDAR, photo), then one blind box in a council
  without kerb data (Sydney, rank 1) checked on one picture sheet by Jacky.

## 5 Compute: free and faster

GitHub public runners are 4 vCPU, 16 GB, free, 20 at once, 6 h per job; a 150-minute CPU round is a few thousand steps of a
ResNet-34 U-Net. Kaggle gives 30 GPU hours a week free (P100/T4, 12 h sessions), roughly 20-40x faster per step: one GitHub round
becomes about 10 minutes, and the whole queue above fits in one week's quota. It needs a Kaggle account (phone verification) that
Jacky would create ([[free-signups]]); the training script runs there unchanged (data from the same NSW services, code pulled
from the public repo). Recommended only if Jacky wants the loop to finish in days rather than weeks; the method above does not
depend on it.

## 6 What to change in the code (small, in this order; the loop thread owns it)

1. kerbloop.py: `brief` command (R9); control variant every round; keep bar from state.json `min_gain` (R2); scenario score and
   worst-held-out rule (R5); takeaway template (R8); read kerb-learn/queue.json (R7); drop the by-cause move generator.
2. kerblearn.py: box table from a JSON file with a scenario per box (R3); align() for every council plus a per-council gutter
   shift (R4); 250 m tile share in the result (R5); test-time augmentation flag; scale/colour jitter flag; optional 0.3 m channel.
3. Workflows: remove the push trigger; data job runs before round 1 with a new cache key; a 40-minute probe job before the full
   jobs (R6); matrix of at most 3.
4. Switch at a round boundary: let the running round 5 finish, record it, then start the new run from its state.

Takeaway for Jacky in one line: the model is not the bottleneck yet; the labels, the scene mix and the way rounds are judged are,
and fixing those costs almost no training time.
