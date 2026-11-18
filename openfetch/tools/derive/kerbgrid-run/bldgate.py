import json, glob
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union
to=Transformer.from_crs(4326,7856,always_xy=True).transform
F=json.load(open('blocks.json'))['features']; keep=[]; out=0
cache={}
for f in F:
    n=f['properties']['cell']
    if n not in cache:
        B=[]
        for b in json.load(open(f'grid/bld/{n}.json'))['features']:
            p=Polygon([to(*c[:2]) for c in b['geometry']['coordinates'][0]]).buffer(0)
            if p.area>=120: B.append(p)
        cache={n:(B,STRtree(B))}
    B,T=cache[n]
    g=LineString([to(*c) for c in f['geometry']['coordinates']])
    ins=unary_union([B[int(k)] for k in T.query(g)] or [Polygon()])
    part=g.intersection(ins)
    longest=max([p.length for p in getattr(part,'geoms',[part])] or [0]) if not part.is_empty else 0
    if longest>3: out+=1; f['properties']['bld']=round(longest,1)
    else: keep.append(f)
json.dump({"type":"FeatureCollection","features":keep},open('blocks2.json','w'))
print('building gate out',out,'kept',len(keep))
