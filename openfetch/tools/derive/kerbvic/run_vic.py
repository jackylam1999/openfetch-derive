"""kerblot.py with Victoria's settings: GDA2020 MGA zone 55, inner-Melbourne street widths (1.5 to 3 chain reserves, 30-60 m, so a
street's centreline can lie up to 31 m from the lot front and a front looks 70 m across), OSM footpath lines and, where a council ground model is cached in prep_dir/dem, its gutters as the width measures
and no borrowed widths (Vic width study 18 Nov 2026: a width borrowed from the same street was over 3 m off on 60-80 % of sides).
    python3 run_vic.py prep_dir out_dir      (prep_dir from prep_vic.py)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kerblot as kl
kl.EPSG, kl.C_MAX, kl.RAY, kl.NARROW_JOIN_FH, kl.SHORT_SIDE, kl.MITRE, kl.SAME_STREET_SPREAD = 7855, 31.0, 70.0, (6,), 30.0, True, 1.0
p, o = sys.argv[1], sys.argv[2]
if os.path.isdir(f"{p}/dem"):
    import mbdem
    kl.GUTTER = mbdem.Dem(f"{p}/dem")
os.makedirs(o, exist_ok=True)
kl.main([f"{p}/lots", f"{p}/roads", f"{p}/empty.geojson", f"{p}/empty.geojson", f"{p}/bld", f"{p}/cells.txt", f"{o}/rings.json",
         "--why", f"{o}/why.json", "--sidewalks", f"{p}/sidewalks.geojson", "--no-borrow", "--nomeasure", f"{o}/nomeasure.json"] + sys.argv[3:])
