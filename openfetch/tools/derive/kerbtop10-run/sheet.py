"""sheet.py m.json why.json kerbs.geojson.gz cause N out_prefix [seed]
Close-ups (aerial, 140 m) of gap blocks with a given kerblot reason: yellow = block outline, blue = kerbs drawn, red = gap sides."""
import json, sys, gzip, random, io, os, urllib.request, time
import numpy as np, shapely
from shapely.geometry import shape, Point, Polygon, box
from shapely.strtree import STRtree
from pyproj import Transformer
from PIL import Image, ImageDraw
T = Transformer.from_crs(4326, 7856, always_xy=True)
M, WY, KF, CAUSE, N, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
random.seed(int(sys.argv[7]) if len(sys.argv) > 7 else 1)
cv = lambda c: np.column_stack(T.transform(np.array(c)[:, 0], np.array(c)[:, 1]))
P, why = [], []
for f in json.load(open(WY))['features']:
    P.append(Polygon(cv(f['geometry']['coordinates'])).buffer(0)); why.append(f['properties']['why'])
ST = STRtree(P)
K = [shapely.transform(shape(f['geometry']), lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1]))) for f in json.load(gzip.open(KF))['features']]
KT = STRtree(K)
G = [g for v in json.load(open(M)).values() for g in v['gaps']]
byb = {}
for g in G:
    h = ST.query(Point(g[7], g[8]), predicate='within')
    w = why[h[0]] if len(h) else 'none'
    if w == CAUSE or (CAUSE == 'none' and w == 'none'):
        byb.setdefault(int(h[0]) if len(h) else (int(g[7] // 150), int(g[8] // 150)), []).append(g)
keys = random.sample(sorted(byb, key=str), min(N, len(byb)))
PX, S = 640, 140.0


def img(cx, cy):
    x0, y0 = cx - S / 2, cy - S / 2
    u = f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+S},{y0+S}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image"
    for i in range(4):
        try:
            return Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'openfetch-derive'}), timeout=60).read())).convert('RGB')
        except Exception:
            time.sleep(2 + i)
    return Image.new('RGB', (PX, PX), (90, 90, 90))


tiles = []
for k in keys:
    gs = byb[k]; cx = float(np.median([g[0] for g in gs])); cy = float(np.median([g[1] for g in gs]))
    im = img(cx, cy); d = ImageDraw.Draw(im); x0, y0 = cx - S / 2, cy - S / 2
    px = lambda x, y: ((x - x0) / S * PX, PX - (y - y0) / S * PX)
    B = box(x0, y0, x0 + S, y0 + S)
    if isinstance(k, int):
        d.line([px(*c) for c in P[k].exterior.coords], fill=(255, 220, 0), width=2)
    for j in KT.query(B):
        for q in getattr(K[j], 'geoms', [K[j]]):
            d.line([px(*c) for c in q.coords], fill=(30, 140, 255), width=3)
    for g in G:
        if B.contains(Point(g[0], g[1])):
            a, b = px(g[0], g[1]), px(g[7], g[8]); d.line([a, b], fill=(255, 40, 40), width=1); d.ellipse([b[0] - 3, b[1] - 3, b[0] + 3, b[1] + 3], fill=(255, 40, 40))
    d.rectangle([0, 0, 260, 18], fill=(0, 0, 0)); d.text((4, 3), f"{len(tiles)+1} {int(cx)} {int(cy)} {len(gs)*5} m gap", fill=(255, 255, 255))
    tiles.append(im)
for s in range(0, len(tiles), 4):
    sh = Image.new('RGB', (PX * 2, PX * 2), (0, 0, 0))
    for i, t in enumerate(tiles[s:s + 4]):
        sh.paste(t, ((i % 2) * PX, (i // 2) * PX))
    sh.save(f'{OUT}-{s//4}.jpg', quality=85)
print(len(byb), 'blocks', len(tiles), 'tiles')
