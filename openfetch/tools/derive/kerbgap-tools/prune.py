"""Leave out ADDED loops (not in the last version) that raise the version gates: near a flagged audit/review spot or doubled
(twin share over TW). Old loops are never touched, so the ratchet compares like with like."""
import sys, json, gzip
sys.path.insert(0, sys.argv[1])
import numpy as np
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from pyproj import Transformer
src, prev, audit, review, out, TW = sys.argv[2:8]; TW = float(TW)
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
key = lambda f: tuple(tuple(round(v, 6) for v in c) for c in f["geometry"]["coordinates"])
new = json.load(gzip.open(src))["features"]; old = {key(f) for f in json.load(gzip.open(prev))["features"]}
G = [LineString([to(*c) for c in f["geometry"]["coordinates"]]) for f in new]; T = STRtree(G)
a = json.load(open(audit)); r = json.load(open(review))
pts = [Point(p[0], p[1]) for k in ("points", "kink_points", "fussy_points", "end_points") for p in a.get(k, [])]
pts += [Point(s["x"], s["y"]) for s in r.get("spots", [])]
drop = set()
for p in pts:
    for k in T.query(p, predicate="dwithin", distance=3.0):
        if key(new[int(k)]) not in old: drop.add(int(k))
def twin_share(i, lo=1.0, hi=4.5, step=2.0):
    g = G[i]; tot = dbl = 0
    for t in np.arange(step / 2, g.length, step):
        p = g.interpolate(t); tot += 1
        a_ = np.asarray(g.interpolate(max(t - 1, 0)).coords[0]); b_ = np.asarray(g.interpolate(min(t + 1, g.length)).coords[0]); u = b_ - a_
        if np.hypot(*u) < 1e-6: continue
        u = u / np.hypot(*u)
        for k in T.query(p.buffer(hi)):
            k = int(k)
            if k == i: continue
            gk = G[k]; d = gk.distance(p)
            if lo <= d <= hi:
                tk = gk.project(p); c = np.asarray(gk.interpolate(max(tk - 1, 0)).coords[0]); e = np.asarray(gk.interpolate(min(tk + 1, gk.length)).coords[0]); v = e - c
                if np.hypot(*v) > 1e-6 and abs(u @ v) / np.hypot(*v) > np.cos(np.radians(20)): dbl += 1; break
    return dbl / max(tot, 1)
tw = 0
for i, f in enumerate(new):
    if i not in drop and key(f) not in old and twin_share(i) > TW: drop.add(i); tw += 1
keep = [f for i, f in enumerate(new) if i not in drop]
json.dump({"type": "FeatureCollection", "features": keep}, gzip.open(out, "wt"))
print("dropped", len(drop), "(twins", tw, ") kept", len(keep), "km", round(sum(f["properties"]["length_m"] for f in keep) / 1000, 1))
