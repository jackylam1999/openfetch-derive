import json, sys, numpy as np
from shapely.geometry import shape, LineString, Point, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
rings = [transform(TO, shape(f["geometry"])) for f in json.load(open(sys.argv[1]))["features"]]
ext = unary_union(rings).envelope.buffer(60)
T = []
for p in sys.argv[2:]:
    for f in json.load(open(p))["features"]:
        if f["geometry"]:
            g = transform(TO, shape(f["geometry"]))
            if g.intersects(ext): T.append(g.buffer(0))
U = unary_union(T); B = U.boundary; parts = list(getattr(B, "geoms", [B])); TT = STRtree(parts)
D = []; per = []; skip = 0
for r in rings:
    pts = [r.interpolate(t) for t in np.arange(0, r.length, 1.0)]
    d = np.array([min(parts[int(k)].distance(p) for k in TT.query(p.buffer(10))) if len(TT.query(p.buffer(10))) else 10 for p in pts])
    if np.mean(d < 8) < 0.8: skip += 1; continue
    D += d.tolist(); per.append((np.mean(d < 1), np.mean(d > 3)))
D = np.array(D)
print(f"rings {len(rings)} km {len(D)/1000:.1f}  <0.5m {np.mean(D<.5):.2f} <1m {np.mean(D<1):.2f} <2m {np.mean(D<2):.2f} >3m {np.mean(D>3):.3f}")
print("outside truth", skip); print("rings with >10% over 3 m:", sum(b > .1 for a, b in per))
