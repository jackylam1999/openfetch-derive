# Kerbs version i (8 Nov 2026)

Thread "Fix local-street kerbs for version i". Code: openfetch-derive branch claude/project-thread-nq5zda (PR #27, on ahcwqk 017d79a).
Files: /mnt/project-files/.notes/kerb-i/ (kerbs-nsw-i.json.gz, reviewer/review.json + review-sheet.jpg, sneak-peek images).

## How to run
- Full: `kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --local-only --dump-g g.pkl` (~25 min, 1 core) on
  derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz. The dump now holds TUNNELS, level, LOCAL_BRIDGES and the traced pieces.
- Fast loop (new): `kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --local-only --from-g g.pkl` reruns only
  kerbg.clean on the dumped network and writes the normal output (~10 min). The g.pkl of this run is in .notes/kerb-i/ if kept.
- Debug: KERBG_TRACE=1 prints line and near-end counts after every kerbg step; KERBG_WATCH="x,y" prints the line ends within 8 m
  of a point after every step (finds which step opened a gap); KERBG_SIDES_DBG=1 prints sides() per street.
- kerbg.clean is now a list of named steps (clean() in kerbg.py), so a step can be moved or repeated in one line.

## What changed from h (tools/derive/kerbg.py, kerbnet.py)
- sides() (new, the main one): every local street (fh 5-7) is walked both sides every 2 m with rays; where a side has no kerb for
  12 m+ and no cross street is in the way, a kerb is drawn at that side's own offset nearby (30 m), else the other side's (15 m),
  else (nothing drawn either side) at the property line less the street class's verge measured in the same run (fh 5/6 ~3.8 m,
  fh 7 ~0.9 m). Never within 3.5 m of a kerb, nearer than 2.2 m to the centreline, on a main road band or in a lot. 2,819 pieces,
  176 km. Fixes "one side missing" (h tile 18) and "whole street deleted" (h tiles 21, 22).
- on_centre(): a line lying on a centreline (within 1.5 m for 10 m+) is not a kerb (29 km, mostly drawn by h's extend walking
  0.5-1 m off a centreline). extend's lowest offset raised 0.5 -> 1.3 m.
- Short local bridges (fh 5-7, roadontype 2, <= 45 m): kept as streets in kerbg, not cut beside, never stop a walk or a join
  (kerbs carry on over them and under them). Long bridges only stop a walk when they run along the street (an overpass does not).
- main_tails() + a 'main' stop in the walk: a stretch whose nearest street is a main road (fh 1-4) within its band goes again
  after the walks (h V41, V65, V78).
- end_hooks(): 2 m hooks at the traced-area edge (1 km cell lines) taken off, so the walk carries those ends on.
- folds() on rings: a narrow spur (legs < 3 m, up to 120 m) is cut off and the ring closed across its mouth (h V80 lane cap).
- caps(dead=False) "lane caps": the two kerbs of a narrow street stopping side by side (2.7-8 m, centreline between) get a cap,
  staggered ends too (h V69); up to 100 deg apart when under 4.5 m (h V82 lane mouth).
- corner_join: a 2.5-4 m step between two facing ends is an S curve (h V81 type); a join that comes back onto its own line is
  split into the island ring and the kerb running on (h V87); short local bridges never block it.
- flare(): a cross street on a bridge is a mouth too.
- near_ends(): last pass, an end 1-5 m from a kerb runs straight onto it (square) or is taken back up to 8 m.
- "short" before the last joins (a stub about to go held an end shut), ring_shut (a block loop left < 3 m open is closed, also
  after ringseat), despike (mm vertices / turn-backs that read as self-touches).

## Result
Geometry (kerbreview check, --roads, --prev h): cross/poke/self/fold/dup/inside/beside/merge/gap/loop all 0; near 125
(0.041/km, cap 0.05). h: near 177, fold 7, gap 5, beside 1, V69 back. 3,023 km, 6,409 lines (h 2,895 km).
Visual: sent to the reviewer thread "Automate kerb quality review" (see STATUS.txt in .notes/kerb-i/).

## Left for j
- Lanes: kerbs in narrow lanes (under 5 m) are the main source of near ends; many lanes have no kerbs in reality.
- V38 (313257 6252970): a fh 6 centreline over grass; a kerb drawn along a street that is not built. Needs imagery or lot data.
- sides() uses the property line where nothing is drawn: check those streets on the sheet (verge per class, not per street).
- 'near' counter in KERBG_TRACE counts ring seams until ringseat; only the final number matters.

## Reviewer verdict (8 Nov 17:27Z)
FAIL but beats h: 27/53 tiles wrong (h, same whole-tile scoring: 34/53). Files .notes/kerb-i/reviewer-independent/ (verdicts.json,
review.json); cases on derive v6yk7j bc988c5. Patterns for j, worst first:
- Missing kerbs elsewhere in the tile (most near tiles): one side or arm missing 329653 6246421, 330991 6246824, 334071 6250599,
  332031 6248097, 329743 6247336, service lane 337607 6245343; V32 324946 6249886 west arm; V39 314096 6254182 car-park east kerb.
- Square-ended gaps: ~20 m at 336526 6253983 (median nose open), lane 333122 6251979, ~5 m driveway 315698 6255909.
- Open ends/stubs: 306565 6188642 (into roof), 334859 6249767, 329918 6245977.
- False lines: depot forecourt 317465 6256715, roof 306379 6188602, V38 grass, V42 323465 6255283 into yards, V77 311109 6254692
  down a cul-de-sac bulb middle.
- Main-road leftovers to remove: V29, V41 (motorway), V43 (slip loop), V65 (across intersection), V78 (past stop line).
- V33 323862 6256010: local roundabout island not drawn.
- J4: given coordinate is a pale strip with no centreline; coordinator asking Jacky which line.
