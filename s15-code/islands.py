import json, glob, sys
from shapely.geometry import shape, LineString, Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
segs=[];seen=set()
for fn in sorted(glob.glob('in/roads/*.json')):
    for f in json.load(open(fn))['features']:
        p=f['properties']; oid=p.get('OBJECTID') or p.get('objectid')
        if oid in seen or not f.get('geometry'): continue
        seen.add(oid)
        if p.get('roadontype') in (2,3): continue
        g=shape(f['geometry'])
        for l in getattr(g,'geoms',[g]): segs.append((l,p))
net=unary_union([l for l,_ in segs])
faces=list(polygonize(net))
isl=[]
for F in faces:
    a=F.area; per=F.length
    if a<30 or a>4000: continue
    comp=4*3.1416*a/per**2
    isl.append(F)
print(len(segs),len(faces),len(isl),file=sys.stderr)
json.dump([list(F.exterior.coords) for F in isl],open('islands.json','w'))
