# Finding more real kerbs: what was measured (7 Nov 2026)

Thread "Explore ways to find more real kerbs" (Opus, research only, nothing built or published). Jacky asked whether the kerb
fine-tuning raises accuracy; it does not (found flat ~70%, precise ~82.5% vs Parramatta council kerbs since 5 Nov). This note
says where the missing real kerb actually is and what to do next. Waiting on Jacky's choice before anything is built.

## Measured (cloud, CPU only, published version 2026-11-05, the only one on openfetch-data so far)
- Parramatta suburb vs City of Parramatta kerbs (raw council lines, rail corridor removed, 1 m tolerance): whole suburb found
  56%, precise 84%. Inside the area OpenFetch drew: found 75%, precise 84% (agrees with the 70-72% on the cleaned reference).
- 71% of the missed council kerb had NO OpenFetch line within 15 m, 85% of it in runs > 40 m. Picture check of 12 random such runs
  (NSW imagery): 10 of 12 are plain, clearly visible kerbs on ordinary streets; 1 is under a CBD building, 1 a park path.
- Cause: the ship run (kerbapply.py, docs/handoffs/kerbs-ship-pc.md on branch tkuw2p) drew a 2 x 2 km block of 1 km boxes per
  suburb around a hand-picked centre, not the suburb. The south of Parramatta suburb was never drawn.
- All 20 shipped suburbs (openfetch/tools/derive/kerbcover.py, every 5 m of state centreline, function hierarchy 2-6, kerb within
  15 m): 1,081 km of streets, 59% have a kerb. Only 64% of the street length lies inside the drawn 1 km squares; there 92% has a
  kerb. 389 km of street sit outside the drawn squares. Worst: Mosman 35%, Parramatta 38%, Auburn 47%, Merrylands 52%,
  Randwick 53%. Sydney CBD 70% and Haymarket 69% are inside drawn squares (tracing gaps, dense centre).
- Whole-suburb cover needs about 84 more 1 km boxes (155 squares touch the 20 suburbs by > 5 ha; 72 drawn).

## Ranked recommendation
1. Draw whole suburbs, not 2 x 2 km blocks (same model, same kerbnet/kerbdraft clean-up, must pass the kerb reviewer).
   Expected: streets with a kerb 59% -> about 90%; Parramatta suburb found vs council 56% -> about 75%. Cost: fetch + draw
   ~84 boxes on the PC (1-2 sessions); LiDAR: first check which of the 49 held ELVIS 2 km tiles already cover them, order the rest
   only with Jacky's OK. Boxes without LiDAR ship "partial" as before. Change kerbapply boxes() to take the suburb polygon
   (all km squares it touches by > 5 ha) instead of lon/lat + km.
2. Independent second score outside Parramatta (score only, no training): Sutherland Shire and Wollondilly kerb and gutter
   lines were added to the app after training ended (docs/regions/nsw.md). Draw one busy box in each, score with the same
   compare. Gives honest numbers, does not add kerbs.
3. Not proposed, already proved not to work or no source (do not retry): more model variants or labels (10 variants 0.80-0.815,
   arterial data round +0.8/+1.5 pts main-road found), map hiding, trace filter, learned tracer (no evidence along long misses),
   lot-frontage fill (no gain on real output), gap net; sharper aerial (model scores 0.808 with the photo blanked on 80% of chips;
   NSW imagery is already ~7 cm); denser NSW LiDAR (none open; newest ELVIS surveys already used; NSW spec floor 4 pts/m2);
   City of Melbourne point cloud/mesh as a LiDAR substitute (rejected 30 Oct: photogrammetric, 25 cm, no ground under trees).

## Files
- openfetch/tools/derive/kerbcover.py (this branch): coverage per suburb, no truth needed; rerun on every new version.
- Picture sheet: project files kerbs/more-kerbs-misses-2026-11-07.jpg (red council, cyan OpenFetch, 120 m tiles).

## Decision
Jacky 7 Nov 10:06Z chose "Draw whole suburbs" (item 1). The build goes to a fresh PC + cloud thread; it starts from this note.
