# Lab log: Vic angle-parking bays and paved corners (scenario 17), thread "Make kerbs work for Vic angle parking", 21 Nov 2026
Base: openfetch-derive 26f6e4f (VK1), my branch claude/project-thread-ywkhnl. Inputs .notes/kerb-vic-aer/inputs (prob 2026-11-19, prep x5).
## Round 0: baseline rebuilt on the same inputs (CPU, no model run)
- Carlton 58 rings 9.2 km: <1 m 83 %, <2 m 97 %, >3 m 1.4 %. North Melbourne 29 rings 12.2 km: <1 m 87 %, <2 m 97 %, >3 m 0.7 %.
  (lead's 91 % NM bar not reproducible on these inputs, as VK1 found; 87 % is the baseline to hold.)
## Labelled fails (review 9, vic-2026-11-19-b verdicts.json)
- V12 Albert Park: west side runs straight between kerb outstands across indented angle bays, 2.5-4 m road-side of the back-of-bay kerb, ~35 m.
- R3 Fitzroy North: SW corner cut diagonally ~20 m across an evenly paved corner; true kerb corner 8-10 m away.
- V33 Preston: north side along building fronts, kerb 2-3 m further out (wide paved footpath, scenario 18 territory, noted only).
## Round 1 (21 Nov 2026): diagnosis on known answers, 3 hypotheses refused
Known answers: City of Melbourne kerb polygons + On-street Parking Bays points (CC BY; angle bay = next bay point < 3.3 m away).
- Per ray (raytruth.py, Carlton / North Melbourne): angle-bay rays read +0.8 / +0.6 m median past the council kerb (parallel -0.2 / -0.1);
  16 % / 9 % read > 2 m out (parallel 4-5 %). Road probability crosses 0.5 about 1 m past the kerb at angle bays, at the kerb elsewhere.
  => in the council area angle bays are read about 1 m out: inside the 2D bar. Not the review-9 failure.
- Blocks facing angle bays are kept as often as other blocks (Carlton 14 kept / 32 refused; North Melbourne 22 / 38); refusals are
  the usual "no footpath measure" / "too narrow", not bay-specific.
- Albert Park (prep rebuilt; buildings from Middle Park prep because the Vicmap WFS timed out): 23 sides "two levels" (1.0 km), blanked by
  the VK1 GAP rule; 262 sides have no aerial square (15.8 km): prob squares 318_*, *_5810 were never made. Coverage is mostly missing squares.
- H1 (two levels: take the near level = back of bay): refused. Council kerbs: near level within 1 m on 16-19 % of two-level sides,
  median 44-62 %. The near level is usually a concrete footpath read as road (-2 to -4 m), not a bay back.
- H2 (paved corner: use the mitre point when it was refused as too far): refused. Chord err <= mitre err on every council-kerb corner tested
  (e.g. 5.5 vs 13.8 m). Worst chord corners on a sheet: rounded corners short of a kerb build-out, not odd shapes.
- H3 (two levels as contiguous runs along the side = stepped kerb, keep per-run offsets): refused. Per-run within 1 m 45 % / 31 % vs
  median 49 % / 50 %. Two-level structure in the aerial read is mostly misreads, not real steps.
- OSM street-side parking polygons as a back-of-bay reference: 399 in the council area, median 21 % of perimeter within 1 m of a council
  kerb (112 polygons >= 40 %). Too loose alone; thin coverage in Port Phillip (~30 polygons).
Conclusion: on the current probability map no rule separates real bays/steps from misreads (VK1 said the same). Next levers need a better read.
## Plan round 2
1. CPU fine-tune of the existing U-Net (not from scratch) on council crops weighted to angle bays and paved build-outs, labels from the
   council carriageway/kerb polygons; judge by raytruth angle "> 2 m out" (16 % / 9 %) and the Carlton/NM 83 / 87 % hold.
2. Make the missing Port Phillip / Fitzroy North prob squares on CPU so the review-9 spots (V12 Albert Park, R3 Fitzroy North) can be re-run and
   judged; the GAP blank stays until a fix beats it on them.
## Round 2 (21 Nov 2026)
- Step 1, missing aerial squares (same model unet-r34-2026-11-19.pt, CPU, ~1 min per square): 21 squares made (318_5808-5810, 319-321_5810,
  321_5816-5817, 322-325_5814-5817). Albert Park rerun: 13 rings / 5.2 km -> 52 rings / 20.4 km; "no aerial" sides 262 -> 7.
  Fitzroy North (new prep; Vicmap building WFS timed out twice, so no roof guard in this diagnostic run): 67 rings / 31.1 km.
  With the gap rule off Albert Park keeps 55 (3 more); the 4 rings it blanks look like plain blocks on a sheet, not bays.
  Squares: .notes/kerb-vic-angle/prob-cpu-2026-11-21.tgz.
- H4 paved corner (kerblot SPLAY_FAR 20 m, 60-120 deg): diagnosis on Fitzroy North chord corners: the 20 m diagonal (R3 type, 322309,5815487)
  is a square corner (89 deg) whose mitre point was refused only for being over 2D+4 m away, because the corner lot is cut back. All council-area
  chord corners are acute (26-33 deg), where the mitre point spikes (H2). Rule: accept the mitre point up to 20 m when the corner is 60-120 deg.
  Effect: 1 ring changed in 4 boxes (Fitzroy North corner, +104 m2); Carlton / North Melbourne 83 % / 87 % unchanged. Selftest test_splay.py.
  Derive c3d7dec. Small: a real but rare shape.
- Step 2, fine-tune ft1 (CPU, 45 min, 1,410 steps of 8 x 256 px, lr 5e-5, BN frozen, 6 council boxes outside Carlton/NM, half the crops on
  angle bays, angle zone x5): REFUSED. North Melbourne angle rays > 2 m out 9 % -> 4 %, but Carlton angle 16 % -> 17 %, parallel / other rays
  > 2 m out 4-5 % -> 7-9 %, rings 58 -> 22 and 29 -> 19, within 1 m 83 -> 80 % and 87 -> 82 %. The fine-tune pushed every read ~0.2 m outward
  and broke the side agreement; weighting one class on 6 boxes over-fits. Model not kept.
## Round 3 (21 Nov 2026): blind pack for the lead's G2
- Fitzroy North roof guard: Vicmap building WFS 504 even on 250 m boxes; Overture copy (bld_overture.py, 73k footprints) used; rerun 67 rings,
  31.1 km, 0 over a roof (same as without).
- Pack .notes/kerb-vic-angle/pack17/ (41 crops, key pack17-KEY.json apart): 15 Albert Park, 15 Fitzroy North, H4 corner, 4 gap-blanked rings,
  6 known-odd controls (pre-H4 R3 chord, 3 rings moved 5 m out, 2 moved 5 m in). Waiting on the lead's verdicts.
## Round 4 (21 Nov 2026)
- Lead G2 pack17: 33 OK / 1 odd / 1 unsure on real crops; controls 5 of 6 caught (S12, 5 m into the road, missed).
- S06 (Port Melbourne L3195810-131): acute block tip, the reserve runs 10-15 m past the last lots; the ring rounds the lot outline 5 m out.
  S22 (L3185810-41): ring round a narrow planted reserve strip (10-12 m hairpin). Thin-limb rule (ring part < 14 m wide) refused: it also
  flags 6 acute tips, the 3 inside City of Melbourne within 2.2-3.1 m of the council kerb. Both dropped whole as known exceptions.
- Candidate vs 19-b: 21 new blocks (72 of the run duplicate 19-b blocks); kerbguard pass (Overture roofs 0, lane 0, council 0); kerbaudit 2 kinks,
  drop_audit leaves 1 out -> 20 rings 8.0 km. Lead whole-file sheet: 18 OK / 2 odd:
  - tile 15 L3215815-11 (Carlton North, Princes St side): one aerial width per side (4.25-4.5 m) applied along a side whose kerb is not
    parallel to the lot fronts: starts at the house frontage, drifts 6-8 m into the carriageway; top side mid angle bays 2-3 m.
    Input that drew it: kerblot's single offset per side (aerial gutter median), not a bad aerial read.
  - tile 19 L3225815-130 (Fitzroy, Alexandra Parade side): park kerb 3-4 m off, main road with a wide reserve. Marginal.
  Both dropped whole. 18 rings go into vic-kerbs 2026-11-21.
- Lesson: a side's kerb is assumed parallel to its lot fronts; where a main road widens or narrows along a block the constant offset drifts.
## Round 5-6 (21 Nov 2026): version vic-kerbs 2026-11-21
- New kerbguard (counts council lines) read 23,789 City of Melbourne kerb outlines once polygons count; 2 Carlton rings doubled them (354 / 360 m): dropped whole (P-0246).
- Review sheet r5 (16 random spots over the whole file): 3 WRONG, all on 19-b rings (South Melbourne shadowed roadway 5-10 m, Hawthorn bend V 3 m into the road,
  Middle Park roundabout under canopy 8 m). Dropped whole; cases V1-V3 in kerbreview-cases-7855.json. r6 fresh sheet: 16 OK, V1-V3 no line.
- Version: 617 lines, 368.2 km, kerbs-check pass (940 pieces, 87 cells); openfetch main 2fc94953.
- OPEN (lead 5): 3 of 16 random spots on 19-b rings were wrong. Before the next Vic version, sweep the whole of 19-b (the measured road-edge walk, H5 canopy tools,
  on Vic intensity if held) or a bigger blind draw.
