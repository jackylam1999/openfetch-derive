# Roof tracing rounds: the kerb method applied to LiDAR roofs (Fable, 4 Nov 2026)

For the Opus threads that run cards RT1-RT6 (docs/audits/TASKS.md). Read this file, then only the files a card names. The kerb
rules live in docs/handoffs/kerbs-method.md (R1-R9) and kerbs-direction.md; this file says what they mean for roofs. Jacky
(4 Nov 2026 14:42Z): take the kerb lessons over, run pilots, then a game plan that cheaper models execute systematically,
busiest council first (tools/priority/TOP.md: NSW = City of Sydney). Nothing here publishes or deploys.

## 1 What the roof tracer is, and why rows merge (read once)

openfetch/tools/derive (repo jackylam1999/openfetch-derive; the same files sit in the main repo's tools/derive):
pipeline.py runs one box: community.py (OSM + Microsoft shapes) -> roofs.py (LiDAR building-class points on a 0.5 m grid ->
blobs -> squared outlines) -> snap_pilot.py (moves each community shape onto the LiDAR roof, reads its height) -> lots.py (NSW
cadastre) -> gapfill.py (traces only where nobody drew, cut along lot lines, then LiDAR ground / 2.5 m height steps) -> gates.
The tracer has no model and no training: every "round" is a code or settings change, so there is no seed noise (R2's noise
floor is 0); the spread that matters is between scenes, so a verdict needs the change to hold on 2 of the 3 Sydney boxes AND
not lower the official-reference box (Gosford).

Diagnosis from the first pilot (Erskineville terraces, City of Sydney rank 4, 600 m box, Sydney 2020 LiDAR, OSM 509 houses):
1. The raw trace joins 94 % of the OSM houses into row blobs (141 blobs for 509 houses, median blob 351 m2, largest 28,755 m2).
   A terrace row is one roof surface in the LiDAR; the tracer cannot see party walls. Only the lot lines split it.
2. snap_pilot.py DROPPED 507 of 728 community shapes: a shape with shared walls scores "inside minus 1 m ring", and the ring
   is full of the neighbour's roof, so fit < 0.3 and on dense LiDAR the shape was thrown away (that rule was written for Microsoft
   shapes drawn smaller than their roof). gapfill.py then drew lot-cut strips where those OSM houses were. In the app the OSM
   house AND the strip show: that is the "OpenFetch roof overlaps OSM" and "whole row is one property" Jacky saw (Paddington
   P-0104, 4 Nov). The row is not merged by the tracer in the output; it is replaced by strips that follow the cadastre, not the
   drawn houses, and sit under OSM shapes that are still drawn.
3. The lot cut works where lots are Torrens (Erskineville: 0 gaps over 2+ lots), but HOUSE_LOT started at 100 m2 and 21 % of
   Erskineville lots are under 100 m2 (median 132), so narrow terrace lots did not count as house lots. Where lots are strata or
   community title (townhouse rows, Zetland), there is no lot line to cut along and only a LiDAR step could.

So the first lesson from kerbs holds here too: the misses are a WHERE / reference problem, not a visibility problem. The kerb
model was blind where its prior had never seen a kerb; the roof pipeline is blind where its "one footprint = one free-standing
roof" prior fails (shared walls), and it then overwrote a better judge (hand-drawn OSM) with a worse one (lot strips).

## 2 Scoring: roofscore.py (R5 for roofs)

`python3 openfetch/tools/derive/roofscore.py BOXDIR --box xmin ymin xmax ymax [--ref council.geojson --hmax FIELD] --json out.json`
`python3 openfetch/tools/derive/roofscore.py brief a.json b.json ...` prints one table, one line per box (the only thing a thread reads).

Columns: found (reference buildings with one output roof at IoU >= 0.5), precise (output roofs that match one reference building),
merged (reference buildings whose output roof also covers 40 %+ of another: the row-as-one-roof failure), trace_merged (the same
for the raw trace, so a tracer change and a lot-cut change can be told apart), split, offset, out_2lots (output roofs spanning 2+
cadastre lots of 30-2000 m2), lots_1 (built lots with exactly one roof), sites_ok (share of 150 m tiles with found >= 85 %,
merged <= 5 %, extra <= 15 %: what a user exporting a small site sees), h_bias (median height error, official references only).

