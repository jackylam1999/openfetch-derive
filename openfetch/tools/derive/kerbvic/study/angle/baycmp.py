"""baycmp.py rings.json com-kerbs.json bays.geojson : ring error vs CoM kerbs, split by angle-bay stretches (CoM bay points <3.3 m apart)"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
from shapely.geometry import shape, Point
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from scipy.spatial import cKDTree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
rings = [transform(TO, shape(f["geometry"])) for f in json.load(open(sys.argv[1]))["features"]]
ext = unary_union(rings).envelope.buffer(60)
T = [transform(TO, shape(f["geometry"])).buffer(0) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]]
T = [g for g in T if g.intersects(ext)]; B = unary_union(T).boundary; parts = list(getattr(B, "geoms", [B])); TT = STRtree(parts)
bp = np.array([TO(*f["geometry"]["coordinates"]) for f in json.load(open(sys.argv[3]))["features"] if f["geometry"]])
kd = cKDTree(bp); dd, _ = kd.query(bp, 2); ang = bp[dd[:, 1] < 3.3]; par = bp[dd[:, 1] >= 3.3]
ka, kp = cKDTree(ang), cKDTree(par)
res = {"angle": [], "parallel": [], "none": []}; perr = []
for ri, r in enumerate(rings):
    r = r.exterior if r.geom_type == "Polygon" else r
    for t in np.arange(0, r.length, 1.0):
        p = r.interpolate(t); q = TT.query(p.buffer(10))
        d = min(parts[int(k)].distance(p) for k in q) if len(q) else 10
        if d >= 8: continue
        c = "angle" if ka.query([p.x, p.y])[0] < 9 else ("parallel" if kp.query([p.x, p.y])[0] < 9 else "none")
        res[c].append(d)
        if c == "angle": perr.append((ri, round(p.x), round(p.y), round(d, 1)))
for k, v in res.items():
    v = np.array(v)
    if len(v): print(f"{k:9s} m {len(v):5d} <1m {np.mean(v<1):.2f} <2m {np.mean(v<2):.2f} >3m {np.mean(v>3):.3f}")
print("angle bay points in box", int(sum(ext.contains(Point(*a)) for a in ang)))
json.dump(perr, open(sys.argv[4], "w")) if len(sys.argv) > 4 else None
