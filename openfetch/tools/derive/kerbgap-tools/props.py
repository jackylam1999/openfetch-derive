"""Join the per-square gap kerb loops into one file with the published properties (road, source, length_m, areas);
loops touching another loop are left out (as in version 2026-11-15)."""
import sys, json, glob, gzip, collections
sys.path.insert(0, sys.argv[1])
import numpy as np, shapely
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
S, out_fn, prev_fn = sys.argv[2], sys.argv[3], sys.argv[4]
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
roads = [(g, fh) for g, fh in ka.load_roads(S + "/in/roads") if fh not in ka.SKIP_FH]
RG = [g for g, _ in roads]; RF = [fh for _, fh in roads]; RT = STRtree(RG)
prev = json.load(gzip.open(prev_fn))["features"]
cell_area = collections.defaultdict(collections.Counter); road_check = []
for f in prev:
    xy = np.array([to(*c) for c in f["geometry"]["coordinates"]])
    c = xy.mean(0); cell_area[(int(c[0] // 1000), int(c[1] // 1000))][f["properties"]["areas"]] += 1
    road_check.append((LineString(xy), f["properties"]["road"]))
def road_of(g):
    P = shapely.points(np.asarray([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, max(2, int(g.length // 2)))]))
    fhs = set()
    for k in RT.query(g.buffer(15)):
        if (shapely.distance(P, RG[int(k)]) < {1: 14, 2: 11, 3: 11, 4: 8.5}.get(RF[int(k)], 9)).any():
            fhs.add(RF[int(k)])
    return "main" if fhs & {1, 2, 3, 4} else "collector" if 5 in fhs else "local"
ok = sum(road_of(g) == r for g, r in road_check[:300]); print("road class agrees with the published one on", ok, "of 300")
loops = []
for fn in sorted(glob.glob(S + "/final/[0-9]*_[0-9]*.json")):
    if fn.endswith("why.json"): continue
    cell = tuple(map(int, fn.split("/")[-1][:-5].split("_")))
    for f in json.load(open(fn))["features"]:
        cs = f["geometry"]["coordinates"]; g = LineString([to(*c) for c in cs])
        loops.append((cell, cs, g))
T = STRtree([g for _, _, g in loops]); touch = set()
for i, (_, _, g) in enumerate(loops):
    for k in T.query(g, predicate="dwithin", distance=0.5):
        if int(k) != i: touch.add(i); touch.add(int(k))
feats = []
for i, (cell, cs, g) in enumerate(loops):
    if i in touch: continue
    ar = cell_area.get(cell) or cell_area.get(min(cell_area, key=lambda c: (c[0] - cell[0]) ** 2 + (c[1] - cell[1]) ** 2))
    feats.append({"type": "Feature", "properties": {"road": road_of(g), "source": "model", "length_m": round(g.length, 1),
                  "areas": ar.most_common(1)[0][0]}, "geometry": {"type": "LineString", "coordinates": cs}})
json.dump({"type": "FeatureCollection", "features": feats}, gzip.open(out_fn, "wt"))
print("loops", len(loops), "touching left out", len(touch), "kept", len(feats), "km", round(sum(f["properties"]["length_m"] for f in feats) / 1000, 1))
