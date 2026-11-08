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
