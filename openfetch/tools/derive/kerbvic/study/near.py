import json,sys,numpy as np
from pyproj import Transformer
TO=Transformer.from_crs(4326,7855,always_xy=True).transform
F=json.load(open(sys.argv[1]))["features"]; rid=sys.argv[2]; x,y=float(sys.argv[3]),float(sys.argv[4])
f=[f for f in F if f["properties"]["id"]==rid][0]
c=np.array([TO(*p) for p in f["geometry"]["coordinates"]])
d=np.hypot(c[:,0]-x,c[:,1]-y); idx=np.where(d<40)[0]
for i in idx: print(i, round(c[i,0]-x,1), round(c[i,1]-y,1))
print(f["properties"])