Two kinds of reference, and they answer different questions (kerb rule R4: decide what the reference is first):
- OFFICIAL council footprints (Central Coast/Gosford truth set research/lidar-top20/gosford-council-7856.geojson.gz with HEIGHT_MAX;
  Tweed BuildingFootprint_LiDARandAI; Wollongong LOD2 scene layer, top-20 rank 17, not yet exported): absolute accuracy, heights,
  precision. City of Sydney, Parramatta, Randwick, Inner West publish NO footprints (checked 4 Nov 2026; NSW's Geoscape copy is
  government-only), so the busiest council has no official judge.
- OSM hand-drawn houses (community.geojson src=osm) in the inner suburbs: one shape per house, so found / merged / lots say whether
  the output KEEPS the houses apart. Because the output may contain the OSM shape itself, offset is 0 by construction and
  precision is low wherever OSM is incomplete (Microsoft and traced gaps fill the rest): on OSM boxes read found, merged,
  out_2lots, lots_1 and sites_ok only. Cadastre lots are the second judge (29 % of OSM Erskineville shapes span 2 lots themselves,
  because 4 m lots and 1 m drawing error overlap: so "2+ lots" is a warning, not a fail, on terrace lots under 60 m2).

Ship gate per scenario (the kerb "by road type" rule, applied by scene): found >= 85 %, merged <= 3 %, lots_1 >= 70 %,
sites_ok >= 70 %; on official boxes also precise >= 75 % and |h_bias| <= 0.3 m. Report every box, every round, in that table.

## 3 Scenario boxes (R3: busiest first, every scene, cross-checkable)

LiDAR tiles saved 4 Nov 2026 in /mnt/project-files/research/lidar-roof-pilot/laz/ (ELVIS links expired that day): Sydney 2020
tiles 332000_6246000, 332000_6248000, 334000_6246000, 334000_6248000, 334000_6250000; Gosford 2020 x4; Wollongong 2021 x3.

| scenario | box (MGA56, 600 m) | council (rank) | reference | tile |
|---|---|---|---|---|
| Victorian terraces, Torrens lots | ersk 332000 6247100 332600 6247700 | Sydney (Erskineville 4) | OSM + lots | 3326246 |
| dense terraces + shops, laneways | surry 334400 6248800 335000 6249400 | Sydney (Surry Hills 39) | OSM + lots | 3346248 |
| townhouse rows + apartment blocks, strata lots | zetland 334100 6246500 334700 6247100 | Sydney (Zetland 3 / Waterloo 2) | OSM + lots | 3346246 |
| suburban detached, known answer | gosford 345200 6299400 346000 6300200 (800 m) | Central Coast | official + heights | Gosford x4 |
| CBD towers (heights only, tracing off) | cbd 333900 6250500 334500 6251100 | Sydney (1) | OSM | 3346250 |
| coastal/hilly detached, official LOD2 | later: Wollongong 306500 6188500 ... | Wollongong (17) | official LOD2 | Wollongong x3 |

Before/after pilot outputs: /mnt/project-files/research/lidar-roof-pilot/{before,after}/<box>/ (combined.geojson, check.png,
report.md, scores json). Rerun a box in minutes: `python3 openfetch/tools/derive/pipeline.py <name> <box> OUT <tile.laz>`;
after a change in snap or gapfill only, copy the before folder and add `--from snap` (community, trace and lots are reused).

## 4 Rules for a round (R1, R6-R9 for roofs)

- One question per round, with a control: control = the current best settings (env switches below) on all four boxes;
  hypothesis = one change. Kept when found or merged improves beyond 2 points on 2 of 3 Sydney boxes and Gosford does not fall
  (found -1, precise -1, |h_bias| +0.05 at most). Everything else: dropped, written down with its numbers so nobody retries it.
