"""Official road, rail, water and unlotted land outlines (NSW cadastre) per 1 km square +-300 m, for kerbcad.py.
    python3 fetchcad.py cells.txt   (writes in/cad/<layer>_<x>_<y>.json)"""
import json, sys, time, urllib.request, urllib.parse, os
from concurrent.futures import ThreadPoolExecutor
def fetch(url,q):
    for i in range(6):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url+"?"+urllib.parse.urlencode(q),headers={"User-Agent":"openfetch-derive"}),timeout=90).read())
        except Exception as e:
            if i==5: raise
            time.sleep(2**(i+1))
def get(url,b,fields,page):
    q={"geometry":",".join(map(str,b)),"geometryType":"esriGeometryEnvelope","inSR":7856,"outSR":7856,"spatialRel":"esriSpatialRelIntersects",
       "outFields":fields,"orderByFields":"OBJECTID","resultRecordCount":page,"f":"geojson"}
    out,off=[],0
    while True:
        d=fetch(url,{**q,"resultOffset":off}); g=d.get("features",[])
        if "error" in d: raise RuntimeError(d["error"])
        out+=[{"type":"Feature","geometry":f["geometry"],"properties":{k.split('.')[-1]:v for k,v in f["properties"].items()}} for f in g if f.get("geometry")]
        off+=len(g)
        if not g or (len(g)<page and not d.get("exceededTransferLimit")): break
    return out
B = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/"
L = {"roadcor": (5, "OBJECTID,roadtype,roadcorridortype,roadnamelabel"), "rail": (7, "OBJECTID,railwaynamelabel"),
     "water": (2, "OBJECTID,waterfeaturenamelabel"), "unid": (4, "OBJECTID,classsubtype")}
def cell(c):
    x, y = c
    for k, (lid, fl) in L.items():
        fn = f"in/cad/{k}_{x}_{y}.json"
        if os.path.exists(fn): continue
        f = get(B + f"{lid}/query", (x * 1000 - 300, y * 1000 - 300, x * 1000 + 1300, y * 1000 + 1300), fl, 200)
        json.dump({"type": "FeatureCollection", "features": f}, open(fn + ".tmp", "w")); os.rename(fn + ".tmp", fn)
    return c
os.makedirs("in/cad", exist_ok=True)
cells = [tuple(map(int, l.split())) for l in open(sys.argv[1]) if l.strip()]
with ThreadPoolExecutor(4) as ex:
    for n in ex.map(cell, cells): print(n, flush=True)
