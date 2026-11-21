"""joinjudge.py out_dir com-kerbs.json : per corner join on kept rings, max ring error vs CoM kerbs near the corner, by join type"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
from shapely.geometry import shape, Point, LineString
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
o = sys.argv[1]
rings = [transform(TO, shape(f["geometry"])) for f in json.load(open(o + "/rings.json"))["features"]]
rings = [r.exterior if r.geom_type == "Polygon" else r for r in rings]; RT = STRtree(rings)
ext = unary_union(rings).envelope.buffer(60)
T = [transform(TO, shape(f["geometry"])).buffer(0) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]]
T = [g for g in T if g.intersects(ext)]; B = unary_union(T).boundary; parts = list(getattr(B, "geoms", [B])); TT = STRtree(parts)
def err(p):
    q = TT.query(p.buffer(12)); return min(parts[int(k)].distance(p) for k in q) if len(q) else 12
rows = []
for a1, b0, X, used, t in json.load(open(o + "/joins.json")):
    A, Bp = Point(a1), Point(b0)
    k = [int(i) for i in RT.query(A.buffer(1.0)) if rings[int(i)].distance(A) < 1.0 and rings[int(i)].distance(Bp) < 1.0]
    if not k: continue
    r = rings[k[0]]; ta, tb = r.project(A), r.project(Bp)
    lo, hi = sorted((ta, tb))
    seg = [r.interpolate(x) for x in (np.arange(lo, hi, 0.5) if hi - lo < r.length / 2 else np.r_[np.arange(hi, r.length, 0.5), np.arange(0, lo, 0.5)])]
    if not seg: continue
    e = [err(p) for p in seg]
    if min(e) >= 12: continue
    rows.append((used, A.distance(Bp), Point(X).distance(A), max(e), float(np.mean(e)), a1))
rows.sort(key=lambda r: -r[3])
for used in (True, False):
    R = [r for r in rows if r[0] == used]
    if R:
        mx = np.array([r[3] for r in R]); print(f"used X={used}: corners {len(R)}  max err >3m {np.sum(mx>3)}  >5m {np.sum(mx>5)}  median max {np.median(mx):.1f}")
print("worst chords:"); [print(" chord %.1f m, X %.1f m from a1, max err %.1f, mean %.1f at %s" % (r[1], r[2], r[3], r[4], [round(v) for v in r[5]])) for r in rows if not r[0]][:8]
print("worst X:"); [print(" chord %.1f m, X %.1f m, max err %.1f, mean %.1f at %s" % (r[1], r[2], r[3], r[4], [round(v) for v in r[5]])) for r in rows if r[0]][:5]
