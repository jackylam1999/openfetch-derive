import json, sys, numpy as np
from shapely.geometry import LineString, shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
for b in sys.argv[1:]:
    R = json.load(open(b + "/m.json")); F = json.load(open(b + "/osm.geojson"))["features"]
    G = [transform(TO, shape(f["geometry"])) for f in F if f["properties"].get("footway") == "sidewalk"]; T = STRtree(G)
    for r in R:
        r["sf"] = None
        if not r["w"] or r["w"] > 69: continue
        p = np.array([r["x"], r["y"]]); n = np.array([r["nx"], r["ny"]]); ray = LineString([p, p + n * (r["w"] - 0.5)])
        best = None
        for g in T.query(ray, predicate="intersects"):
            x = ray.intersection(G[g])
            for q in getattr(x, "geoms", [x]):
                for c in getattr(q, "coords", []):
                    d = Point(p).distance(Point(c))
                    if d > 0.65 * r["w"] and (best is None or d > best): best = d
        r["sf"] = None if best is None else round(r["w"] - best, 2)
    json.dump(R, open(b + "/m.json", "w"))
