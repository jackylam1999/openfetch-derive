# Kerbs version f (7-8 Nov 2026), handoff for version g

Thread "Fix local-street kerbs for version f". Code: openfetch-derive branch claude/project-thread-w2p8ss fdf1dbe (on top of c09cop 66491fd).

## What f is
- Run: `kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --local-only` (~20 min, 1 core) on
  derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz (84 new boxes; 3,054 km r11). Output 2,772 km (e: 1,559 km).
- Files: /mnt/project-files/.notes/kerb-f/ (kerbs-nsw-f.geojson.gz, kerbnet-stats.json, reviewer/, reviewer-independent/).
- New steps in kerbnet main (all general rules):
  - streets on bridges/tunnels (roadontype 2/3) are left out of build/fill/guide/joins; tunnels out of the scope cut
    (Jacky 8 Nov: kerbs stopped at the WestConnex tunnel).
  - across(): a kerb never crosses a ground street centreline (or an fh 9 piece <= 15 m inside a junction); the stretch
    within half width + 2 m is cut, gapjoin(reach 20) rounds the corners. 1,393 cuts on whole suburbs.
  - no_motorway local scope also cuts within SCOPE_W (8.5-14 m) of any fh 1-4 carriageway (V41).
  - no_islands(): kerb with parallel carriageways on both sides for 15 m+ goes (medians/islands out of scope).
  - lot_tails(), unmerge(), endpairs() (hooked ends, straight breaks up to 30 m), snap_near() (ends 1-3.5 m short),
    deknot(), unfold(), and a final untie in lon/lat (7844) space as readers see it.
- Old inputs: geometry 0 flags, all e cases clean. Whole suburbs: reviewer FAIL: geometry 4 spots (self, fold, gap, beside;
  my run said pending only because 1/2,772 km rounded to 0; fixed in kerbreview 2b5712c), merge now capped 0 (f has 7);
  visual 20 of 47 wrong (7 of 8 random tiles OK). Verdicts .notes/kerb-f/reviewer-independent/verdicts.json; all now cases (v6yk7j d2c972d).

## Fix list for g (EPSG 7856)
- Corners/junctions: Y/X with tails 335731 6251088, 317930 6253368, 332370 6247179; square corner 337956 6247752,
  337442 6247053; doubled strand + T 306389 6189091; diagonal off kerb 323692 6256759; closed street end open 326633 6247957;
  corner cut across mouth then 2 m into road 327320 6247919.
- Missing: north kerb 334885 6250056 (across() cut it, gapjoin did not rebuild); V54-type blocks with NO block loop
  (337950 6247110: lanes on two sides, polygonize gives no face - debug build() first).
- Strays: V48 328291 6246090 ends in a yard (no lot there); dead ends under trees 324789 6250363; line through park 314556 6257216;
  loop across parking 334049 6252312; 2nd strand by bays 317965 6253355; V44 331024 6246472 through parked cars + 13 m gap.
- Scope: V16 332861 6246448 lines on a multi-lane road over the canal bridge (bridge roads are out of the scope test now: keep
  bridges in `level` for no_motorway, they are; check fh of that road); V31 still follows the painted parking-lane line;
  random 336265 6243098 line along an arterial kerb.
- Merge cap 0: 7 left; unmerge only drops/cuts the sliding line when the slide is <3 m at 8 m back - widen or pick the junk side.

## Do not retry
- Lot-guide (see kerbs-version-e.md). Kerb on a centreline (within 1.5 m of fh <= 6 for 10 m+): centrelines are often drawn
  at the kerb on narrow streets, 7 of 9 sampled were real kerbs.
- Copying the kerb of the neighbouring street (Jacky's 8 Nov tip): 6 Nov test had only ~1/3 within 1 m; block loop already
  copies the other side / frontage.

## How to check
`kerbreview.py check out.json dir/ --roads <extracted roads/> --prev /mnt/project-files/.notes/kerb-e2/reviewer/review.json`
(v6yk7j latest). Scratch tools used here: spot sheets via kerbreview photo() with road fh colours; post-processing a finished
output with single steps is fast (seconds) vs 20 min full runs - confirm in a full run before sending.
