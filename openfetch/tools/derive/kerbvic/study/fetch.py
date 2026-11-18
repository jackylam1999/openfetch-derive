import json, sys, os, math, urllib.request, urllib.parse, time
B = "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services"
LAY = {"lots": "Vicmap_Parcel/FeatureServer/0", "roads": "Vicmap_Transport/FeatureServer/1",
       "trees": "Vicmap_Vegetation_Tree_Urban/FeatureServer/0"}
BOX = json.load(open(os.path.join(os.path.dirname(__file__), "boxes.json")))
def bbox(lat, lon, half=550):
    dlat = half / 111320; dlon = half / (111320 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat
def get(url, data=None, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data=data, headers={"User-Agent": "openfetch-derive"}), timeout=180).read()
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(3 * (i + 1))
def arc(layer, bb, out):
    feats, off = [], 0
    while True:
        q = {"where": "1=1", "geometry": ",".join(map(str, bb)), "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "f": "geojson", "resultOffset": off, "resultRecordCount": 2000}
        d = json.loads(get(f"{B}/{layer}/query?" + urllib.parse.urlencode(q)))
        feats += d.get("features", [])
        if len(d.get("features", [])) < 2000 and not d.get("properties", {}).get("exceededTransferLimit"): break
        off += len(d["features"])
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    return len(feats)
def osm(bb, out):
    s, w, n, e = bb[1], bb[0], bb[3], bb[2]
    q = f'[out:json][timeout:120];(way["footway"="sidewalk"]({s},{w},{n},{e});way["highway"]({s},{w},{n},{e}););out geom tags;'
    d = json.loads(get("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode()))
    json.dump(d, open(out, "w")); return len(d.get("elements", []))
for name in sys.argv[1:]:
    lat, lon = BOX[name]; bb = bbox(lat, lon); d = os.path.join(os.path.dirname(__file__), "..", "data", name); os.makedirs(d, exist_ok=True)
    for k, l in LAY.items():
        print(name, k, arc(l, bb, os.path.join(d, k + ".geojson")), flush=True)
    if 0: print(name, "osm", osm(bb, os.path.join(d, "osm.json")), flush=True)

