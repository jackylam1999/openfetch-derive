"""fresh.py roads_dir traced.json official.json n seed out.json : n fresh random places on local streets (fh 5-7, on the ground),
inside the traced area, more than 60 m from any official kerb line, more than 150 m apart, chosen by street length."""
import json, sys, random
sys.path.insert(0, sys.argv[7] if len(sys.argv) > 7 else ".")
import numpy as np
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka

roads_dir, traced, official, n, seed, out = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
area = ka.traced_area(ka.Kerbs(ka.read_kerbs(traced))).buffer(-80)
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
O = []
for f in json.load(open(official))["features"]:
    g = f.get("geometry") or {}
    parts = g.get("coordinates", []) if g.get("type") == "MultiLineString" else [g.get("coordinates", [])]
    O += [LineString([to(*c[:2]) for c in p]) for p in parts if len(p) > 1]
OT = STRtree(O)
loc = [g for g, fh in ka.load_roads(roads_dir) if fh in (5, 6, 7) and area.intersects(g)]
L = np.cumsum([g.length for g in loc])
rng = random.Random(seed); P = []
while len(P) < n:
    t = rng.uniform(0, L[-1]); i = int(np.searchsorted(L, t)); g = loc[i]
    p = g.interpolate(t - (L[i - 1] if i else 0))
    if not area.contains(p) or len(OT.query(p, predicate="dwithin", distance=60)):
        continue
    if any(p.distance(q) < 150 for q in P):
        continue
    P.append(p)
json.dump([{"id": f"F{i+1}", "x": round(p.x, 1), "y": round(p.y, 1)} for i, p in enumerate(P)], open(out, "w"))
print(len(P))
