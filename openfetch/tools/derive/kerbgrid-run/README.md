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
