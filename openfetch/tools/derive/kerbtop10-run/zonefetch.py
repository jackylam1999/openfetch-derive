import json,sys,os,time,urllib.request,urllib.parse
from concurrent.futures import ThreadPoolExecutor
U="https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/EPI_Primary_Planning_Layers/MapServer/2/query"
def one(c):
    x,y=c; fn=f"in/zones/{x*1000}_{y*1000}.json"
    if os.path.exists(fn): return
    out=[];off=0
    while True:
        q={"geometry":f"{x*1000-50},{y*1000-50},{x*1000+1050},{y*1000+1050}","geometryType":"esriGeometryEnvelope","inSR":7856,"outSR":7856,"spatialRel":"esriSpatialRelIntersects","where":"1=1","outFields":"OBJECTID,SYM_CODE,PURPOSE,LAY_CLASS","resultOffset":off,"resultRecordCount":200,"f":"geojson"}
        for i in range(6):
            try: d=json.loads(urllib.request.urlopen(urllib.request.Request(U+"?"+urllib.parse.urlencode(q),headers={"User-Agent":"openfetch-derive"}),timeout=120).read());break
            except Exception as e:
                if i==5: raise
                time.sleep(2**i)
        if "error" in d: raise RuntimeError(d["error"])
        g=d.get("features",[]);out+=g;off+=len(g)
        if not g or (len(g)<200 and not d.get("exceededTransferLimit")): break
    json.dump({"type":"FeatureCollection","features":out},open(fn,"w"))
cells=[tuple(map(int,l.split())) for l in open(sys.argv[1]) if l.strip()]
with ThreadPoolExecutor(4) as ex: list(ex.map(one,cells))
print("done")
