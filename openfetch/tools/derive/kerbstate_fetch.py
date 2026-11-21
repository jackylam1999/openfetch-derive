"""Inputs for kerbstate.py (kerb scenario 12): council kerbs and footpath shapes, NSW road centrelines and railways, in EPSG:7856.
    python3 kerbstate_fetch.py <council> lon0,lat0,lon1,lat1 out_dir
council: parramatta | canterbury-bankstown. Facts per council are in the openfetch data registry (data/sources/nsw/*.json):
  parramatta            Data.NSW Hosted/Parramatta_Council_Data_1 layer 2 kerbs, layer 4 footpaths 2018 (shapes); stored GDA94
                        (served 4283, shift client): fetched as 4283 and moved to GDA2020 here. Park paths (field park set) left out.
  canterbury-bankstown  Kerb_Condition_1_5 and Footpath_Condition_1_5 (lines, stored 4283, served 4326, shift client); a footpath
                        line is widened 0.6 m each side into a shape; the verge is measured at the corners so its width is absorbed.
Writes kerb.json, foot.json, roads.json, rail.json. Attributes are dropped except the few the tools read (no inspector names).
"""
import json, sys, time, urllib.parse, urllib.request
from pyproj import Transformer
from shapely.geometry import mapping, shape

NSW = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Transport_Theme_multiCRS/FeatureServer"
COUNCILS = {
    "parramatta": {"kerb": ("https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/2", 4283),
                   "foot": ("https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/4", 4283),
                   "keep_foot": lambda p: not (p.get("park") or "").strip(), "widen": 0},
    "canterbury-bankstown": {"kerb": ("https://services2.arcgis.com/Ax17MufLaTdpFneh/arcgis/rest/services/Kerb_Condition_1_5/FeatureServer/0", 4283),
                             "foot": ("https://services2.arcgis.com/Ax17MufLaTdpFneh/arcgis/rest/services/Footpath_Condition_1_5/FeatureServer/0", 4283),
                             "keep_foot": lambda p: True, "widen": 0.6},
}
KEEP = ("functionhierarchy", "roadontype", "classsubtype", "park")


def query(url, bbox, srcsr):
    feats, off = [], 0
    while True:
        p = dict(where="1=1", geometry=",".join(map(str, bbox)), geometryType="esriGeometryEnvelope", inSR=4326, outSR=srcsr,
                 spatialRel="esriSpatialRelIntersects", outFields="*", f="geojson", resultOffset=off, resultRecordCount=1000)
        for k in range(5):
            try:
                d = json.load(urllib.request.urlopen(url + "/query?" + urllib.parse.urlencode(p), timeout=180)); break
            except Exception:
                if k == 4:
                    raise
                time.sleep(5 * (k + 1))
        fs = d.get("features", []); feats += fs; off += len(fs)
        if not fs or (len(fs) < 1000 and not d.get("exceededTransferLimit")):
            break
    t = Transformer.from_crs(srcsr, 7856, always_xy=True)
    def tr(c):
        return list(t.transform(c[0], c[1])) if isinstance(c[0], (int, float)) else [tr(e) for e in c]
    out = []
    for f in feats:
        if f.get("geometry"):
            out.append({"type": "Feature", "properties": {k: f["properties"].get(k) for k in KEEP if k in f["properties"]},
                        "geometry": {"type": f["geometry"]["type"], "coordinates": tr(f["geometry"]["coordinates"])}})
    return out


def main(a):
    c = COUNCILS[a[0]]; bbox = [float(x) for x in a[1].split(",")]; d = a[2].rstrip("/")
    save = lambda n, F: json.dump({"type": "FeatureCollection", "features": F}, open(f"{d}/{n}", "w"))
    save("kerb.json", query(c["kerb"][0], bbox, c["kerb"][1]))
    foot = [f for f in query(c["foot"][0], bbox, c["foot"][1]) if c["keep_foot"](f["properties"])]
    if c["widen"]:
        foot = [{"type": "Feature", "properties": {}, "geometry": mapping(shape(f["geometry"]).buffer(c["widen"], cap_style="flat"))} for f in foot]
    save("foot.json", foot); save("roads.json", query(NSW + "/5", bbox, 7844)); save("rail.json", query(NSW + "/7", bbox, 7844))
    print("written", d)


if __name__ == "__main__":
    main(sys.argv[1:]) if len(sys.argv) == 4 else print(__doc__)
