#!/usr/bin/env python3
"""Victorian boxes for the kerb photo model (Jacky 30 Oct 2026: train Victoria together with NSW; Vicmap agreed to training on its aerial).

Writes the same files as kerbphoto.fetch, in GDA2020 MGA zone 55 (EPSG:7855): the Vicmap Basemaps aerial AERIAL_VG2020 (about 10 cm;
the WMS serves only VicGrid 2020, EPSG:7899, so each box is fetched in 7899 and warped onto the MGA grid), City of Melbourne kerbs
(open data "Road segments, with surface type", type Road Kerb: thin polygons, used as their outlines; lon/lat in GDA94), Vicmap Property parcels without
road parcels as the lots, the LGA from Vicmap Admin, Vicmap Transport roads (class_code mapped onto the NSW functionhierarchy scale)
and Vicmap Hydro water areas.
"""
import sys, os, json, io, urllib.parse
import numpy as np
import kerbphoto as kp

SR = 7855
WMS = ("https://base.maps.vic.gov.au/service?service=WMS&version=1.3.0&request=GetMap&layers=AERIAL_VG2020&styles=&crs=EPSG:7899"
       "&bbox={},{},{},{}&width={}&height={}&format=image/jpeg")
VM = "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/"
LOTS, LGA = VM + "Vicmap_Parcel/FeatureServer/0/query", VM + "Vicmap_Admin/FeatureServer/9/query"
ROADS, WATER = VM + "Vicmap_Transport/FeatureServer/1/query", VM + "Vicmap_Hydro/FeatureServer/1/query"
COM = ("https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/road-segments-with-surface-type/exports/geojson?"
       + urllib.parse.urlencode({"where": 'type="Road Kerb"'}))
HIER = {0: 2, 1: 2, 2: 2, 3: 4, 4: 4, 5: 6}  # Vicmap class_code (freeway..local) -> NSW functionhierarchy band
LGA_NAME = {"com": "MELBOURNE"}


def photo(X0, Y0, W):
    """The box in MGA 55 at kp.CELL, from 7899 tiles of 400 m warped with rasterio (bilinear)."""
    from PIL import Image
    from rasterio.warp import transform, reproject, Resampling
    from affine import Affine
    Image.MAX_IMAGE_PIXELS = None
    xs, ys = transform(f"EPSG:{SR}", "EPSG:7899", [X0, X0 + W, X0, X0 + W], [Y0, Y0, Y0 + W, Y0 + W])
    gx0, gy0, gx1, gy1 = min(xs) - 20, min(ys) - 20, max(xs) + 20, max(ys) + 20
    T = 400; nx, ny = int(np.ceil((gx1 - gx0) / T)), int(np.ceil((gy1 - gy0) / T)); px = int(T / kp.CELL)
    src = np.zeros((ny * px, nx * px, 3), np.uint8)
    for i in range(nx):
        for j in range(ny):
            x0, y0 = gx0 + i * T, gy0 + j * T
            b = kp.get(WMS.format(x0, y0, x0 + T, y0 + T, px, px))
            if b[:2] != b"\xff\xd8":
                print(f"no Vicmap photo at {x0},{y0}", file=sys.stderr); continue
            src[(ny - 1 - j) * px:(ny - j) * px, i * px:(i + 1) * px] = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))
    n = int(round(W / kp.CELL)); dst = np.zeros((3, n, n), np.uint8)
    reproject(np.moveaxis(src, -1, 0), dst, src_transform=Affine(kp.CELL, 0, gx0, 0, -kp.CELL, gy0 + ny * T), src_crs="EPSG:7899",
              dst_transform=Affine(kp.CELL, 0, X0, 0, -kp.CELL, Y0 + W), dst_crs=f"EPSG:{SR}", resampling=Resampling.bilinear)
    return np.moveaxis(dst, 0, -1)


def com_kerbs(out):
    """All City of Melbourne kerb polygons, once per cache, as outlines in MGA 55."""
    p = f"{out}/_com_kerbs.geojson"
    if not os.path.exists(p):
        from rasterio.warp import transform_geom
        from shapely.geometry import shape, mapping
        fs = []
        for f in json.loads(kp.get(COM))["features"]:
            if f.get("geometry"):
                g = shape(transform_geom("EPSG:4283", f"EPSG:{SR}", f["geometry"]))  # lon/lat are GDA94 (first cache: 1.4 m south)
                fs.append({"type": "Feature", "geometry": mapping(g.boundary), "properties": {}})
        json.dump({"type": "FeatureCollection", "features": fs}, open(p, "w"))
    return json.load(open(p))["features"]


def fetch(name, council, x0, y0, out):
    from shapely.geometry import shape, box
    os.makedirs(out, exist_ok=True)
    X0, Y0, W = x0 - kp.MARGIN, y0 - kp.MARGIN, kp.SIZE + 2 * kp.MARGIN
    np.save(f"{out}/{name}_rgb.npy", photo(X0, Y0, W))
    bb = box(X0 - 3, Y0 - 3, X0 + W + 3, Y0 + W + 3)
    kerbs = [f for f in com_kerbs(out) if shape(f["geometry"]).intersects(bb)]
    q = lambda url, f: kp.query(url, (X0, Y0, X0 + W, Y0 + W), sr=SR, fields=f)
    lots = [f for f in q(LOTS, "OBJECTID,parcel_road") if f["properties"].get("parcel_road") != "Y"]
    roads = q(ROADS, "OBJECTID,class_code")
    for f in roads:
        f["properties"] = {"functionhierarchy": HIER.get(f["properties"].get("class_code"), 7)}
    lga = [f for f in q(LGA, "OBJECTID,lga_name") if f["properties"].get("lga_name") == LGA_NAME[council]]
    for k, fs in (("kerbs", kerbs), ("lots", lots), ("roads", roads), ("water", q(WATER, "OBJECTID")), ("lga", lga)):
        json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{name}_{k}.geojson", "w"))
    json.dump({"x0": X0, "y0": Y0, "w": W, "box": [x0, y0, x0 + kp.SIZE, y0 + kp.SIZE], "crs": SR}, open(f"{out}/{name}_meta.json", "w"))
    print(f"{name}: Vicmap photo, {len(kerbs)} council kerbs, {len(lots)} lots, {len(roads)} roads", file=sys.stderr)
