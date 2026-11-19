"""Close-up review sheets for drafted kerb rings (REVIEW-BRIEF.md format): 2x2 tiles of NSW aerial, north up, thick magenta =
the ring judged, yellow = kerb lines already there, thin cyan = other drafted rings, white = cadastre lot lines.
    python3 ringsheet.py rings.geojson[,..] drawn.geojson.gz lots_dir out_prefix [ids.txt]
Writes out_prefix-<n>.jpg and out_prefix-index.json (sheet -> block ids)."""
import gzip, io, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np, shapely
from shapely.geometry import shape, box, LineString
from shapely.strtree import STRtree
from pyproj import Transformer
from PIL import Image, ImageDraw

T = Transformer.from_crs(4326, 7856, always_xy=True)
m = lambda g: shapely.transform(g, lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))
PX, MARGIN, S_MIN = 900, 25.0, 120.0


def img(x0, y0, S):
    u = (f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+S},{y0+S}"
         f"&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image")
    for i in range(5):
        try:
            return Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "openfetch-derive"}), timeout=90).read())).convert("RGB")
        except Exception:
            time.sleep(3 + 2 * i)
    return Image.new("RGB", (PX, PX), (90, 90, 90))


def main(a):
    R = []
    for fn in a[0].split(","):
        for f in json.load(open(fn))["features"]:
            R.append((f["properties"]["id"], m(shape(f["geometry"]))))
    if len(a) > 4:
        want = set(open(a[4]).read().split())
        R = [r for r in R if r[0] in want]
    RT = STRtree([g for _, g in R])
    D = [m(shape(f["geometry"])) for f in json.load(gzip.open(a[1], "rt"))["features"] if f.get("geometry")]
    DT = STRtree(D)
    lots = {}

    def lotsin(B):
        out = []
        x0, y0, x1, y1 = B.bounds
        for x in range(int(x0 // 1000), int(x1 // 1000) + 1):
            for y in range(int(y0 // 1000), int(y1 // 1000) + 1):
                fn = os.path.join(a[2], f"{x*1000}_{y*1000}.json")
                if fn not in lots:
                    lots[fn] = [shape(f["geometry"]) for f in json.load(open(fn))["features"]] if os.path.exists(fn) else []
                out += [g for g in lots[fn] if g.intersects(B)]
        return out

    def tile(k):
        bid, g = R[k]
        x0, y0, x1, y1 = g.bounds
        S = max(x1 - x0, y1 - y0) + 2 * MARGIN
        S = max(S, S_MIN)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        X0, Y0 = cx - S / 2, cy - S / 2
        B = box(X0, Y0, X0 + S, Y0 + S)
        im = img(X0, Y0, S)
        d = ImageDraw.Draw(im)
        px = lambda x, y: ((x - X0) / S * PX, PX - (y - Y0) / S * PX)
        for p in lotsin(B):
            for q in getattr(p, "geoms", [p]):
                if q.geom_type == "Polygon":
                    d.line([px(*c) for c in q.exterior.coords], fill=(255, 255, 255), width=1)
        for j in DT.query(B):
            for q in getattr(D[j], "geoms", [D[j]]):
                c = q.exterior.coords if q.geom_type == "Polygon" else q.coords
                d.line([px(*c) for c in c], fill=(255, 230, 0), width=3)
        for j in RT.query(B):
            if int(j) != k:
                d.line([px(*c) for c in R[int(j)][1].coords], fill=(0, 230, 255), width=2)
        d.line([px(*c) for c in g.coords], fill=(255, 0, 255), width=5)
        d.rectangle([0, 0, 260, 22], fill=(0, 0, 0))
        d.text((5, 5), f"{bid}  {int(S)} m wide", fill=(255, 255, 255))
        return im

    with ThreadPoolExecutor(4) as ex:
        tiles = list(ex.map(tile, range(len(R))))
    idx = {}
    for s in range(0, len(tiles), 4):
        sh = Image.new("RGB", (PX * 2, PX * 2), (0, 0, 0))
        for i, t in enumerate(tiles[s:s + 4]):
            sh.paste(t, ((i % 2) * PX, (i // 2) * PX))
        fn = f"{a[3]}-{s // 4}.jpg"
        sh.save(fn, quality=85)
        idx[fn] = [R[k][0] for k in range(s, min(s + 4, len(R)))]
    json.dump(idx, open(f"{a[3]}-index.json", "w"), indent=0)
    print(len(R), "rings", len(idx), "sheets")


if __name__ == "__main__":
    main(sys.argv[1:])
