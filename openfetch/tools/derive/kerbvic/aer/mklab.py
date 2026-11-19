"""Training pair per CoM box: aerial mosaic (0.25 m, z19) + road mask (CoM carriageway, channel, kerb, arterial, tram) + valid mask (inside City of Melbourne)."""
import sys, json, numpy as np, math
sys.path.insert(0, sys.argv[1]); from mosaic import mosaic
from shapely.geometry import shape, box
from shapely.ops import transform, unary_union
from shapely import contains_xy
from pyproj import Transformer
from PIL import Image, ImageDraw
S = sys.argv[1]; TO = Transformer.from_crs(4326, 7855, always_xy=True).transform; RES = 0.25
BOX = json.load(open(sys.argv[2])); com = transform(TO, shape(json.load(open(f"{S}/truth/com_lga.geojson"))["features"][0]["geometry"]))
T = [(transform(TO, shape(f["geometry"])).buffer(0)) for f in json.load(open(f"{S}/truth/com_kcc.geojson"))["features"]]
from shapely.strtree import STRtree
TT = STRtree(T)
for name in sys.argv[3:]:
    lat, lon = BOX[name]; cx, cy = TO(lon, lat); x0, y0, x1, y1 = cx - 600, cy - 600, cx + 600, cy + 600
    img = mosaic(x0, y0, x1, y1, RES, 19); H, W = img.shape[:2]
    def raster(geoms):
        m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m)
        for g in geoms:
            for p in getattr(g, "geoms", [g]):
                if p.geom_type != "Polygon": continue
                d.polygon([((x - x0) / RES, (y1 - y) / RES) for x, y in p.exterior.coords], fill=1)
                for h in p.interiors: d.polygon([((x - x0) / RES, (y1 - y) / RES) for x, y in h.coords], fill=0)
        return np.array(m, np.uint8)
    bb = box(x0, y0, x1, y1); road = raster([T[i] for i in TT.query(bb)])
    valid = raster([com.intersection(bb).buffer(-15)])
    np.savez_compressed(f"{S}/train_{name}.npz", img=img, road=road, valid=valid, origin=np.array([x0, y1, RES]))
    print(name, img.shape, road.mean().round(3), valid.mean().round(3), flush=True)
