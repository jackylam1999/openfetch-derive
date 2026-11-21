"""baywhy.py out_dir bays.geojson : blocks within 14 m of CoM angle-bay points: kept vs why-refused, with metres of angle frontage"""
import json, sys, warnings, collections, numpy as np; warnings.filterwarnings("ignore")
from shapely.geometry import shape, Point, Polygon
from shapely.ops import transform
from scipy.spatial import cKDTree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
bp = np.array([TO(*f["geometry"]["coordinates"]) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]])
dd, _ = cKDTree(bp).query(bp, 2); ang = bp[dd[:, 1] < 3.3]; ka = cKDTree(ang)
c = collections.Counter(); m = collections.Counter(); ex = collections.defaultdict(list)
for fn, key in ((f"{sys.argv[1]}/why.json", "why"), (f"{sys.argv[1]}/rings.json", None)):
    for f in json.load(open(fn))["features"]:
        g = transform(TO, shape(f["geometry"])); g = g.exterior if g.geom_type == "Polygon" else g
        n = len(ka.query_ball_point(np.array([[p.x, p.y] for p in [g.interpolate(t) for t in np.arange(0, g.length, 2.0)]]), 14).sum() if False else 0) if False else 0
        pts = np.array([g.interpolate(t).coords[0] for t in np.arange(0, g.length, 2.0)])
        near = ka.query(pts)[0] < 14
        if near.sum() < 5: continue
        w = f["properties"][key] if key else "kept"; c[w] += 1; m[w] += 2 * int(near.sum()); ex[w].append(f["properties"].get("id"))
for w, k in c.most_common(): print(f"{w:40s} blocks {k:3d}  angle frontage m {m[w]}", ex[w][:4])
