# Kerbs version g (8 Nov 2026), handoff for version h

Thread "Fix local-street kerbs for version g". Code: openfetch-derive branch claude/project-thread-vvxu3s (on main b19c57a).
Jacky 8 Nov 07:22Z: the build + review loop runs on its own (h, i, ...) until a version passes or two versions in a row do not
improve the visual fail count; then report to the coordinator (not Jacky).

## What g is
- Same run as f: `kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --local-only` (~22 min, 1 core) on
  derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz. Output 6,418 lines, 2,734 km.
- New file tools/derive/kerbg.py, `clean()` run last in kerbnet main (after deknot/unfold, `--no-g` skips it). Steps in order:
  bridges (kerb parallel within 12 m of a fh 1-7 bridge/tunnel centreline goes), streetless (stretch > 16 m from every ground
  street; short line mostly > 11 m goes whole), away (free end gaining distance from its street), hairpins + folds, doubles
  (parallel strand 0.3-5 m with no street or lot between: shorter one loses the stretch), junctions (end touching a line: join /
  take over a short tail / cut back 5.3 m), hooks (end turning > 45 deg in last 10 m and stopping near a kerb's middle: hook cut),
  caps (two ends either side of a dead-end centreline: Bezier cap), corner_join (end pairs: straight across up to 30 m, corner
  within 8 m, any pair within 2.5 m; never across a street or kerb; a loop left 2.5 m open is closed), fillets (turn > 50 deg
  over +-2 m gets a 4 m curve), junctions again, besides, tees (end 1-5 m short of a kerb's middle, no street between: cut
  back 5.3 m), folds, endtrim/endfix (self-touch as read in lon/lat 7844 at 8 dp), ringseat (loop seams moved away from other
  kerbs; a loop touching itself in lon/lat is untied there).
- Fast loop used here: post-process the finished f output with kerbg alone (scratch tools post.py/steps.py/spot.py, ~4 min)
  and kerbreview --no-photo; confirm in a full run.
- Result: geometry 0 hard flags (f: 4 + 7 merge), cases clean; VISUAL FAIL 26 of 48 wrong (f: 20 of 47). Files
  /mnt/project-files/.notes/kerb-g/ (kerbs-nsw-g.geojson.gz, reviewer/, reviewer-independent/verdicts.json).

## Lesson (main one)
g removed bad shapes (cut back, dropped) and the visual reviewer saw the holes: "deleted, not fixed". Every cut must be
followed by a redraw of the kerb there (join to the kerb it ran into with a corner, cap the end, or walk the block loop as
guide() does). Do not ship a step that only deletes. Near ends are now capped at 0.05 per km (g had 624, ~0.23/km).

## Fix list for h (EPSG 7856, reviewer cases on derive v6yk7j 526ca60, PR #26: use that kerbreview.py)
- Near ends (all 12 wrong): street ends where one kerb hooks across the road and stops 2-3.5 m short 338022 6247128,
  339370 6243216, 329768 6247061 (cap the end); lane mouths/corners left open 337607 6245343, 331318 6247743, 329918 6245977,
  326588 6248652 (close the corner); kerb stops mid-street 332232 6246954, 338822 6244905 (~7 m before the main road).
- Deleted not fixed: 337956 6247752 (~30 m gap in trees), 318288 6252362 (rail-side kerb missing ~29 m), 326633 6247957
  (north kerb missing), 335731 6251088 (corner open).
- Still there: 334049 6252312 strand through car park; 317965 6253355 parallel line along parking bays; 323692 6256759 jog
  across the footpath.
- Stopping short: 311109 6254692 outer bend missing; 331989 6257088 stops 15-25 m short of the junction; 327855 6248416 stub
  into the main-road intersection; V16 332861 6246448 should run up to where the bridge starts (bridges() cut 12 m too far:
  cut only the stretch alongside the bridge piece itself, not its approach); V38 313257 6252970 over grass and back fences;
  V44 331024 6246472 through parked cars into a construction site; V65 336265 6243098 curls onto the main-road kerb.

## Ideas for h
- Replace tees()/junction "cut" with "join": an end within 5 m of a kerb's middle is joined to it with a round corner (pick the
  branch direction by the street side), never left short.
- For a near end with nothing to join, extend along its block loop (kerbnet guide() with a longer reach) instead of stopping.
- bridges(): measure along the bridge segment only (project inside it), so approaches stay.
