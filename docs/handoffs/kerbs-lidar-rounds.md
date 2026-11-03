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

## RUNNING: gap-repair net on the PC (kerbgap.py, C:\kerb\gap.ps1, log C:\kerb\gap.out, started ~01:25Z 3 Nov, 45 min train then test)
Trained on council kerbs with pieces cut out; adds only pieces touching a drawn line. Tested on C:\kerb\cleanvg3 lines (3-model average at 0.6, base 0.814).

## NEXT (in order)
1. Read gap.out: keep if the scenario score beats base by more than 0.006 at a cut chosen on the check boxes.
2. Kerb tracing (iCurb / Topo-boundary, HKUST 2021-22) for the > 40 m misses; 74% of missed length has neither kerb of the street drawn.
3. Newport offset 0.31 m (limit 0.3) and Kensington precision 68% (Vic, aerial only) need their own look.

## Open items with Jacky
- Melbourne LiDAR email drafts (DTP Coordinated Imagery Program, Merri-bek virtual@merri-bek.vic.gov.au) and the newer NSW LiDAR
  email: offered, no answer. Drafts only, never send.
- Picture sheets of the miss check: on the PC in Claude's temp scratchpad (misscheck\), not copied to Drive.
