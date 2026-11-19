import json, io, urllib.request, time, glob, numpy as np, shapely
from shapely.geometry import shape, box
from pyproj import Transformer
from PIL import Image, ImageDraw
T = Transformer.from_crs(4326, 7856, always_xy=True)
m = lambda g: shapely.transform(g, lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))
K = [m(shape(f['geometry'])) for f in json.load(open('v19/kerbs-nsw.json'))['features']]
PX, S = 900, 120.0
def img(x0, y0):
    u = f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+S},{y0+S}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image"
    for i in range(4):
        try: return Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'openfetch-derive'}), timeout=60).read())).convert('RGB')
        except Exception: time.sleep(2 + i)
    return Image.new('RGB', (PX, PX), (90, 90, 90))
tiles = []
for n, (cx, cy) in enumerate([(326274, 6239878), (326246, 6238991), (336640, 6255289), (324600, 6249885)], 1):
    x0, y0 = cx - S / 2, cy - S / 2; B = box(x0, y0, x0 + S, y0 + S); im = img(x0, y0); d = ImageDraw.Draw(im)
    px = lambda x, y: ((x - x0) / S * PX, PX - (y - y0) / S * PX)
    for fn in glob.glob(f'in/lots/{int(cx//1000)*1000}_{int(cy//1000)*1000}.json'):
        for f in json.load(open(fn))['features']:
            g = shape(f['geometry'])
            for p in getattr(g, 'geoms', [g]):
                if p.geom_type == 'Polygon' and p.intersects(B): d.line([px(*c) for c in p.exterior.coords], fill=(255, 255, 255), width=1)
    for fn in glob.glob(f'in/roads/{int(cx//1000)*1000}_{int(cy//1000)*1000}.json'):
        for f in json.load(open(fn))['features']:
            g = shape(f['geometry'])
            for p in getattr(g, 'geoms', [g]):
                if p.intersects(B): d.line([px(*c) for c in p.coords], fill=(255, 220, 0), width=2)
    for g in K:
        if g.intersects(B): d.line([px(*c) for c in g.coords], fill=(0, 230, 255), width=4)
    r = PX / 2; d.ellipse([r - 12, r - 12, r + 12, r + 12], outline=(255, 0, 255), width=3)
    d.rectangle([0, 0, 200, 20], fill=(0, 0, 0)); d.text((4, 4), f"{n}  {cx} {cy}  120 m", fill=(255, 255, 255)); tiles.append(im)
sh = Image.new('RGB', (PX * 4, PX)); [sh.paste(t, (i * PX, 0)) for i, t in enumerate(tiles)]; sh.save('v19/close/close4.jpg', quality=88)
