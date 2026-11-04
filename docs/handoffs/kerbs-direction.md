# Kerb tracing: direction after the 4 Nov review (Fable, review only, no GPU)

Read with docs/handoffs/kerbs-lidar-rounds.md (results) and kerbs-method.md (rules). This doc decides what the cheaper threads do next
and when they stop. Numbers: scenario F1 on the 8 NSW LiDAR boxes at 1 m tolerance, noise 0.006, retraining spread 0.007.
Scenario score = plain mean of 5 scenarios, and two of them are ONE box each: apartments = olympicpark (0.73), dense = parramatta (0.79).
Hilly 0.79, grid 0.915, terraces 0.85. Best pipeline pc-16-1 + street prior 0.817. Target 0.85 means roughly Olympic Park 0.80,
Parramatta 0.82 and hilly 0.83 at once. Report main-road found (%) next to the scenario score from now on.

## What the evidence says (from state.json, LOG.md, kerbs-lidar-rounds.md)
1. The misses are NOT mainly a visibility problem. On nbcheck the model finds 77% of CLEAR kerb, 78% under trees, 77% in shadow.
   On wocheck 77% clear, 77% trees, 71% shadow. Trees and shadow score the same as clear kerb, so occlusion is not what is missing.
2. The misses are a WHERE problem. nbcheck: main roads 53% found, collectors 68%, local 89%, lanes 97%. wocheck is the mirror image:
   main 88%, local 64%, lanes 17%. Olympic Park (arterials, medians by parkland and water, bridge decks) 60%. Each box has a
   kerb-location type the model refuses, and 78% of the long (> 40 m) misses have P < 0.1 within 1 m: the model is sure there is no kerb.
3. The model is largely a geometry prior, not a kerb detector. With the photo blanked on 80% of chips it still scores 0.808 (vs 0.815).
   Its inputs lot mask + distance to centreline + LiDAR let it learn "kerb = lot frontage offset a few metres", which fits local streets
   (89-99%) and fails wherever the kerb is not where that prior puts it: medians, far edges of wide arterials, kerbs along parks,
   water, rail and station land, narrow terrace streets with an unusual offset. Ten changes since round 16 (mining, averaging, gap net,
   hysteresis, wider view, long-miss mining, pdrop, stepfit) all touched how the model trains, not what the prior allows. All landed at
   0.80-0.815.
4. The LiDAR step is in the input where the model is blind (median step 7 cm, 43% >= 8 cm, only 18% without ground points) but at
   1-6 pts/m2 it cannot FIND kerbs alone (7-18% of candidates real). It is a check, not a finder.
5. Tracing (kerbtrace.py) raises found on every box (+4 pts Olympic Park) but half the traced length is not kerb: 0.818. The street
   prior (0.817) reaches only 0-11% of long misses because those streets have neither kerb drawn.

## Decision
- PAUSE the full iCurb-style learned tracer (DAgger, rotated crops, rollouts). Its inputs are the same P, LiDAR step, lots and
  centreline distance, so it inherits the blindness in point 2 and 3: where P < 0.1 and the step is a 7-18% finder, a learned stop
  head has little more to go on than the hand rule, and the continuation prior it would learn is what kerbstreet already does.
  Its realistic gain is +0.005 to +0.01 for several days of GPU and agent time on a tight 8 GB card, with many silent ways to fail.
  It stays as the LAST step (step 4), only if steps 1-3 leave the score below 0.84 AND the new P maps show evidence (P 0.2-0.5) along
  the long misses for a tracer to follow.
- Attack the prior first (steps 1-2), then convert the rule tracer's found into F1 with a cheap learned keep/drop filter (step 3).
- Parramatta: score it on the cleaned reference (kerbclean.py) from now on; council lines under buildings and on rail land are not
  kerbs. Say so in every report ("Parramatta cleaned"). Normal reference kept for the other boxes.

## Steps (in order; each one run by an Opus thread; one thread per step; hand over through kerbs-lidar-rounds.md)

### Step 1: where exactly is the model blind (CPU only, no training, ~1 session)
Write openfetch/tools/derive/kerbwhere.py next to kerbmiss.py (reuse its loaders). For every council kerb sample (0.5 m) on the 8
NSW boxes, record: found (drawn line within 1 m), P at the sample (pc-16-1, C:\kerb\long), road type, distance to the nearest lot in
bands 0-3 / 3-6 / 6-10 / 10-15 / > 15 m, distance to the nearest centreline in 2 m bands, and "lot side" (the nearest lot is on this
side of the centreline) or "far side / median". Print found % and median P per band per box, and the same for the training boxes'
own output (C:\kerb\out\<round>). Also print: of the kerb the model misses, what share lies in band types where the TRAINING labels
have < 5% of their length (the prior has never seen such a kerb).
Keep/stop: the step is DONE when the table exists. Read: if found collapses in specific bands (far side, > 10 m from lots, medians,
narrow offsets) while visibility types stay flat, the prior is the problem and step 2 runs both variants. If the misses are spread
like the found kerb across all bands (no band under 65% while the box average is 75%+), skip step 2 and go to step 3.

