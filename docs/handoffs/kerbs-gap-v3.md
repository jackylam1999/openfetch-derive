# Gap kerbs version 2026-11-15-b: more CBD coverage (15 Nov 2026)

Thread "Fix missing kerbs around George St". Jacky: George St box in the Sydney CBD had kerbs on only a few blocks. Cause: no
council or state kerbs there (City of Sydney publishes none), so only OpenFetch gap kerbs draw; kerbgap.py v2 blanked most CBD
blocks because the LiDAR loses the kerb step under awnings, buses and parked cars (unseen run > 12 m, main-road side < 90 % seen)
and because rear-lane mouths count as street crossings.
Jacky's bar (15 Nov 09:33Z): fill as much as possible; a few metres off is fine; fail only odd lines (across intersections,
weird turns onto the wrong kerb).

## What changed (kerbgap.py flags, see its docstring)
`--bridge --lane-mouth --loose --split` on version k loops (run: kerbgap-tools/runcell-v3.sh, cells.txt; join: props.py).
- First try (unseen runs up to 60 m even when bending): CBD 221 blocks but Jacky marked 3 merges across streets + 1 bump.
  All four were bending guessed stretches; straight-only bridging drops all four. KG_RUN 25 and 40 brought them back.
- Result: 1,219 km, 2,284 loops (2026-11-15: 1,022 km, 1,914); CBD six squares 150 -> 193 blocks (47 -> 62 km).
- Independent reviewer, 40 fresh places on new lines only (seed 20261117, 70 m + 160 m tiles): 40 OK, 0 WRONG, 0 UNSURE.

## Lessons
- Show the owner a before/after picture of a loosened gate before the full run: his 4 marks found the failure class in minutes.
- A guessed stretch is safe only when straight; bending guesses are where merges and bumps come from.
- Judging is cheap once loop builds are cached (.pkl): 145 squares build ~3.5 h on 4 cores, re-judge ~40 min.
