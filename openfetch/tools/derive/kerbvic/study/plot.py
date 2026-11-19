import json, sys, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
R = sys.argv[1]; out = sys.argv[2]; bx = list(map(float, sys.argv[3:7])) if len(sys.argv) > 6 else None
RR = sys.argv[8] if len(sys.argv) > 8 else R
fig, ax = plt.subplots(figsize=(14, 14))
for f in json.load(open(R + "/lots/lots.json"))["features"]:
    c0 = f["geometry"]["coordinates"][0] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"][0][0]
    if bx and not (bx[0] - 50 < c0[0][0] < bx[2] + 50 and bx[1] - 50 < c0[0][1] < bx[3] + 50): continue
    for poly in ([f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"]):
        x, y = zip(*poly[0]); ax.fill(x, y, color="#e6e6e6", lw=0.2, ec="#bbb")
for f in json.load(open(R + "/roads/roads.json"))["features"]:
    g = f["geometry"]; fh = f["properties"]["functionhierarchy"]
    for c in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
        x, y = zip(*c); ax.plot(x, y, color={7: "#c9a", 10: "#ccc"}.get(fh, "#888"), lw=0.6, ls="--" if fh == 7 else "-")
for f in json.load(open(R + "/sidewalks.geojson"))["features"]:
    x, y = zip(*[TO(*p) for p in f["geometry"]["coordinates"]]); ax.plot(x, y, color="#6af", lw=0.6)
cols = {"side faces no street": "orange", "no footpath measure": "purple", "street too narrow for a footpath": "brown", "street centreline inside or too close": "red"}
for f in json.load(open(RR + "/why.json"))["features"]:
    x, y = zip(*[TO(*p) for p in f["geometry"]["coordinates"]]); ax.plot(x, y, color=cols.get(f["properties"]["why"], "pink"), lw=1.2)
for f in json.load(open(RR + "/rings.json"))["features"]:
    x, y = zip(*[TO(*p) for p in f["geometry"]["coordinates"]]); ax.plot(x, y, color="green", lw=1.4)
if len(sys.argv) > 7 and sys.argv[7] != "x":
    for f in json.load(open(sys.argv[7]))["features"]:
        g = f["geometry"]
        for poly in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
            x, y = zip(*[TO(*p) for p in poly[0]]); ax.plot(x, y, color="black", lw=0.3)
if bx: ax.set_xlim(bx[0], bx[2]); ax.set_ylim(bx[1], bx[3])
ax.set_aspect("equal"); ax.set_title("green kept | orange no street | purple no measure | brown narrow | red centreline | blue OSM footpaths")
plt.savefig(out, dpi=110, bbox_inches="tight")
