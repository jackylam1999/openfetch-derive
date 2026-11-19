import json,sys,collections
from shapely.geometry import shape,Point,Polygon
from shapely.strtree import STRtree
from pyproj import Transformer
import numpy as np,shapely
T=Transformer.from_crs(4326,7856,always_xy=True)
M=json.load(open(sys.argv[1])); W=json.load(open(sys.argv[2]))
P=[];why=[]
for f in W['features']:
    c=np.array(f['geometry']['coordinates']); x,y=T.transform(c[:,0],c[:,1])
    P.append(Polygon(np.column_stack([x,y])).buffer(0)); why.append(f['properties']['why'])
kept=json.load(open(sys.argv[3]))['features'] if len(sys.argv)>3 else []
for f in kept:
    c=np.array(f['geometry']['coordinates']); x,y=T.transform(c[:,0],c[:,1])
    P.append(Polygon(np.column_stack([x,y])).buffer(0)); why.append('NEW ring drafted (not yet reviewed)')
ST=STRtree(P)
tot=collections.Counter(); per={}
for s,v in M.items():
    c=collections.Counter()
    for g in v['gaps']:
        q=Point(g[7],g[8]); h=[i for i in ST.query(q,predicate='within')]
        w=why[h[0]] if h else 'no block judged (block crosses the box edge / small / not in a square)'
        c[w]+=5; tot[w]+=5
    per[s]={k:round(x/1000,2) for k,x in c.most_common()}
    print(s, v['pct'], per[s])
print('ALL km', {k:round(x/1000,1) for k,x in tot.most_common()})
