"""Leave out whole rings that kerbaudit.py marks with a kink (wobble, jog) or a fussy cap: a ring is kept whole or left blank,
never cut (review 7, 19 Nov 2026: 3 rings wobbled 1-2 m along one side).
    python3 drop_audit.py kerbs.json audit.json out.json out_mga55.geojson"""
import json, sys
from shapely.geometry import LineString, Point
from pyproj import Transformer
T = Transformer.from_crs(4326, 7855, always_xy=True).transform
d = json.load(open(sys.argv[1])); a = json.load(open(sys.argv[2]))
pts = [Point(p[0], p[1]) for p in a.get("kink_points", []) + a.get("fussy_points", [])]
keep, mf = [], []
for f in d["features"]:
    g = LineString([T(*c[:2]) for c in f["geometry"]["coordinates"]])
    if any(g.distance(p) < 1.0 for p in pts):
        continue
    keep.append(f); mf.append({"type": "Feature", "properties": f["properties"], "geometry": {"type": "LineString", "coordinates": [list(c) for c in g.coords]}})
print("left out", len(d["features"]) - len(keep), "kept", len(keep))
json.dump({"type": "FeatureCollection", "features": keep}, open(sys.argv[3], "w"))
json.dump({"type": "FeatureCollection", "features": mf}, open(sys.argv[4], "w"))
