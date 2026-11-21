"""inbays.py rings.json osmpark.json : length of each ring running inside OSM street-side parking (polygon shrunk 1 m)"""
import json, sys, warnings; warnings.filterwarnings("ignore")
from shapely.geometry import shape, Polygon
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
P = []
for f in json.load(open(sys.argv[2]))["features"]:
    g = transform(TO, shape(f["geometry"]))
    if g.is_ring and len(g.coords) > 3:
        q = Polygon(g.coords).buffer(0)
        if q.area > 20: P.append((q, f["properties"]))
T = STRtree([p for p, _ in P]); tot = 0; hits = []
for i, f in enumerate(json.load(open(sys.argv[1]))["features"]):
    r = transform(TO, shape(f["geometry"])); r = r.exterior if r.geom_type == "Polygon" else r
    L = 0; ws = []
    for k in T.query(r):
        q = P[int(k)][0].buffer(-1.0)
        if q.is_empty: continue
        l = r.intersection(q).length
        if l > 3: L += l; c = q.centroid; ws.append(round(l, 1))
    if L > 0: hits.append((i, round(L, 1), f["properties"].get("areas"), ws, TO.__self__ if False else None)); tot += L
for h in hits: print(h[:4])
print("rings", len(hits), "m inside bays", round(tot))