### Step 2: let the model see instead of assume (GPU, 2-3 variants of ~1 h each; PC now, Kaggle after Sat 7 Nov)
All fine-tune C:/kerb/saved/best-pc-16-1.pt with the usual cfg (kerb-learn/pc/side-street-eval.json), minutes 150, street 1.
  a. context dropout: new CFG "cdrop": 0.5 in kerblearn.py, blank the lot and centreline/water layers (zeros) on 50% of training
     chips, keep photo + LiDAR + label. At drawing time keep the layers. The model must learn to find the kerb from the picture
     and the step when the map is gone.
  b. no map at all: cfg "context": 0 (lots stay? no: also drop the lot layer; add CFG "nolot": 1 so inputs = photo + LiDAR only).
  c. only if step 1 shows the far side / median bands empty in the training labels: add 4 training boxes (role train_new, more 1)
     centred on arterials with medians INSIDE the training councils (Northern Beaches: Pittwater Rd at Dee Why or Brookvale,
     Warringah Rd; Canterbury-Bankstown: Canterbury Rd Belmore or Punchbowl, Hume Hwy; Woollahra: New South Head Rd Rose Bay).
     Fetch with kerblearn.py data; order their LiDAR only if the step 1 table says the LiDAR is what finds them.
Score every variant on: scenario score, main-road found, Olympic Park found, worst held-out, Kensington + Melb CBD (photo only:
must not fall more than 0.01). Keep rule: scenario >= 0.823 (bar 0.006 over 0.817) OR main-road found +10 pts with scenario within
0.003. Stop rule: if a and b both score <= 0.817 and main-road found moves < 3 pts, the prior hypothesis is dead; write that in the
handover, do not run more training variants of this kind, go to step 3.
If a variant wins, promote it, then rerun kerbmiss.py and kerbwhere.py on its output so step 3 and 4 start from the new misses.

### Step 3: trace filter instead of a learned tracer (CPU, sklearn, no GPU, ~1 session)
Run kerbtrace.py at e0.3 (most found, half false) on the TRAINING boxes with the current best lines and P. For each trace compute:
length, share of its length within 1 m of council kerb (label: good if >= 70%), mean and min P, mean LiDAR step, straightness,
heading difference to the nearest centreline, distance to nearest lot, distance to nearest centreline, whether it reached another
line, whether the street's other kerb is drawn, and the kerbstreet offset agreement. Fit a gradient-boosted tree classifier
(sklearn HistGradientBoostingClassifier, minutes on CPU) with box-grouped cross-validation. Apply to the check/held-out traces,
keep traces with p(good) >= cut, choose the cut on the check boxes only. Wire as CFG "trace": 1 after street in kerblearn
(same kerb layer, properties.trace = 1), kerbtrace.py gets a `filter` mode and the model file lives with best.pt.
Keep rule: NSW scenario >= 0.823 with kept-trace precision >= 70%. Stop rule: if kept-trace precision stays < 60% at any cut that
still adds >= 2 km, the traces carry no separable signal: drop step 3 and record it. Budget: one session plus one for wiring.

### Step 4: learned tracer, only if needed (GPU)
Run only if after steps 1-3 the scenario is < 0.84 AND kerbwhere/kerblong show P 0.2-0.5 along at least 30% of the remaining long
misses (there is evidence to follow). Scope it down: single pass, no DAgger at first; teacher = council kerb paths on the training
boxes, seeds = line ends as in kerbtrace.py, crop = rotated 64 x 64 at 0.1 m of photo, P, step, lots, centreline distance; heads =
next angle (classes, 5 deg) + stop. Prove it on 2 boxes (olympicpark, nbcheck) against kerbtrace e0.5 + step-3 filter before any
full run. Hard budget: 3 GPU rounds. Stop rule: no +0.005 over the step-3 result after 3 rounds, or kept-trace precision < 70%.
Thread "Build learned kerb tracer": hold at the current commit; do not start training until step 2 has a result.

### Always
- Every report lists: scenario score, main-road found, Olympic Park found, Parramatta (cleaned) found, worst held-out, Kensington.
- Never promote on < 0.006 without "better on 6 of 8 boxes". Check data/best/model.pt after every `pc.py record` (it promotes
  the control).
- Melbourne stays photo only; a change that drops Kensington or Melb CBD by > 0.01 is not kept.
- Stop the whole programme and tell Jacky if steps 1-3 end below 0.83: then the remaining gap is reference quality (Parramatta,
  Woollahra lanes) and Olympic Park's bridges/parkland, not the model, and the honest move is to ship kerbs by area with a
  per-council confidence, busiest first, and keep training in the background.
