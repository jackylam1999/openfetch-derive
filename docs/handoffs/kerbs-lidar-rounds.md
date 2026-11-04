# Handover: kerb training with LiDAR (2 Nov 2026 ~17:10Z)
From thread "Fill hidden kerbs and continue training". Read AGENTS.md (project files), docs/handoffs/kerbs-method.md (project files), then
`python3 openfetch/tools/derive/kerbloop.py brief kerb-learn/state.json`. PC setup details: project memory kerb-pc-training.

## Goal and standing rules (Jacky)
- Kerb lines good enough to ship (found >= 85%, offset <= 0.3 m, precise >= 70% on every held-out box), busiest areas first
  (tools/priority/TOP.md).
- LiDAR first; aerial kept while it helps (round 11). Train on BOTH Kaggle and the PC when both are free.
- AUTONOMY (1 Nov 13:14Z): never wait for his decision during training; pick the most sensible next step, run it, tell him after.
  Never leave the PC idle.
- Hidden kerbs: estimate kerbs hidden by cars/trees "like a human would"; filled kerbs go in the SAME kerb layer.
- AFTER THE MODEL HITS THE TARGET (Jacky 2 Nov 13:16Z): run kerbs on the top 20 suburbs per state first (tools/priority/TOP.md).
  Jacky has NO official NSW building footprints: where buildings are needed (e.g. to clean the reference), use our LiDAR roofs
  (Buildings (OpenFetch), openfetch-derive roofs.py) for the top twenty.

