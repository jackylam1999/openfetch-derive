"""osmbay.py osmpark.json com-kerbs.json : how well OSM street-side parking polygons' edges match council kerbs (CoM area only)"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
from shapely.geometry import shape, Polygon
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
K = [transform(TO, shape(f["geometry"])).buffer(0) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]]
KU = unary_union(K); area = KU.convex_hull.buffer(-100)
B = KU.boundary; parts = list(getattr(B, "geoms", [B])); T = STRtree(parts)
res = []
for f in json.load(open(sys.argv[1]))["features"]:
    g = transform(TO, shape(f["geometry"]))
    if not (g.is_ring and len(g.coords) > 3): continue
    p = Polygon(g.coords).buffer(0)
    if not p.within(area) or p.area < 20: continue
    b = p.exterior; d = []
    for t in np.arange(0, b.length, 1.0):
        q = b.interpolate(t); c = T.query(q.buffer(8)); d.append(min(parts[int(k)].distance(q) for k in c) if len(c) else 8)
    d = np.array(d)
    # the polygon's edge nearest a kerb along its long side: share of the perimeter within 1 m of a kerb
    res.append((f["properties"].get("parking"), f["properties"].get("parking:orientation"), p.area, np.mean(d < 1), np.mean(d < 2)))
r = np.array([[x[2], x[3], x[4]] for x in res]) if res else np.zeros((0, 3))
print("OSM street parking polygons inside the council kerb area:", len(res))
if len(res): print("median share of perimeter within 1 m of a council kerb %.2f, within 2 m %.2f; polygons with >=40%% within 1 m: %d" % (np.median(r[:, 1]), np.median(r[:, 2]), np.sum(r[:, 1] >= .4)))
