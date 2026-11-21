"""mkang.py rseg.geojson bays.geojson angboxes.json out_dir : training pairs for the angle-bay fine-tune (council road surfaces as labels)
road = carriageway, channel, kerb, arterial, tram formation; valid = within 15 m of any council road polygon; ang = within 8 m of an angle bay point"""
import sys, json, numpy as np
sys.path.insert(0, "/tmp/claude-0/w/derive/openfetch/tools/derive/kerbvic"); from mosaic import mosaic
from shapely.geometry import shape, box
from shapely.ops import transform
from shapely.strtree import STRtree
from scipy.spatial import cKDTree
from scipy import ndimage
from pyproj import Transformer
from PIL import Image, ImageDraw
TO = Transformer.from_crs(4326, 7855, always_xy=True); RES = 0.25
ROAD = {"Road Carriageway", "Road Channel", "Road Kerb", "Road Arterial", "Road Tram Formation", "Road Kerb & Or Channel"}
G, R = [], []
for f in json.load(open(sys.argv[1]))["features"]:
    if not f["geometry"]: continue
    g = transform(TO.transform, shape(f["geometry"])).buffer(0); G.append(g); R.append(f["properties"].get("type") in ROAD)
T = STRtree(G)
bp = np.array([TO.transform(*f["geometry"]["coordinates"]) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]])
dd, _ = cKDTree(bp).query(bp, 2); ang = bp[dd[:, 1] < 3.3]
for name, (lat, lon) in json.load(open(sys.argv[3])).items():
    cx, cy = TO.transform(lon, lat); x0, y0, x1, y1 = cx - 600, cy - 600, cx + 600, cy + 600
    img = mosaic(x0, y0, x1, y1, RES, 19); H, W = img.shape[:2]
    def raster(geoms):
        m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m)
        for g in geoms:
            for p in getattr(g, "geoms", [g]):
                if p.geom_type != "Polygon": continue
                d.polygon([((x - x0) / RES, (y1 - y) / RES) for x, y in p.exterior.coords], fill=1)
                for h in p.interiors: d.polygon([((x - x0) / RES, (y1 - y) / RES) for x, y in h.coords], fill=0)
        return np.array(m, np.uint8)
    idx = T.query(box(x0, y0, x1, y1)); road = raster([G[i] for i in idx if R[i]]); anyc = raster([G[i] for i in idx])
    valid = (ndimage.distance_transform_edt(1 - anyc) <= 60).astype(np.uint8)
    a = np.zeros((H, W), np.uint8); q = ang[(ang[:, 0] > x0) & (ang[:, 0] < x1) & (ang[:, 1] > y0) & (ang[:, 1] < y1)]
    a[np.clip(((y1 - q[:, 1]) / RES).astype(int), 0, H - 1), np.clip(((q[:, 0] - x0) / RES).astype(int), 0, W - 1)] = 1
    a = (ndimage.distance_transform_edt(1 - a) <= 32).astype(np.uint8)
    np.savez_compressed(f"{sys.argv[4]}/train_{name}.npz", img=img, road=road, valid=valid, ang=a)
    print(name, road.mean().round(3), valid.mean().round(3), a.mean().round(4), flush=True)