## State
- Code + state: openfetch-derive branch claude/project-thread-tkuw2p (PR #7). kerblearn.py, kerbloop.py, kerbfill.py, kerbmiss.py,
  kerb-learn/state.json, LOG.md, queue.json.
- Best = pc-16-1 "learn from misses (mine 0.3)", LiDAR boxes 0.815, promoted by hand (0.005 over control, bar 0.006; worst held-out
  0.778 -> 0.786, better on 7 of 8 boxes). Previous best saved on the PC as C:\kerb\saved\best-pc-16-0.pt.
- PC: Jacky's laptop, RTX 3070, everything in C:\kerb. Driver kerb-learn/pc/pc.py: `data`, `round [side.json]`, `record <tag>`.
  Folder tag = state.json "round" BEFORE record (round N lives in C:\kerb\out\<N-1>). A plain variant ~63 min; a mining (mine>0)
  variant ~3.5 h (it redraws all 34 training boxes first). Start rounds DETACHED plus a C:\kerb\nextNN.ps1 that waits, pulls
  --ff-only, records, commits ONLY state.json + LOG.md (one-off author jackylam1999 noreply; PC git has no user set), pushes.
  RC watchers die on restarts: always schedule a send_later fallback. Keep laptop plugged in, lid open.
- Kaggle GPU quota resets Sat 7 Nov 00:00 UTC (then run a second variant there per round).

## Results this thread (F1 on the 8 NSW LiDAR check/held-out boxes; noise ±0.006)
- Round 15: apartments + hide 3 patches, 300 min 0.806 vs control 0.804 (within noise).
- Hidden-kerb fill (kerbfill.py, CFG gapfill, side run minutes 0): cut-out test found 0.871 -> 0.939, but on real output
  0.804 -> 0.804. It only fills gaps <= 40 m with kerb seen on both sides along a lot frontage; real misses are mostly longer.
  Kept in code, off by default. A looser version (one seen end, longer gaps) is untested; precision is the risk.
- Miss map (kerbmiss.py, round 15 best, thr 0.7): 23.5 of 139.9 km missed; 52% in stretches > 40 m, 32% 10-40 m, 16% < 10 m;
  local streets 54%, collector 28%, lanes 10%, main 8%. ("frontage 97%" counts park/station lots too.) The new
  "other kerb of the street drawn" column (0a19b66) has not been run on real output yet.
- Picture check of the > 40 m misses (12 per box): Olympic Park ~90% real kerbs skipped (arterial edges, medians by parkland/water,
  two bridge decks without ground LiDAR); Parramatta CBD ~70% NOT street kerbs (council lines under a building, station forecourt,
  rail corridor/deck, plaza, construction site) -> its 74% found is understated (rough estimate ~83% after cleaning).
- Round 16: control 0.810 (new best then); main/collector road sampling (CFG mainroad 0.3) 0.806, main-road found unchanged 53%.
- Round 17: learn from misses (mine 0.3) 0.815 vs control 0.810 -> promoted by hand. Gain is mostly precision; Olympic Park found
  fell 63.6% -> 60.1%. Held-out found/precise/offset: monavale 90.5/79.3/0.27, newport 86.7/74.5/0.31, parramatta 74.1/83.7/0.29,
  paddington 86.2/91.4/0.29; kensington (Vic, no LiDAR) 83.0/67.9.

## 3 Nov results (thread "Starts now")
- Round 18 (finished 21:26Z 2 Nov): mine 0.3 retrained 0.808, mine 0.5 0.798, best stays pc-16-1 0.815. `pc.py record` always promotes the control and
  overwrites data/best/model.pt: it did so again, put back by hand (saved/best-pc-16-1.pt, commit 5f80098). Check after every record.
- pc-16-1 rescored unchanged gives 0.815 box for box, so scoring repeats exactly; retraining spread is about 0.007. Fair read of the model: 0.81.
- Clean Parramatta (kerbclean.py, LiDAR roofs from tile 3146256 via roofs.py, in C:\kerb\clean; drawn lines near dropped pieces count neither way):
  found 74.1 -> 77.0%, precise 83.7 -> 83.6%, F1 0.786 -> 0.802. Dropped 1.5 of 25 km (building 0.9, off road 0.55, rail 0.07). The old 83% guess was wrong:
  over the photo most remaining misses are real (laneways, deep shadow, bridges, station bus interchange). Normal reference unchanged.
- Model averaging (CFG avg, kerb-learn/pc/side-avg.json): 16-1+16-0 0.815, 16-1+17-0 0.813, all three 0.814. No gain; dropped.
- Miss map on real output (0.7): 24.3 of 139.9 km missed; 53% in stretches > 40 m, 32% 10-40 m, 14% < 10 m; other kerb of the street drawn for only 26%.
- Local commits a4fc601 and later are NOT pushed: pushes of code wait for Jacky's go-ahead.

- Gap-repair net (kerbgap.py, 45 min, tested on the 3-model average lines): 0.815 at cut 0.7-0.9 vs base 0.814. No gain; dropped. The pieces it adds
  are mostly extra lines.
- Long-miss check (kerblong.py, pc-16-1 probabilities in C:\kerb\long): of 12.5 km missed in stretches > 40 m, 9.75 km (78%) has P < 0.1 within 1 m:
  the model does not see them at all. Short misses are the opposite: 2.8 of 3.5 km under 10 m and 4.4 of 7.5 km at 10-40 m have P >= 0.5 nearby
  but no line within 1 m (tracing or offset, not seeing). Growing lines into weak pixels (hysteresis, low 0.2-0.5): 0.805-0.816, no gain.

- side-scale2 (pc-16-1 + 3x wider photo view): 0.811 vs 0.815, Olympic Park found 60.3% vs 60.1%. No gain; dropped.
- LiDAR step across council kerb (10 m pieces, kl.steps): found median 0.066 m (39% >= 8 cm), blind misses 0.072 m (43%), only 18% without
  ground points. The LiDAR shows the kerb where the model is blind, so the evidence is in the input; the model does not use it there.

- side-longmine (30% of chips at missed stretches > 40 m only): 0.803 vs 0.815, worse on 7 of 8 boxes; Olympic Park found 59.1%. Dropped.
- Plateau: since round 16 every change lands at 0.80-0.815 (averaging, gap net, hysteresis, wider view, long-miss mining, mine 0.5).
  The photo+LiDAR segmentation model looks at its ceiling; the blind long misses need another kind of method.

- side-pdrop8 (photo blanked on 80% of chips): 0.808 vs 0.815, Olympic Park found 57.8%. No gain; dropped.

## 3 Nov LiDAR step detector (thread "Find the kerbs the model misses")
- kerbstep.py (CPU, no training; log C:\kerb\step2.out, lines C:\kerb\step): redraws pc-16-1 lines from C:\kerb\long P at 0.6 (base 0.816,
  matches the round), then adds pieces >= 1.5 m from drawn lines where the ground steps up 4-25 cm away from the centreline.
  Plain 1 m height difference: candidates near 43% of missed kerb but only 7% of candidates real; adds nothing.
  Step-vs-slope fit on a 3 m profile (Zhou & Vosselman 2012): 18% real; best 0.814 (smin 0.04-0.08, min length 20 m) vs 0.816. Only nbcheck
  gains (0.736 -> 0.743). Ground at 1-6 pts/m2 is too sparse to FIND kerbs (Vosselman used ~20); use the step as a CHECK only. kerbstep_diag.py
  breaks a box's missed kerb down by test. 42% of nbcheck missed council kerb lies inside lot polygons (lot test is off).
- Research + game plan doc (Claude Doc): https://claude.ai/artifact/19EfzmPzeuU9rLbRpJLBY8

- Short misses (kerbshort.py, log C:\kerb\short.out): of 7.5 km missed in stretches <= 40 m with P >= 0.5 nearby, 6.2 km "off" (mask within
  1 m, traced line 1-2.5 m away), 0.6 dropped by tidy/MIN_LEN, 0.7 under the 0.6 cut. Ridge tracing (kerbridge.py, keep mask cells within
  0.8-0.9 of the 5-15 cell max): 0.812-0.816, no gain. kerboff.py: LiDAR step >= 4 cm at the drawn line vs at the council line, Paddington
  28% vs 10%, Newport 37% vs 13% -> much of "off" looks like the council line offset ~1.3 m, not the model. Confirm over the photo.
  (kerbshort/kerbridge/kerboff.py uncommitted on the PC until Jacky OKs a push.)

- Street-offset prior (kerbstreet.py, logs C:\kerb\street.out, street_m.out): per centreline + side, median drawn-kerb offset (>= 10 m drawn,
  IQR <= 0.6 m) carried along the street, trimmed 3 m past other streets, pieces >= 10 m with no line within 1.5 m. Best: keep pieces with a
  LiDAR step >= 3 cm on 30% of samples, 0.819 vs 0.816 (0.7 km added, worst held-out 0.788). All pieces 0.817; mirrored to the other side
  (KERB_MIRROR=1) 0.818 with check, 0.802 without. Proposals reach only 0-11% of the long misses: those streets have neither kerb drawn.
  Small, deterministic gain. WIRED IN 4 Nov (81c1b65): CFG "street": 1 runs kerbstreet.fill_file after vectorising (and after gapfill),
  same kerb layer, pieces tagged properties.street = 1. side-street-eval (pc-16-1, minutes 0, street 1; log C:\kerb\streeteval.out,
  out C:\kerb\out\side-street-eval): 0.817 vs 0.815 (scenario 0.790 vs 0.788, thresh picked 0.8 vs 0.7). Gains nbcheck +1.3,
  Kensington +1.3, Melb CBD +1.0; Paddington -0.5. NEW BEST pipeline = pc-16-1 + street. Use street 1 in every control from now on.

## NEXT (in order)
0. 4 Nov Fable review: direction, step plan and stop rules in docs/handoffs/kerbs-direction.md. Learned tracer PAUSED until its
   steps 1-3 are done; the misses are a location problem (clear kerb found = under-trees found; main roads 53%), not visibility.
1. Score side-pdrop8.
2. DONE: LiDAR step detector, no gain alone (above). Game plan from the doc, in order:
3. DONE (above): short misses are mostly a 1-2.5 m offset, no tracing fix. Left: photo check of the offsets; Newport offset 0.31 m; Kensington precision 68%.
4. DONE (0.819, above). Was: Street-offset prior: carry the drawn kerb's offset from centreline / lot boundary along the same street into undrawn stretches, keep pieces
   the step fit or weak P (0.1-0.5) confirms. Oracle check first (share of long misses within 1 m of the carried offset).
5. DONE, no gain: side-stepfit (CFG stepfit, step-fit height + roughness as input layers 10-11, kerbstep.fit) 0.809 vs 0.815,
   Olympic Park found 57.2%. pdrop 0.8 (photo blanked on 80% of chips) also 0.808. Since round 16, ten changes all land at 0.80-0.815:
   the segmentation model is at its ceiling on this data. Denser LiDAR is NOT available (ELVIS checked 4 Nov): every check/held-out box
   already uses its newest state survey (Parramatta, Olympic Park: Sydney201906 only; others Sydney202005/202006); the 2018 council
   surveys (SydNthB2018, SydEstB2018) are no denser. Remaining levers: kerbclean on all boxes, kerb tracing (street prior now wired, 0.817).
6. DONE 4 Nov, little change: kerbclean.py on all 10 boxes at 0.8 on the side-street-eval lines (roofs only for Parramatta, others
   road + rail rules; C:\kerb\kp\*_clean.json). F1 moves only Parramatta 0.786 -> 0.802 and cbcheck 0.916 -> 0.921; Kensington drops
   5.5 km off-road lines but F1 stays 0.759, Melb CBD 0.605. The council reference is not what holds the score down outside Parramatta
   CBD, so no ELVIS order for roofs. Left:
7. Tracing pilot, 4 Nov (kerbtrace.py, no training; log C:\kerb\trace.out; 8 NSW boxes, side-street-eval lines at 0.8, pc-16-1 P in
   C:\kerb\long): walk on 1 m steps from every line end, turn <= 15 deg/step, evidence = max(P, LiDAR step / 8 cm), stop after 3 weak steps.
   NSW scenario 0.814 -> 0.818 (e0.5, 9.3 km added, worst held-out unchanged 0.786). Found rises on every box (Olympic Park 57.7 -> 62.0%,
   e0.3 63.9%), precision falls: only about half the traced length is kerb. "bridge" (keep only traces that reach another line) 0.816.
   Read: tracing reaches kerbs the pixel model misses; the hand-made stop/turn rule is what costs precision. Jacky OK'd longer GPU time
   (4 Nov) if viable, and Melbourne runs on photo only (no DTP LiDAR, treat as not existing).
   NEXT = learned tracer (iCurb-style, Xu et al. RA-L 2021): small CNN on a rotated crop (photo, P, LiDAR step, lots, centreline distance)
   around the current point predicts the next step angle + stop; teacher = council kerb paths in the training boxes; second pass on its
   own rollouts (DAgger). Seeds = line ends as in kerbtrace.py. Compare with e0.5 (0.818 NSW) and wire as CFG "trace" after street. denser ELVIS LiDAR over check boxes; kerb tracing (iCurb) only if 3-5 leave long misses.
- Watchers die on session restarts: side-longmine sat finished from ~09:15Z to 13:37Z. Chain runs in one .ps1 where possible.

## Open items with Jacky
- Melbourne LiDAR email drafts (DTP Coordinated Imagery Program, Merri-bek virtual@merri-bek.vic.gov.au) and the newer NSW LiDAR
  email: offered, no answer. Drafts only, never send.
- Picture sheets of the miss check: on the PC in Claude's temp scratchpad (misscheck\), not copied to Drive.

## 4 Nov results (thread "Raise kerb score to 0.85", following kerbs-direction.md)
- Step 1 DONE (kerbwhere.py, log C:\kerb\where.out; side-street-eval lines at 0.8, pc-16-1 P). Found by distance to the nearest lot:
  0-3 m 64% (41.6 km; 18% of training labels), 3-6 m 94% (79.2 km; 58%), 6-10 m 71%, 10-15 m 47%, > 15 m 77%. Far side / median
  40% (4.4 km; 7% of training) vs lot side 83%. Centreline 4-6 m 88%, 0-2 m 71%, 10-15 m 41-49%, > 20 m 0%. 56-85% of each box's
  missed kerb lies in (lot, centreline, side) types holding < 5% of the training labels (found kerb: 15-40%). Olympic Park lot 0-3 m
  found 38% with P50 0.00, Parramatta 42% / P50 0.31: the model is sure there is no kerb off its usual offset. -> prior problem,
  step 2a + 2b run. Far side/median is 7% of the training labels (not empty), so 2c (new arterial boxes) is not run.
- Step 2 RUNNING: side-cdrop.json (CFG cdrop 0.5 = lots/centreline/water blanked on half the chips; CFG nolot 1 = photo + LiDAR only,
  layers zeroed at drawing too), 150 min each from pc-16-1, street 1. Log C:\kerb\cdrop.out, out C:\kerb\out\side-cdrop\<id>.
- Step 3 DONE, no gain (kerbtrace.py filter, log C:\kerb\tracefilt.out). HistGradientBoosting keep/drop on the e0.3 traces, fitted
  leave-one-box-out on the 8 NSW boxes (NOT the training boxes: their P is near-perfect, so their traces would not look like real ones;
  the training-box P made so far is in C:\kerb\tracer). 899 traces, 44% good by length. Base 0.814, unfiltered e0.3 0.817, filtered
  0.815-0.816 at every cut 0.3-0.8 (kept precision 58-69%, 2.9-5.9 km). Not the stop rule (precision >= 60% at >= 2 km) but nowhere
  near the keep rule (0.823): the filter throws away found faster than it gains precision. Not wired. Rule pilot e0.5 (0.818) stays
  the trace reference.
- Learned tracer (kerbtracer.py, prep + teacher only, commit 63867fb) held as the doc says.
- Step 2 DONE, stop rule hit (C:\kerb\out\side-cdrop): cdrop 0.5 score 0.805 (scenario 0.781, thresh 0.8), nolot 0.770 (scenario 0.753,
  thresh 0.6) vs 0.817. Main-road found 60.8% / 61.5% vs 61.1% (first box with main roads): moves < 3 pts. The prior hypothesis
  is dead for this kind of training; no more variants of it. Olympic Park found 58.4% / 62.3%.
  CAUTION: a side run overwrites C:\kerb\kp\<box>_derived_*.geojson. The nolot run did; streeteval.ps1 was rerun 4 Nov to put the
  pc-16-1 + street lines back (check C:\kerb\streeteval.out before using kp lines).
- Step 4 NOT run: needs P 0.2-0.5 along >= 30% of the long misses; kerblong found 78% of them at P < 0.1.
- Programme result (kerbs-direction.md "Always"): steps 1-3 end at 0.817-0.818, below 0.83 -> stop and tell Jacky; recommend shipping
  kerbs by area with a per-council confidence, busiest first (tools/priority/TOP.md), training only in the background.

## 4 Nov arterial data round (kerbs-direction.md item 3): STOP ALL TRAINING
side-arterial.json, 150 min (3150 steps) from pc-16-1, street 1, 6 new arterial/median boxes (deewhy, frenchsforest, belmore,
lakemba, rosebay, rydalmere; no LiDAR grids on them). Found by road type, length-weighted over the 8 NSW scored boxes:
| run | scenario | main | collector | local |
|---|---|---|---|---|
| pc-16-1 + street (control) | 0.790 | 82.9% | 73.8% | 85.1% |
| a: + 6 boxes | 0.789 | 83.7% | 75.9% | 86.3% |
| b: + 6 boxes + rare chips 0.3 | 0.787 | 84.4% | 75.7% | 86.4% |
Main-road found +0.8 / +1.5 pts, under the 5-pt stop rule: all kerb training stops, pc-16-1 stays the model, the PC is free after
the ship run. Caveat: the new boxes had no LiDAR, so a LiDAR version of the same round is untested; it is not a reason to restart
by itself. Training restarts only on new information (denser or Vic LiDAR, a new council kerb reference, a user-reported miss pattern).
