"""sheet.py kept.json(lon/lat) places.json out_prefix : 70 m tiles on the NSW aerial, our kerbs cyan, 12 tiles per sheet.
places.json = [{"id": "A1", "x": .., "y": ..}, ...] in EPSG 7856. Writes out_prefix-1.png ... and out_prefix-index.json."""
import io, json, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from shapely.geometry import LineString, box
from shapely.strtree import STRtree

kept, places, pre = sys.argv[1:4]
M, PX = 70.0, 420
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
L = [LineString([to(*c) for c in f["geometry"]["coordinates"]]) for f in json.load(open(kept))["features"]]
T = STRtree(L)
P = json.load(open(places))
font = ImageFont.load_default(size=22) if hasattr(ImageFont, "load_default") else None


def tile(p):
    x0, y0 = p["x"] - M / 2, p["y"] - M / 2
    u = ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?"
         f"bbox={x0},{y0},{x0+M},{y0+M}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image")
    for t in range(5):
        try:
            im = Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=120).read())).convert("RGB"); break
        except Exception:
            import time; time.sleep(5 * (t + 1))
    else:
        im = Image.new("RGB", (PX, PX), (90, 90, 90))
    d = ImageDraw.Draw(im); s = PX / M
    q = lambda x, y: ((x - x0) * s, (y0 + M - y) * s)
    n = 0
    for k in T.query(box(x0, y0, x0 + M, y0 + M)):
        d.line([q(*c) for c in L[int(k)].coords], fill=(0, 255, 255), width=3); n += 1
    d.rectangle([0, 0, 70, 30], fill=(0, 0, 0)); d.text((5, 3), p["id"], fill=(255, 255, 255), font=font)
    return im, n


idx = []
for s in range(0, len(P), 12):
    sh = Image.new("RGB", (PX * 4 + 30, PX * 3 + 20), (255, 255, 255))
    for i, p in enumerate(P[s:s + 12]):
        im, n = tile(p)
        sh.paste(im, ((i % 4) * (PX + 10), (i // 4) * (PX + 10)))
        idx.append({**p, "sheet": s // 12 + 1, "drawn": n > 0})
    sh.save(f"{pre}-{s // 12 + 1}.png")
json.dump(idx, open(f"{pre}-index.json", "w"))
print(len(idx), "tiles,", sum(1 for t in idx if t["drawn"]), "with kerbs drawn")
