import json, sys, numpy as np
from shapely.geometry import LineString, shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
def main(bdir):
    R = json.load(open(bdir + "/m.json")); F = json.load(open(bdir + "/osm.geojson"))["features"]
    SW = [transform(TO, shape(f["geometry"])) for f in F if f["properties"].get("footway") == "sidewalk"]
    KB = [transform(TO, shape(f["geometry"])) for f in F if f["properties"].get("barrier") == "kerb"]
    for name, G in (("s", SW), ("k", KB)):
        if not G: continue
        T = STRtree(G)
        for r in R:
            p = np.array([r["x"], r["y"]]); n = np.array([r["nx"], r["ny"]]); ray = LineString([p, p + n * 12])
            best = None
            for g in T.query(ray, predicate="intersects"):
                x = ray.intersection(G[g])
                for q in getattr(x, "geoms", [x]):
                    for c in getattr(q, "coords", []):
                        d = Point(p).distance(Point(c))
                        if d > 0.2 and (best is None or d < best): best = d
            r[name] = None if best is None else round(best, 2)
    json.dump(R, open(bdir + "/m.json", "w"))
for b in sys.argv[1:]: main(b)
