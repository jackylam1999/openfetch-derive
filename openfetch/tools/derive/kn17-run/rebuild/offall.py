import os; K = os.environ["K"]
import json, sys, time, urllib.request, urllib.parse
S = {"liverpool": "https://gis.liverpool.nsw.gov.au/server/rest/services/Public/Dial_Before_You_Dig/MapServer/3",
     "woollahra": "https://maps.woollahra.nsw.gov.au/server/rest/services/basemap/basemap_eng_assets/MapServer/43",
     "canterbury-bankstown": "https://services2.arcgis.com/Ax17MufLaTdpFneh/arcgis/rest/services/Kerb_Condition_1_5/FeatureServer/0"}
def get(u, q):
    for i in range(5):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u + "/query?" + urllib.parse.urlencode(q), headers={"User-Agent": "openfetch-derive"}), timeout=120).read())
        except Exception as e: err = e; time.sleep(3 * (i + 1))
    raise err
for n, u in S.items():
    if n != "canterbury-bankstown": continue
    ids = get(u, {"where": "1=1", "geometry": "150.68,-34.44,151.29,-33.73", "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "returnIdsOnly": "true", "f": "json"})
    oid = sorted(ids.get("objectIds") or []); out = []
    for k in range(0, len(oid), 200):
        d = get(u, {"objectIds": ",".join(map(str, oid[k:k + 200])), "outFields": "*", "outSR": 4326, "f": "json"})
        out += [{"type": "Feature", "properties": {}, "geometry": {"type": "MultiLineString", "coordinates": f["geometry"]["paths"]}} for f in d.get("features", []) if (f.get("geometry") or {}).get("paths")]
    json.dump({"type": "FeatureCollection", "features": out}, open(f"{K}/off2/official-{n}.json", "w")); print(n, len(oid), len(out), flush=True)
