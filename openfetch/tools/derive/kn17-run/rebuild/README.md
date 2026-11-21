# KN17 rebuild (21 Nov 2026, terrace card S14): exact command chain, reproduces kn17/rings-new-bar (489 identical rings)
K = work folder with cells.txt (datum/cells-kn13-21-40.txt). Fetch: fetchplain.py (plain layers, ONLY for reproducing KN17; true runs use
.notes/kerb-top10/datum inputs), bldall.py (b/bld), kerbtop10-run/fetchcad.py (in/cad, multiCRS), kerbtop10-run/zonefetch.py (in/zones, plus
edge cells kerbguard names), council kerbs: plain run official.py + offall.py (as KN17, unshifted); true runs kerbtruth.py fetch (registry datum;
Parramatta and Canterbury-Bankstown shifted, Woollahra none, Liverpool refused). Traced raw: derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz.
Drawn = nsw-2026-11-20-d kerbs-nsw.geojson.gz + council lines: final/0_0.json + final/1_1.json (kerbgrid), drawn.geojson.gz (kerblot).
Run: K=... bash pipe.sh <inputs root with in/lots in/roads> <out dir> <KR_AGREE 3.0|2.0> <"" plain | "-true">
= kerbgrid --review --road igrids per cell (3x3 inputs), kerblot --road --cad (NO --ground: KN17 had none; with kn13 ggrids 237 rings not 59),
kn17-run/comb.py (join + building gate), kerbguard --official --zones --drop, kerbface --drop. cmp.py compares two ring files.
Plain 3.0: kerbgrid 749, kerblot 59 (39.4 km), joined 623 (372.0 km), guard drops 56, kerbface 489 (313.7 km) = KN17.
