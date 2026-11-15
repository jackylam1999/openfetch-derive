import json, math, gzip, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pmtiles.reader import Reader
import mapbox_vector_tile as mvt
from pyproj import Transformer
from shapely.geometry import Polygon, box
from shapely.strtree import STRtree
URL="https://tiles.openfetch.earth/au/2026-10-21.0/buildings.pmtiles"
def get(off, ln):
    return subprocess.run(["curl","-s","-m","90","--retry","3","-r",f"{off}-{off+ln-1}",URL],capture_output=True,check=True).stdout
R=Reader(get); z=14
back=Transformer.from_crs(7856,4326,always_xy=True).transform
to=Transformer.from_crs(4326,7856,always_xy=True).transform
cells=[tuple(map(int,l.split())) for l in open('../cells.txt') if l.strip()]
def tx(lon,lat): n=2**z; return int((lon+180)/360*n), int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
T=set()
for cx,cy in cells:
    a=back(cx*1000-400,cy*1000-400); b=back(cx*1000+1400,cy*1000+1400)
    x0,y1=tx(*a); x1,y0=tx(*b)
    for x in range(x0,x1+1):
        for y in range(y0,y1+1): T.add((x,y))
print(len(T),'tiles',flush=True)
def one(t):
    x,y=t; d=R.get(z,x,y); out=[]
    if not d: return out
    try: d=gzip.decompress(d)
    except Exception: pass
    for ln,L in mvt.decode(d).items():
        ext=L.get('extent',4096)
        for f in L['features']:
            g=f['geometry']; polys=[g['coordinates']] if g['type']=='Polygon' else g['coordinates'] if g['type']=='MultiPolygon' else []
            for p in polys:
                n=2**z
                ring=[]
                for c in p[0]:
                    lon=(x+c[0]/ext)/n*360-180; yy=(y+1-c[1]/ext)/n
                    ring.append(to(lon, math.degrees(math.atan(math.sinh(math.pi*(1-2*yy))))))
                if len(ring)>3: out.append(ring)
    return out
with ThreadPoolExecutor(12) as ex: res=list(ex.map(one,sorted(T)))
P=[]
for r in res:
    for ring in r:
        g=Polygon(ring).buffer(0)
        if g.geom_type=='Polygon' and g.area>10: P.append(g)
print(len(P),'polys',flush=True)
t=STRtree(P)
for cx,cy in cells:
    B=box(cx*1000-350,cy*1000-350,cx*1000+1350,cy*1000+1350)
    fs=[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[list(back(*c)) for c in P[int(k)].exterior.coords]]}} for k in t.query(B)]
    json.dump({"type":"FeatureCollection","features":fs},open(f'bld/{cx}_{cy}.json','w'))
print('done')
