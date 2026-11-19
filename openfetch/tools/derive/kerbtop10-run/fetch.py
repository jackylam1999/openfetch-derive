import json, sys, os, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
B = "https://portal.spatial.nsw.gov.au/server/rest/services"
LOTS = B + "/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query"
ROADS = B + "/NSW_Transport_Theme/FeatureServer/5/query"
SUB = B + "/NSW_Administrative_Boundaries_Theme/FeatureServer/2/query"
W = sys.argv[1]; SUBS = sys.argv[2].split(',')


def fetch(url, q):
    for i in range(6):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "openfetch-derive"}), timeout=120).read())
        except Exception:
            if i == 5: raise
            time.sleep(2 ** (i + 1))


def env(url, b, fields, page):
    q = {"geometry": ",".join(map(str, b)), "geometryType": "esriGeometryEnvelope", "inSR": 7856, "outSR": 7856, "spatialRel": "esriSpatialRelIntersects",
         "outFields": fields, "orderByFields": "OBJECTID", "resultRecordCount": page, "f": "geojson"}
    out, off = [], 0
    while True:
        d = fetch(url, {**q, "resultOffset": off})
        if "error" in d: raise RuntimeError(d["error"])
        g = d.get("features", [])
        out += [{"type": "Feature", "geometry": f["geometry"], "properties": {k.split('.')[-1]: v for k, v in f["properties"].items()}} for f in g if f.get("geometry")]
        off += len(g)
        if not g or (len(g) < page and not d.get("exceededTransferLimit")): break
    return out


def tile(a):
    kind, x, y = a
    fn = f"{W}/{kind}/{x}_{y}.json"
    if os.path.exists(fn): return
    if kind == "lots":
        f = env(LOTS, (x, y, x + 500, y + 500), "OBJECTID", 100)
    else:
        f = env(ROADS, (x, y, x + 500, y + 500), "OBJECTID,functionhierarchy,roadontype,operationalstatus,roadnameoid,roadnamebase,roadnametype", 1000)
    json.dump({"type": "FeatureCollection", "features": f}, open(fn + ".tmp", "w")); os.rename(fn + ".tmp", fn)


os.makedirs(f"{W}/lots", exist_ok=True); os.makedirs(f"{W}/roads", exist_ok=True); os.makedirs(f"{W}/sub", exist_ok=True)
jobs = set()
for s in SUBS:
    fn = f"{W}/sub/{s}.json"
    if not os.path.exists(fn):
        d = fetch(SUB, {"where": f"suburbname='{s.upper()}'", "outSR": 7856, "outFields": "suburbname", "f": "geojson"})
        json.dump(d, open(fn, "w"))
    d = json.load(open(fn))
    xs = [c[0] for f in d["features"] for r in (f["geometry"]["coordinates"] if f["geometry"]["type"] == "Polygon" else [q for p in f["geometry"]["coordinates"] for q in p]) for c in r]
    ys = [c[1] for f in d["features"] for r in (f["geometry"]["coordinates"] if f["geometry"]["type"] == "Polygon" else [q for p in f["geometry"]["coordinates"] for q in p]) for c in r]
    x0, y0, x1, y1 = (int(min(xs) - 150) // 500 * 500, int(min(ys) - 150) // 500 * 500, int(max(xs) + 150), int(max(ys) + 150))
    for x in range(x0, x1, 500):
        for y in range(y0, y1, 500):
            jobs.add(("lots", x, y)); jobs.add(("roads", x, y))
    print(s, len(d["features"]), x0, y0, x1, y1, flush=True)
with ThreadPoolExecutor(8) as ex:
    for i, _ in enumerate(ex.map(tile, sorted(jobs))):
        if i % 50 == 0: print(i, len(jobs), flush=True)
print("done")