- Switches, not forks: every hypothesis is an environment variable read by snap_pilot.py / gapfill.py / roofs.py (like CFG in
  kerblearn.py), default = old behaviour, so the control and the change run from one code base. Switches and defaults since RT1 (4 Nov 2026):
  KEEP_SHARED=1 (snap_pilot keeps OSM shapes with shared walls on dense LiDAR; 0 = old rule), LOT_MIN=30 (gapfill + pipeline
  count terrace lots as house lots; 100 = old), ROW_SPLIT=1 (row cut from thread "Split terrace rows into separate roofs":
  lot-line + party-wall cut of rows; 0 = none), ROW_MAPPED=row3 (a mapped OSM/Microsoft outline is cut only when it covers
  3+ one-home lots under 250 m2; all / ms are the other values). Gates in pipeline.py: "OSM houses kept" (>= 90 % of OSM
  houses lying 80 %+ on LiDAR roof) and "terrace rows split into houses" (<= 1 % of outlines over 3+ one-home lots). A kept switch becomes the default in the next card, and the gate in pipeline.py.
- Every round ends with this takeaway in this file (section 6), in the kerb shape:
  `Round N. Question: does <change> raise found / lower merged? Control: <brief table>. Change: <brief table>. Verdict: kept /
  dropped. Learnt: <one line per scenario that moved>. Next: <queue head and why>.`
- The thread reads the brief table and ONE check.png per round. No full geojson reads, no whole-file reads over 60 KB.
- Budget: one card = one thread = one or two rounds, under ~15 commits. Report to Jacky only at a milestone: ship gate met on a
  scenario, a plateau, or a decision (e.g. licence or a new ELVIS order, which needs his PC and his OK).

## 5 The hypothesis queue (ordered by expected gain per hour; cards RT1-RT6)

1. RT1 Keep the better judge (done in the pilot, make it default): KEEP_SHARED=1 for OSM only (Microsoft shapes merge rows
   themselves: 81 % span 2+ lots in Erskineville) + LOT_MIN=30. Then: a Microsoft shape with shared walls on dense LiDAR is
   dropped and the lot-cut trace takes its place (as now); an OSM shape is kept. Add the gate "OSM houses kept >= 90 % where
   the LiDAR shows roof under them". Rebuild nothing yet.
2. RT2 Fine LiDAR height step (the kerb step detector lesson, docs/handoffs/kerbs-lidar-pilot.md: a 7 cm kerb step is visible at
   1-6 pts/m2; Sydney 2020 roofs have 8+): in gapfill.by_lidar add a second cut: cells where the 0.5 m DSM jumps 0.3-2.5 m
   (parapet or party wall) AND the jump cells form a line that crosses the piece from one outline edge to the other at right
   angles to the long axis (a parapet line, not roof furniture). Switch STEP_FINE=0.3. Scenario it targets: zetland (strata
   townhouse rows), surry shop rows. Kill if zetland merged does not fall by 3 points or Gosford precise falls.
3. RT3 Roof ridge / plane split: within a row piece still spanning 2+ built lots after RT2, segment the DSM into planes (normal
   from a 3x3 fit), cut where plane direction flips (hip to hip between semis) or at a valley line. Only if RT2 leaves merged > 5 %
   on zetland.
4. RT4 The official judges: export Wollongong LOD2 footprints (I3S scene layer, src/regions/nsw/council-models.js) to a geojson
   truth set and run the Wollongong box; rerun Tweed with the saved truth. Gives precision and h_bias on three councils.
5. RT5 The "where is it blind" table (kerbwhere.py lesson, cheap, CPU): for every reference house in the four boxes record found,
   merged, lot kind (Torrens / strata / none), shared walls (yes/no from neighbours within 0.5 m), roof height, whether OSM had it,
   and print found % by band. It decides whether RT3 is worth running and which scene to fix next.
