import json,gzip,sys
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
to=Transformer.from_crs(4326,7856,always_xy=True).transform
def rd(p):
    op=gzip.open if open(p,'rb').read(2)==b'\x1f\x8b' else open
    return [LineString([to(*c[:2]) for c in f['geometry']['coordinates']]) for f in json.load(op(p,'rt'))['features']]
A=rd(sys.argv[1]);B=rd(sys.argv[2])
print('mine',len(A),round(sum(g.length for g in A)/1000,1),'ref',len(B),round(sum(g.length for g in B)/1000,1))
T=STRtree(B); same=sum(1 for g in A if any(B[int(k)].hausdorff_distance(g)<0.01 for k in T.query(g)))
print('identical rings',same)
