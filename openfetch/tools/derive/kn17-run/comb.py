import json,glob,sys
from pyproj import Transformer
from shapely.geometry import Polygon,LineString
from shapely.strtree import STRtree
from shapely.ops import unary_union
gd,lot,out=sys.argv[1:4]
to=Transformer.from_crs(4326,7856,always_xy=True).transform
F=[];P=[]
def add(f,src,cell):
    p=Polygon([to(*c[:2]) for c in f['geometry']['coordinates']]).buffer(0)
    if p.is_empty: return
    for q in P:
        if q.intersects(p) and q.intersection(p).area>0.3*min(p.area,q.area): return
    P.append(p); f['properties']={**f.get('properties',{}),'src':src,'cell':cell}; F.append(f)
for f in json.load(open(lot))['features']:
    add(f,'lot',f['properties'].get('cell'))
nl=len(F)
for fn in sorted(glob.glob(gd+'/*_*.json')):
    if fn.endswith('why.json'): continue
    n=fn.split('/')[-1][:-5]
    for f in json.load(open(fn))['features']: add(f,'grid',n)
print('lot',nl,'grid',len(F)-nl)
cache={};keep=[];out_b=0
for i,f in enumerate(F):
    f['properties']['id']=f"K{i+1:04d}"
    g=LineString([to(*c[:2]) for c in f['geometry']['coordinates']])
    b=g.bounds; cx,cy=int((b[0]+b[2])/2//1000),int((b[1]+b[3])/2//1000)
    key=(cx,cy)
    if key not in cache:
        try: B=[Polygon([to(*c[:2]) for c in x['geometry']['coordinates'][0]]).buffer(0) for x in json.load(open(f'b/bld/{cx}_{cy}.json'))['features']]
        except Exception: B=[]
        B=[p for p in B if p.area>=120]; cache={key:(B,STRtree(B))}
    B,T=cache[key]
    ins=unary_union([B[int(k)] for k in T.query(g)] or [Polygon()]); part=g.intersection(ins)
    L=max([p.length for p in getattr(part,'geoms',[part])] or [0]) if not part.is_empty else 0
    if L>3: out_b+=1
    else: keep.append(f)
print('building gate out',out_b,'kept',len(keep),'km',round(sum(LineString([to(*c[:2]) for c in f['geometry']['coordinates']]).length for f in keep)/1000,1))
json.dump({"type":"FeatureCollection","features":keep},open(out,'w'))