6. RT6 Rebuild and rescore the top-20: once RT1 (+RT2 if kept) are default, rebuild the 2026-11-02 areas (needs a new ELVIS order
   via Jacky's PC: he must OK it) and run roofscore on the five pilot boxes from the rebuilt layer before openfetch-publish-derived.
   Also fold the roofscore brief into tools/mirror/roofs-check.py so every published version carries its scores.

Not doing (recorded so nobody retries): a learned roof model (no labels but OSM; the kerb programme showed ten model variants
at the noise floor while the data/reference moves were the only gains); wider closing in roofs.py (joins neighbours, Tweed 27 Oct);
hand-drawn truth for Sydney (days of work).

## 6 Rounds

### Round 0 (Fable, 4 Nov 2026): control vs RT1 (KEEP_SHARED=1 for OSM + LOT_MIN=30)

Control = today's pipeline (what version 2026-11-02 was built with). Reference: OSM houses in the three Sydney boxes, Central Coast council footprints in Gosford.

Control:

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 19% | 25% | 5% | 94% | 1% | 0.74 m | 15% | 22% | 0% | - |
| surry | osm | 482 | 39% | 49% | 10% | 95% | 0% | 0.78 m | 21% | 41% | 0% | - |
| zetland | osm | 276 | 37% | 66% | 8% | 86% | 0% | 1.24 m | 10% | 33% | 23% | - |
| gosford | official | 166 | 49% | 64% | 17% | 39% | 2% | 1.01 m | 11% | 53% | 6% | +0.01 m |

RT1 (KEEP_SHARED=1 for OSM shapes + LOT_MIN=30):

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 87% | 62% | 1% | 94% | 0% | 0.00 m | 31% | 65% | 25% | - |
| surry | osm | 482 | 80% | 69% | 7% | 95% | 1% | 0.00 m | 37% | 58% | 12% | - |
| zetland | osm | 276 | 79% | 83% | 9% | 86% | 0% | 0.00 m | 37% | 52% | 38% | - |
| gosford | official | 166 | 49% | 64% | 17% | 39% | 2% | 1.01 m | 11% | 53% | 6% | +0.01 m |

Verdict: KEPT. Found rose 19 -> 87 % (Erskineville), 39 -> 80 % (Surry Hills), 37 -> 79 % (Zetland); merged fell 5 -> 1 % in Erskineville,
about the same in Surry Hills and Zetland (7-9 %: shop rows and strata townhouses, no lot line to cut along); built lots with exactly one
roof 22 -> 65 %, 41 -> 58 %, 33 -> 52 %; Gosford unchanged (its dropped shapes are Microsoft's, which the switch does not keep).
Pictures: research/lidar-roof-pilot/{before,after}/ersk/check.png (before: 507 OSM terraces missing and lot strips over them; after: the
terraces kept, strips only where nobody drew).

Learnt: the row-merge Jacky saw is mostly the pipeline overwriting hand-drawn houses with lot strips, not the tracer alone; the tracer still
joins 86-95 % of houses (trace_merged), so where no OSM house exists and lots are strata (Zetland 9 % merged, 40 % of lots with 2+ roofs because
OSM shapes straddle strata lots) only a LiDAR cut can help: that is RT2. Gosford (official, town centre) found 49 %, merged 17 %, offset 1.0 m:
the official-reference problem is shop rows and Microsoft shapes dropped as shared-wall, RT2 + RT5 territory, and the number to beat.
Next: RT2 fine step on zetland and surry (the rows left merged there sit on strata or shop lots the cadastre cannot split).

### Round 1 (RT1, Opus, 4 Nov 2026): RT1 as default, combined with the row cut

Code: openfetch main tools/derive at bf7430c/c1a04c1 (row cut, ROW_SPLIT) + RT1 defaults. Same four boxes, community/trace/snap/lots
shared by every variant, gapfill and gates rerun (`--from gapfill`). Bug found and fixed first: the round-0 KEEP_SHARED test read a
stale loop variable (the LAST community shape's src, not each shape's); snap_pilot now keeps a per-shape property list and writes
id + src on every output shape. Also fixed: by_rows crashed on a piece with no roof points inside it (Gosford).

RT1 alone (ROW_SPLIT=0): matches round 0 within 1 point on found / merged in the three Sydney boxes; Gosford found 49 -> 52 %,
precise 64 -> 60 % (its OSM shapes are now really kept; round 0 kept none there because of the bug). FAILS the terrace-row gate on
ersk (25 rows), surry (71), zetland (4).

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 87% | 65% | 1% | 94% | 0% | 0.00 m | 26% | 66% | 25% | - |
| surry | osm | 482 | 80% | 69% | 7% | 95% | 1% | 0.00 m | 36% | 58% | 12% | - |
| zetland | osm | 276 | 79% | 84% | 9% | 86% | 0% | 0.00 m | 36% | 52% | 38% | - |
| gosford | official | 166 | 52% | 60% | 17% | 39% | 3% | 1.00 m | 15% | 57% | 6% | +0.00 m |

Row cut on every mapped outline (ROW_SPLIT=1, ROW_MAPPED=all): passes every gate, Gosford merged 17 -> 6 %, lots_1 up everywhere,
but Gosford precise 60 -> 41 % and outputs 144 -> 214 (over-cut shops/houses on 2 lots); Surry Hills found 80 -> 67 %.

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 86% | 46% | 1% | 94% | 7% | 0.00 m | 10% | 70% | 12% | - |
| surry | osm | 482 | 67% | 29% | 5% | 95% | 10% | 0.16 m | 6% | 78% | 0% | - |
| zetland | osm | 276 | 76% | 62% | 8% | 86% | 7% | 0.34 m | 16% | 52% | 23% | - |
| gosford | official | 166 | 53% | 41% | 6% | 39% | 4% | 1.03 m | 1% | 70% | 0% | -0.02 m |

Row cut on mapped outlines only over 3+ one-home lots (ROW_MAPPED=row3; traced pieces still cut by by_rows):

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 87% | 51% | 1% | 94% | 0% | 0.00 m | 18% | 70% | 19% | - |
| surry | osm | 482 | 70% | 34% | 6% | 95% | 1% | 0.00 m | 16% | 79% | 0% | - |
| zetland | osm | 276 | 78% | 75% | 9% | 86% | 0% | 0.00 m | 32% | 53% | 38% | - |
| gosford | official | 166 | 52% | 59% | 17% | 39% | 3% | 1.00 m | 14% | 57% | 6% | +0.00 m |

Microsoft outlines only (ROW_MAPPED=ms): Gosford merged 7 %, precise 47 %; fails the row gate on surry (59) and zetland (4).

| box | ref | n_ref | found | precise | merged | trace_merged | split | offset | out_2lots | lots_1 | sites_ok | h_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ersk | osm | 509 | 87% | 51% | 1% | 94% | 0% | 0.00 m | 16% | 65% | 19% | - |
| surry | osm | 482 | 80% | 61% | 7% | 95% | 1% | 0.00 m | 30% | 58% | 12% | - |
| zetland | osm | 276 | 79% | 82% | 9% | 86% | 0% | 0.00 m | 35% | 52% | 31% | - |
| gosford | official | 166 | 54% | 47% | 7% | 39% | 5% | 1.02 m | 8% | 74% | 0% | -0.05 m |

Verdict: RT1 KEPT as default (KEEP_SHARED=1, LOT_MIN=30, gate "OSM houses kept" passes 96-100 % on all four boxes). Row cut KEPT
as ROW_SPLIT=1 with ROW_MAPPED=row3: the only variant that passes the terrace-row gate on all four boxes (what Jacky saw in
Paddington) without lowering Gosford (found 52, precise 59 vs 60, merged 17, h_bias 0.00 m); ROW_MAPPED=all DROPPED (Gosford precise
-19), ms DROPPED (row gate fails). Cost of row3 by the OSM judge: Surry Hills found 80 -> 70 % and precise 69 -> 34 %, because OSM
draws many Surry Hills rows as one shape and row3 cuts them into houses (by the lot judge it is better: out_2lots 36 -> 16 %, lots_1
58 -> 79 %). The OSM judge cannot score a correct cut of an OSM row; RT4/RT5 (official judges, per-house table) must confirm it.
Learnt: ersk: RT1 alone already near ship gate on found (87 %); row cuts change nothing there. surry: rows drawn whole by OSM are the
open question. zetland: merged 9 % untouched by every variant (strata townhouses, no lots and no step found): RT2 target. gosford:
merged 17 % is Microsoft shapes over 2 lots; cutting them halves merged but over-cuts: RT2/RT5.
Next: RT2 (fine step) on zetland and Gosford, control = these defaults (row3 table above).

