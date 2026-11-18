# Grid kerbs: how a run goes (15 Nov 2026)

1. `bldall.py`: Overture footprints per 1 km square (+-350 m) from tiles.openfetch.earth buildings.pmtiles (curl, not urllib).
2. `run1.sh x y` (K = work folder) per square: `kerbgrid.py --review` drafts one closed ring per blank block.
3. `sheet.py`: picture sheets for two independent reviewers; only blocks both pass go on.
4. Strict close-up pass, ONE block per 800 px picture, every block: sheet-size review missed ~1 in 15 odd blocks
   (ends across houses, cul-de-sac mouths, rear lanes inside the loop). 377 -> 350 kept on 15 Nov.
5. `join.py`: both-passed rings added to the last version, then the usual version gates (kerbaudit, kerbreview, kerbs-check).

Results 15 Nov: 1,107 drafted, 421 passed both sheet reviewers, 44 left out for running >3 m inside footprints,
27 more by the close-up pass; version 2026-11-15-c candidate 1,366 km (from 1,173), all gates pass.
Root cause of most odd blocks: footprints near any street line were ignored as shelters, so houses on a mapped street that
is not on the ground (paper road, path) were invisible. Now only footprints under 120 m2 are ignored: re-drafting the 43
affected squares drops 31 of 69 odd blocks and keeps all 156 good ones. The rest still need the close-up pass.

## Run 18 Nov 2026 (NSW ranks 21-40, no LiDAR traces there, so band widths fall back to HALF_W by road class)
K=/home/user/K: `cells.txt` (1 km squares of each suburb's 2 km box, minus the top-20 squares), `fetchin.py cells.txt`
(cadastre lots +-300 m and road centrelines +-500 m with functionhierarchy and roadontype per square), `official.py`
(Liverpool, Woollahra, Parramatta council kerbs; Parramatta's hosted layer errors on 1000-row pages, use 200),
bldall.py, `run2.sh x y` per square (3x3 neighbour inputs only, `--official`), `combine.py`, `bldgate.py` (ring over 3 m
inside an Overture footprint of 120 m2 or more: out), `closeup.py` (one block per 800 px tile, 2x2 sheets), two Sonnet
reviewers per 20 sheets (BRIEF in the run folder), `join2.py` (both OK, no grey tile, ring simple). Result: 1,796 drafted,
376 building, 1,420 reviewed, 1,140 both OK, 9 self-touching, 1 wobble cap: 1,130 added, 683 km.
Lessons: the gate's roads folder must be current (stale Nov 5 roads made kerbreview flag 2 false gaps in the old version);
kerbreview's 48-tile sheet is downsampled when an agent opens it whole, so a reviewer must judge it in 12-tile crops.
