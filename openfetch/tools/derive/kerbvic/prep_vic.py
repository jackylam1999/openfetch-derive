"""Inputs for kerblot.py in Victoria (no LiDAR): Vicmap lots (road parcels out), Vicmap roads mapped to kerblot's road codes,
Vicmap building footprints per 1 km square (roof guard), OSM footpath lines (width measure, kerblot.sw_width).
    python3 prep_vic.py out_dir lon0 lat0 lon1 lat1 victoria.osm.pbf
Writes out_dir/{lots,roads}/*.json (EPSG 7855), bld/<x>_<y>.json (lon/lat), sidewalks.geojson, empty.geojson, cells.txt."""
import json, math, os, sys, time, urllib.parse, urllib.request
from pyproj import Transformer
ARC = "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services"
WFS = "https://opendata.maps.vic.gov.au/geoserver/wfs"
TO = Transformer.from_crs(4326, 7855, always_xy=True)
FH = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}      # Vicmap class_code -> kerblot functionhierarchy (freeway 1 ... local 6)
LANE_NAMES = (None, "LANE", "ALLEY", "PLACE", "WAY", "WALK", "MEWS", "ROW")   # inner-Melbourne lanes are often named Place or Way


def get(url, data=None):
    for i in range(5):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data=data, headers={"User-Agent": "openfetch-derive"}), timeout=240).read()
        except Exception:
            if i == 4:
                raise
            time.sleep(4 * (i + 1))


def arc(layer, bb, where="1=1", depth=0):
    """Features in the box; a box the service refuses (it answers 400 for some large boxes) is split in four, each feature once."""
    feats, off = [], 0
    while True:
        q = {"where": where, "geometry": ",".join(map(str, bb)), "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "f": "geojson", "resultOffset": off, "resultRecordCount": 2000}
        d = json.loads(get(f"{ARC}/{layer}/query?" + urllib.parse.urlencode(q)))
        if "error" in d:
            if depth >= 4:
                raise RuntimeError(f"{layer} refused {bb}: {d['error']}")
            mx, my = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            seen, out = set(), []
            for b in ((bb[0], bb[1], mx, my), (mx, bb[1], bb[2], my), (bb[0], my, mx, bb[3]), (mx, my, bb[2], bb[3])):
                for f in arc(layer, b, where, depth + 1):
                    k = (f.get("properties") or {}).get("OBJECTID", f.get("id"))
                    if k not in seen:
                        seen.add(k); out.append(f)
            return out
        feats += d.get("features", [])
        if len(d.get("features", [])) < 2000 and not d.get("properties", {}).get("exceededTransferLimit"):
            return feats
        off += len(d["features"])


def wfs(type_name, bb):
    feats, start = [], 0
    while True:
        q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": type_name, "outputFormat": "application/json",
             "bbox": f"{bb[1]},{bb[0]},{bb[3]},{bb[2]},urn:ogc:def:crs:EPSG::4326", "count": 5000, "startIndex": start}
        d = json.loads(get(WFS + "?" + urllib.parse.urlencode(q)))
        feats += d.get("features", [])
        if len(d.get("features", [])) < 5000:
            return feats
        start += 5000


def proj(geom):
    def walk(c):
        return [walk(x) for x in c] if isinstance(c[0], list) else list(TO.transform(c[0], c[1]))
    return {"type": geom["type"], "coordinates": walk(geom["coordinates"])}


def road_props(p):
    cls = p.get("class_code"); ft = p.get("feature_type_code")
    fh = 10 if ft == "trail" or cls is None or cls >= 6 else FH.get(cls, 6)
    rt = p.get("road_type")
    if cls == 5 and (rt in LANE_NAMES):
        fh = 7
    name = p.get("ezi_road_name")
    return {"OBJECTID": p.get("ufi"), "functionhierarchy": fh, "roadnametype": "LANE" if fh == 7 else rt,
            "roadnameoid": (name + "|" + str(p.get("left_locality"))) if name else None, "roadontype": None, "class_code": cls}


def sidewalks(pbf, bb, out):
    import osmium
    F = []
    class H(osmium.SimpleHandler):
        def way(self, w):
            if w.tags.get("footway") != "sidewalk":
                return
            try:
                c = [(n.lon, n.lat) for n in w.nodes]
            except Exception:
                return
            if len(c) > 1 and any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in c):
                F.append({"type": "Feature", "properties": {"id": w.id}, "geometry": {"type": "LineString", "coordinates": c}})
    H().apply_file(pbf, locations=True, idx="flex_mem")
    json.dump({"type": "FeatureCollection", "features": F}, open(out, "w"))
    return len(F)


def main(a):
    out = a[0]; lon0, lat0, lon1, lat1 = map(float, a[1:5]); pbf = a[5]
    m = 400 / 111320; bb = (lon0 - m * 1.3, lat0 - m, lon1 + m * 1.3, lat1 + m)
    for d in ("lots", "roads", "bld"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    lots = [f for f in arc("Vicmap_Parcel/FeatureServer/0", bb) if f.get("geometry") and f["properties"].get("parcel_road") != "Y"]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"OBJECTID": f["properties"]["OBJECTID"]}, "geometry": proj(f["geometry"])} for f in lots]},
              open(os.path.join(out, "lots", "lots.json"), "w"))
    roads = [f for f in arc("Vicmap_Transport/FeatureServer/1", bb) if f.get("geometry")]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": road_props(f["properties"]), "geometry": proj(f["geometry"])} for f in roads]},
              open(os.path.join(out, "roads", "roads.json"), "w"))
    x0, y0 = TO.transform(lon0, lat0); x1, y1 = TO.transform(lon1, lat1)
    cells = [(x, y) for x in range(int(x0 // 1000), int(x1 // 1000) + 1) for y in range(int(y0 // 1000), int(y1 // 1000) + 1)]
    open(os.path.join(out, "cells.txt"), "w").write("".join(f"{x} {y}\n" for x, y in cells))
    back = Transformer.from_crs(7855, 4326, always_xy=True)
    for x, y in {(x + i, y + j) for x, y in cells for i in (-1, 0, 1) for j in (-1, 0, 1)}:
        lo, la = back.transform(x * 1000, y * 1000); hi, ha = back.transform(x * 1000 + 1000, y * 1000 + 1000)
        F = []
        for f in wfs("open-data-platform:building_polygon", (lo, la, hi, ha)):
            g = f["geometry"]
            for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
                F.append({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": poly}})
        json.dump({"type": "FeatureCollection", "features": F}, open(os.path.join(out, "bld", f"{x}_{y}.json"), "w"))
    json.dump({"type": "FeatureCollection", "features": []}, open(os.path.join(out, "empty.geojson"), "w"))
    print("lots", len(lots), "roads", len(roads), "cells", len(cells), "sidewalks", sidewalks(pbf, bb, os.path.join(out, "sidewalks.geojson")))


if __name__ == "__main__":
    main(sys.argv[1:])
