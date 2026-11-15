# Gap kerbs from version k block loops (15 Nov 2026)

Thread "Bring back our own kerbs for gaps". Jacky: "we need to bring them back to fill the gap" (where councils publish no kerbs).
Bar (Jacky 14 Nov): a little off is fine; nothing odd (across mouths/intersections, wrong-road joins, open ends, roofs, doubles).

## Method (no new tracing or training)
- `kerbgap.py`: k's block loops (build + fuse on raw LiDAR traces + roundabouts), judged ONE LOOP AT A TIME; a loop is kept whole
  or left blank, never cut, so no open end can appear. Blank when: open, small, main road side not 90 % seen (--main-seen),
  crosses a street centreline, runs >2 m inside a lot for 3 m, <70 % seen, an unseen stretch >12 m (v2), or within 6 m of an
  official kerb (--official, Parramatta council layer).
- Run per 1 km square with 250 m margin, loops kept by centroid in the square (`kerbgap-tools/runcell.sh`, cells.txt, 145 squares,
  4 at a time ~1 h; loop builds cached as .pkl so a judge change reruns in minutes).
- Inputs: project files derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz; outputs and review in project files .notes/kerb-gap/.

## Results
| | km kept | review |
|---|---|---|
| v1 | 1,376 of 3,289 | fresh 40: 2 WRONG (F13 corner across roof, F31 past a driveway); old 96: 2 WRONG (A20 drift, R22 wobble) |
| v2 (+ unseen run 12 m) | 1,029 | new fresh 40 (seed 20261116): 0 WRONG, 34 OK, 5 BLANK, 1 UNSURE (G10 lane clips roof ~1 m) |
k for comparison: 45 WRONG of 96 judged tiles under the old (stricter) bar.
Known judgement calls left in v2: F31 (driveway mouth), G10. A20, R22, F13 gone in v2.
