KN25 findings (scratch, 20 Nov). Inputs: -h file, NSW lots+roads for all 317 cells (fetched), labels.json (kn19, 279 labelled spots).
Cases on aerial (a_waterloo.jpg, a_eastgardens.jpg, a_kogarah.jpg, Z19/20):
- Eastgardens line 1266 (505 m): a ~30 m stretch at 328-360 m runs across the slip-lane carriageway diagonally; centreline distance 4.6-8 m, angle to road 30-45 deg for only 2-4 m.
- Kogarah line 2261 (543 m): 4.5 m from the centreline along its whole run, parallel (0 deg), sharp corner at 178 m; the aerial road bends away from the straight centreline, the line ends up ~12 m off the visible road (cadastre says it is outside all lots).
- Waterloo: line follows a slip-road inner edge and cuts the bend.
Signals tried, none flags the cases:
1 diagonal run (>=25 deg to every road within 12 m and lot edge within 6 m, >=6 m long): 0 runs on Eastgardens and Kogarah.
2 constant offset from centreline (+-0.15 m over 60 m): 2,115 of 3,282 lines (peak at 4.5 m = assumed width); not selective.
3 inside a lot: Kogarah and Eastgardens never inside a lot.
4 crossing a road centreline (fh<=7): 147 lines, neither case among them.
5 distance to nearest lot: Kogarah 6.5 m, same as ordinary lines.
