import os; K = os.environ["K"]
import json, time, urllib.request, urllib.parse
from pyproj import Transformer
back=Transformer.from_crs(7856,4326,always_xy=True).transform
SV={"liverpool":"https://gis.liverpool.nsw.gov.au/server/rest/services/Public/Dial_Before_You_Dig/MapServer/3/query",
    "woollahra":"https://maps.woollahra.nsw.gov.au/server/rest/services/basemap/basemap_eng_assets/MapServer/43/query",
    "parramatta":"https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/2/query"}
cells=[tuple(map(int,l.split())) for l in open(''+K+'/cells.txt') if l.strip()]
xs=[c[0] for c in cells]; ys=[c[1] for c in cells]
# group cells into 5 km tiles
T=sorted({(x//5,y//5) for x,y in cells})
out=[]; seen=set()
def fetch(u,q):
    for i in range(5):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u+"?"+urllib.parse.urlencode(q),headers={"User-Agent":"openfetch-derive"}),timeout=120).read())
        except Exception as e:
            err=e; time.sleep(2**(i+1))
    raise err
for name,u in SV.items():
    n0=len(out)
    for tx,ty in T:
        a=back(tx*5000-500,ty*5000-500); b=back(tx*5000+5500,ty*5000+5500)
        off=0
        while True:
            d=fetch(u,{"geometry":f"{a[0]},{a[1]},{b[0]},{b[1]}","geometryType":"esriGeometryEnvelope","inSR":4326,"outSR":4326,
                "spatialRel":"esriSpatialRelIntersects","outFields":"*","returnGeometry":"true","f":"geojson","resultOffset":off,"resultRecordCount":200})
            if "error" in d: print(name,d["error"]); break
            fs=d.get("features",[])
            for f in fs:
                g=f.get("geometry")
                if not g: continue
                parts=[g["coordinates"]] if g["type"]=="LineString" else g["coordinates"] if g["type"]=="MultiLineString" else []
                for p in parts:
                    k=(name,round(p[0][0],6),round(p[0][1],6),len(p))
                    if k in seen or len(p)<2: continue
                    seen.add(k); out.append({"type":"Feature","properties":{"c":name},"geometry":{"type":"LineString","coordinates":p}})
            off+=len(fs)
            if len(fs)<200 and not d.get("exceededTransferLimit"): break
    print(name,len(out)-n0,flush=True)
json.dump({"type":"FeatureCollection","features":out},open(K+"/off/official.json","w"))
