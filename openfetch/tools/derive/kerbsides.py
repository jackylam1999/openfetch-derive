"""Close-ups of kerblot ring sides whose footpath width was borrowed from elsewhere on the street (nothing measured on this
stretch): is a road built here at all? 18 Nov 2026: 21 of 206 such rings ran along unbuilt mapped streets, tram corridors or tree
strips, and the three earlier looks had passed them. Every borrowed side gets this look before a version is built.

    python3 kerbsides.py rings.json roads_dir out_dir      -> out_dir/sheet-NNN.jpg (4 tiles each) + index.json [tile, ring, side, how, width]
A reviewer reads the sheets with the brief in out_dir/BRIEF.md (ROAD / NO ROAD / PART / CANT TELL); any NO ROAD or PART ring is left out."""
import json, sys, os, glob, time, urllib.request, numpy as np, shapely
from pyproj import Transformer
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, LineString, shape, MultiPoint
from shapely.strtree import STRtree
from concurrent.futures import ThreadPoolExecutor
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
F = json.load(open(sys.argv[1]))['features']; out = sys.argv[3]; PX = 600
BORROW = ('lidar same street', 'kerbs same street')
R, RN = [], []
for fn in glob.glob(os.path.join(sys.argv[2], '*.json')):
    for f in json.load(open(fn))['features']:
        if f.get('geometry'):
            g = shape(f['geometry'])
            for q in getattr(g, 'geoms', [g]):
                if q.geom_type == 'LineString': R.append(q); RN.append(f['properties'].get('roadnameoid'))
RT = STRtree(R)
jobs = []
for f in F:
    ring = Polygon([to(*c[:2]) for c in f['geometry']['coordinates']]).exterior
    pts = np.asarray([ring.interpolate(t).coords[0] for t in np.arange(0, ring.length, 2.0)]); P = shapely.points(pts)
    cand = [int(k) for k in RT.query(ring.buffer(20))]
    if not cand: continue
    dist = np.stack([shapely.distance(P, R[k]) for k in cand]); near = np.asarray(cand)[dist.argmin(0)]
    for key, (v, how) in f['properties']['d'].items():
        if how not in BORROW: continue
        nm = int(key.split(':')[0])
        m = np.asarray([RN[k] == nm for k in near]) & (dist.min(0) < 20)
        if m.sum() < 3: continue
        part = MultiPoint(pts[m]); jobs.append((f['properties']['id'], key, how, v, ring, pts[m], part))
print(len(jobs), 'sides')
os.makedirs(os.path.join(out, 'cache'), exist_ok=True)
def img(x0, y0, M, cf):
    u = f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+M},{y0+M}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image"
    for t in range(6):
        if os.path.exists(cf) and open(cf, 'rb').read(2) == b'\xff\xd8': break
        try: open(cf, 'wb').write(urllib.request.urlopen(u, timeout=120).read())
        except Exception: time.sleep(min(30, 3 * (t + 1)))
    try: return Image.open(cf).convert('RGB')
    except Exception: return tiles(x0, y0, M, cf)
def tiles(x0, y0, M, cf, z=19):
    """The export refuses some areas (HTTP 500): build the view from the cached web tiles instead (grid turn under 1 deg here)."""
    import math, io
    t = Transformer.from_crs(7856, 4326, always_xy=True).transform
    n = 2 ** z
    def px(x, y):
        lon, lat = t(x, y)
        return (lon + 180) / 360 * n * 256, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256
    (ax, ay), (bx, by) = px(x0, y0 + M), px(x0 + M, y0)
    W = Image.new('RGB', ((int(bx // 256) - int(ax // 256) + 1) * 256, (int(by // 256) - int(ay // 256) + 1) * 256), (90, 90, 90))
    for i in range(int(ax // 256), int(bx // 256) + 1):
        for j in range(int(ay // 256), int(by // 256) + 1):
            u = f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{j}/{i}"
            try: W.paste(Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=60).read())).convert('RGB'), ((i - int(ax // 256)) * 256, (j - int(ay // 256)) * 256))
            except Exception: pass
    o = (int(ax // 256) * 256, int(ay // 256) * 256)
    im = W.crop((int(ax - o[0]), int(ay - o[1]), int(bx - o[0]), int(by - o[1]))).resize((PX, PX))
    im.save(cf, quality=85); return im
def tile(n):
    rid, key, how, v, ring, sp, part = jobs[n]
    b = part.bounds; M = max(80.0, max(b[2] - b[0], b[3] - b[1]) + 40); c = part.envelope.centroid
    x0, y0 = round(c.x - M / 2, 1), round(c.y - M / 2, 1); M = round(M, 1)
    im = img(x0, y0, M, f"{out}/cache/sd-{rid}-{key.replace(':', '_')}.jpg"); dr = ImageDraw.Draw(im); s = PX / M
    q = lambda a, b_: ((a - x0) * s, (y0 + M - b_) * s)
    dr.line([q(*p) for p in ring.coords], fill=(0, 255, 255), width=2)
    for p in sp: x, y = q(*p); dr.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 0, 255))
    dr.rectangle((0, 0, 260, 22), fill=(0, 0, 0)); dr.text((5, 5), f"{n + 1}  {rid}  {M:.0f} m across", fill=(255, 255, 0))
    return im
with ThreadPoolExecutor(6) as ex: ims = list(ex.map(tile, range(len(jobs))))
os.makedirs(out, exist_ok=True)
for s0 in range(0, len(ims), 4):
    sh = Image.new('RGB', (2 * PX, 2 * PX), (0, 0, 0))
    for j, im in enumerate(ims[s0:s0 + 4]): sh.paste(im, ((j % 2) * PX, (j // 2) * PX))
    sh.save(os.path.join(out, f"sheet-{s0 // 4 + 1:03d}.jpg"), quality=85)
json.dump([[n + 1, j[0], j[1], j[2], j[3]] for n, j in enumerate(jobs)], open(os.path.join(out, 'index.json'), 'w'))
