# Kerbs version h (8 Nov 2026)

Thread "Fix local-street kerbs for version h". Code: openfetch-derive branch claude/project-thread-ahcwqk (on vvxu3s b18dc9f).
Files: /mnt/project-files/.notes/kerb-h/ (kerbs-nsw-h.geojson.gz, reviewer/review.json + review-sheet.jpg, kerbnet-stats.txt).

## What changed from g (tools/derive/kerbg.py, all in clean())
Lesson from g was "deleted, not fixed", so h redraws instead of cutting:
- unroad(): a free end lying in a cross street's carriageway (run on into a junction or across a main road) is taken back to
  that street's kerb line (439 ends, 1.4 km).
- extend(): every free end is carried on along its street at its own offset (step 1 m, up to 150 m, 3 passes) until it meets a
  kerb (joined), a cross street, a dead end, a bridge or a sharp turn. Stops when a kerb runs alongside on the same side (and
  meets that kerb with an S curve if its free end is ahead) or when any kerb is within 2.2 m (a footway or median). One end per
  stretch per pass (no two ends drawing the same gap). 6,273 ends, 181 km added.
- close_near(): a free end within 6 m of a kerb (or 10 m straight ahead) is closed onto it with a short curve: end to end when
  that kerb's free end is within 3 m, else a T onto its side (only at 35 deg or squarer). Never across a street unless it
  ends there, never across a kerb. Replaces tees() and hooks() (both only cut).
- flare(): a lane kerb stopping at the mouth onto a cross street gets its corner (a quarter circle, 2-4 m) turning away from the
  lane; it ends on the cross street's kerb if it meets one.
- junctions(): a square T (35 deg+) is kept, only a sliding Y is cut back.
- bridges(): bridges only (tunnels no longer), and only beside the bridge piece itself (V16: approaches stay).
- kerbnet.py: `--dump-g file` pickles the network before kerbg (fast loop: ~6 min clean-only runs instead of 30 min).

## Result (full run, 2,895 km, 5,859 lines)
Geometry FAIL: near 177 (0.061/km, cap 0.05; g had 624), fold 7, gap 5, beside 1, case V69 back (337612 6245342 lane end);
cross/dup/merge/self/inside 0. Visual: sent to the reviewer thread.

## Left for i
- near: ~100 ends in lanes under 5 m wide, where any end is within 5 m of the kerb across; most stop because their offset is
  under 0.5 m from the centreline, at a dead end whose centreline stops short, or at a bridge. Ideas: cap lane ends whose
  centreline ends within 15 m; for bridges, draw local-street kerbs over short rail bridges (the 5 gaps are kerbs broken at
  rail bridges, 19-29 m).
- fold: 7 spots (305743 6188140, 338603 6245736, 338833-338880 6245770).
- Still there from g's list: 334049 6252312 car park strand, 317965 6253355 parking-bay line, 313257 6252970 over grass.

## Visual result (reviewer 8 Nov 12:54Z): FAIL 18 of 51 wrong (f 20/47, g 26/48) -> improved, loop goes on to i
Verdicts in /mnt/project-files/.notes/kerb-h/reviewer-independent/; new cases on derive v6yk7j 3615cf1 (PR #26).
Fix list for i (EPSG 7856):
- folds: 338833 6245777 square cap mid-lane where the lane goes on; 338603 6245736 dead end closed as a needle spike;
  305753 6188128 thin median outline pinching into a crossing.
- gaps: ~5 m at 315847 6255694 and 334515 6249845; 317461 6249752 south kerb missing over a bridge for 19 m while the north
  is drawn (treat both sides the same: draw both over short local bridges).
- junctions: 331442 6247583 stubs + three bunched ends; 330991 6246824 lane west kerb stub, mouth corner open; V69 337607
  6245343 inner kerb stops beside the outer tail; 329918 6245977 two lines touch at the lane mouth.
- deleted again: 338022 6247128 whole visible street has no kerbs (redraw, don't drop).
- one side only: 316180 6255861 east kerb missing.
- main-road leftovers: V41 333980 6251790 zigzag on motorway; V65 336265 6243098 line along arterial kerb; V78 327854
  6248416 side-street kerbs run past the mouth as stubs into the main road.
- 313257 6252970 (old V38, ~5 m off): line through trees and front yards.
- also (tile whys 30, 44, 45, 51): side-street kerb pokes ~10 m into a main road; ramp lines end as a stub; kerbs stop
  20-35 m before a junction.
