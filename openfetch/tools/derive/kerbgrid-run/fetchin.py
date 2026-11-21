import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nswsrc import require_multicrs
import json, sys, time, urllib.request, urllib.parse, os
from concurrent.futures import ThreadPoolExecutor
LOTS=require_multicrs("https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query")
ROADS=require_multicrs("https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Transport_Theme_multiCRS/FeatureServer/5/query")
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
def cell(c):
    x,y=c; n=f"{x*1000}_{y*1000}"
    for kind,url,m,fields,page in (("lots",LOTS,300,"OBJECTID",100),("roads",ROADS,500,"OBJECTID,functionhierarchy,roadontype",1000)):
        fn=f"in/{kind}/{n}.json"
        if os.path.exists(fn): continue
        f=get(url,(x*1000-m,y*1000-m,x*1000+1000+m,y*1000+1000+m),fields,page)
        json.dump({"type":"FeatureCollection","features":f},open(fn+".tmp","w")); os.rename(fn+".tmp",fn)
    return n
cells=[tuple(map(int,l.split())) for l in open(sys.argv[1]) if l.strip()]
with ThreadPoolExecutor(int(os.environ.get("TH",4))) as ex:
    for n in ex.map(cell,cells): print(n,flush=True)
