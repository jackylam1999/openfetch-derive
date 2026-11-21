"""ptsheet.py out.jpg size_m "x,y;x,y;..." overlay.json:color ... : aerial crops at MGA55 points, overlays (lon/lat geojson) drawn"""
import json, sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/w/derive/openfetch/tools/derive/kerbvic")
from mosaic import mosaic
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import shape, box
from shapely.ops import transform
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
out, sz = sys.argv[1], float(sys.argv[2]); C = [tuple(map(float, p.split(","))) for p in sys.argv[3].split(";")]
L = []
for a in sys.argv[4:]:
    fn, col = a.rsplit(":", 1); gs = []
    for f in json.load(open(fn))["features"]:
        if f["geometry"]: gs.append(transform(TO, shape(f["geometry"])))
    L.append((gs, col))
tiles = []
for k, (cx, cy) in enumerate(C):
    x0, y1 = cx - sz / 2, cy + sz / 2; bb = box(cx - sz / 2, cy - sz / 2, cx + sz / 2, cy + sz / 2)
    im = Image.fromarray(mosaic(x0, cy - sz / 2, cx + sz / 2, y1, 0.25, 19)); d = ImageDraw.Draw(im)
    for gs, col in L:
        for g in gs:
            if not g.intersects(bb): continue
            for q in getattr(g, "geoms", [g]):
                cs = q.exterior.coords if q.geom_type == "Polygon" else q.coords
                d.line([((x - x0) / .25, (y1 - y) / .25) for x, y in cs], fill=col, width=2)
    d.text((4, 4), str(k + 1), fill="yellow"); tiles.append(im.resize((360, 360)))
W = 3 if len(tiles) > 4 else 2; h = (len(tiles) + W - 1) // W; o = Image.new("RGB", (364 * W, 364 * h), "white")
for k, im in enumerate(tiles): o.paste(im, (364 * (k % W), 364 * (k // W)))
o.save(out, quality=80)
