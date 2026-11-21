import json,numpy as np,sys,collections
import h8
from h6 import line
from shapely.geometry import Point,LineString
F=json.load(open('feat.json'))
odd=[('s15','s07'),('s15','s33'),('s15','s36'),('datum','x05'),('kn23-b3','c29'),('kn23-c4','c13'),('kn23-c5','c40')]
rows=[]
for f in F:
    key=(f['pack'],f['crop'])
    if f['tdist']>25: continue
    if f['v']=='ODD' and key not in odd: continue
    if f['v'] not in ('OK','ODD'): continue
    if (int(f['x']//1000),int(f['y']//1000)) and h8.ig(int(f['x']//1000),int(f['y']//1000)) is None: continue
    ln=line(f['src']); d=ln.project(Point(f['x'],f['y']))
    S,r=h8.scan(ln,d-30,d+30)
    b,seen=h8.longest_run(S,r); v=[x for x in r if x is not None]
    rows.append(dict(key=key,cls='odd' if f['v']=='ODD' else 'ok',run=b,seen=seen,n=len(S),med=round(float(np.median(v)),1) if v else None,mx=round(float(np.max(np.abs(v))),1) if v else None))
json.dump(rows,open('h8rows.json','w'))
for r in rows:
    if r['cls']=='odd': print(r)
ok=[r for r in rows if r['cls']=='ok']; print(len(ok),'ok; run>=40:',sum(r['run']>=40 for r in ok),' run>=20',sum(r['run']>=20 for r in ok),'seen<8:',sum(r['seen']<8 for r in ok))
