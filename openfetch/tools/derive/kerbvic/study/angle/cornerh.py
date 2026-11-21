"""cornerh.py joins.json com-kerbs.json : for joins that fell back to a chord, max distance to council kerb along chord vs along a1-X-b0"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
from shapely.geometry import shape, LineString, Point
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
J = json.load(open(sys.argv[1])); pts = np.array([j[0] for j in J]); lo, hi = pts.min(0) - 60, pts.max(0) + 60
K = []
for f in json.load(open(sys.argv[2]))["features"]:
    if f["geometry"]:
        g = transform(TO, shape(f["geometry"])); b = g.bounds
        if b[0] < hi[0] and b[2] > lo[0] and b[1] < hi[1] and b[3] > lo[1]: K.append(g.buffer(0))
B = unary_union(K).boundary; parts = list(getattr(B, "geoms", [B])); T = STRtree(parts)
def e(line):
    out = []
    for t in np.arange(0, line.length + .01, .5):
        p = line.interpolate(t); q = T.query(p.buffer(15)); out.append(min(parts[int(k)].distance(p) for k in q) if len(q) else 15)
    return max(out)
seen = set()
for a1, b0, X, used, t in J:
    key = (round(a1[0]), round(a1[1]))
    if used or key in seen or np.hypot(a1[0] - b0[0], a1[1] - b0[1]) < 4: continue
    seen.add(key)
    ch = LineString([a1, b0]); ec = e(ch)
    if ec >= 15: continue
    dx = np.hypot(X[0] - a1[0], X[1] - a1[1]); ex = e(LineString([a1, X, b0])) if dx < 40 else np.nan
    print("corner at %s chord %.1f m: chord err %.1f | X %.1f m away, a1-X-b0 err %s" % (key, ch.length, ec, dx, "%.1f" % ex if np.isfinite(ex) else "-"))
