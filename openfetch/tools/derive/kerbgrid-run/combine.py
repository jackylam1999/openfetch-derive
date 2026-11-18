import json, glob
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.strtree import STRtree
to=Transformer.from_crs(4326,7856,always_xy=True).transform
sub=json.load(open('cellsub.json'))
F=[]; P=[]
for fn in sorted(glob.glob('gridall/*_*.json')):
    if fn.endswith('why.json'): continue
    n=fn.split('/')[-1][:-5]
    for f in json.load(open(fn))['features']:
        p=Polygon([to(*c) for c in f['geometry']['coordinates']])
        dup=any(q.intersection(p).area>0.3*min(p.area,q.area) for q in P if q.intersects(p))
        if dup: continue
        P.append(p); f['properties'].update(id=f"B{len(F)+1:04d}", cell=n, suburb=sub[n][1]); F.append(f)
json.dump({"type":"FeatureCollection","features":F},open('blocks.json','w'))
print(len(F),'blocks',round(sum(p.exterior.length for p in P)/1000,1),'km')
