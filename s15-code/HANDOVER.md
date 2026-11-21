# Scenario 15 handover (21 Nov 2026, closed after part 2): kerbs at slip lanes and cut corners
Reports to kerb lead 5. Lab log with every number: LAB.md (Rounds 1-9). Code: derive branch claude/project-thread-ds2uju (s15-code/, labels.py h6.py h6b.py h7.py h8.py h8score.py; older scratch on claude/project-thread-jr0rwr). Nothing cut, published or deployed; no openfetch file changed; case P-0243 stays open.
## Result
Nine hypotheses, none separates the odd corners (labels: 7-9 odd, 200+ OK, labels-grown.json):
H1 island faces, H2 lot distance, H3 aerial asphalt, H4 LiDAR kerb step, H5 distance to own centreline, H6 junction + lot vertex/edge/angle, H7 rebuilt return (our corners are fixed 4 m fillets, no shape signal), H8 road-edge walk, (b) build only with both arms verified (removes 57 % of OK corners, catches 0 odd).
Root cause (by looking): the arm or kink sits on the cadastre (frontage kink, strip parcel, angled lot corner), 10-20 m long and within the road-edge noise (arms measure 1-1.7 m from the walked edge); no measure of it separates from good corners.
## Known limit
Corner faults of 10-20 m are not detectable by any test tried; whole-file review sheets catch them. H8 (road-edge walk on LiDAR intensity, 20 m window medians, run of 3 windows over 3 m) is a COARSE whole-line screen: known answer 2 % false on OK lines, 57-87 % found at 3-5 m toward the road; on labels 5.6 % of OK crops flagged, 3 of 8 S11 whole lines (2818, 2376, 2950). Disputed labels (walk says fine, eye said odd): 2799 (angle-parking bays are the kerb), 2545, 2847, 2608.
## Lessons
- Tried a corner-shape test; failed because our own corners are built fillets of one radius, so shape carries no signal. Check how a line was built before measuring its shape.
- Tried a 40 m rule on 10-20 m faults; failed by design. Match the run length to the fault length before scoring.
- Per-2 m road-edge offsets are too noisy (0-5 % recall at 5 m); use 20 m window medians (57-87 %).
- Whole-line "odd" labels need a second look before they score a detector: 2799 was a good kerb.
- Untested: first-kerb-rise half of the canopy H5 (needs ground grids, 440 MB), official kerb within 3 m as arm proof (only Parramatta/CBC files), more LiDAR for tile 335_6243 (Eastgardens).
