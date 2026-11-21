import json,numpy as np
from h6 import *
# vertex turn angles (abs) with same filtering
VA=[]
for g in lots:
    for p in getattr(g,'geoms',[g]):
        for r in [p.exterior]+list(p.interiors):
            c=np.array(r.coords)[:-1];n=len(c)
            for i in range(n):
                a=c[i]-c[i-1]; b=c[(i+1)%n]-c[i]
                ang=abs((np.degrees(np.arctan2(b[1],b[0])-np.arctan2(a[1],a[0]))+180)%360-180)
                if ang>=10: VA.append(ang)
VA=np.array(VA)
def mirror(m,turn,R=12):
    idx=VT.query(m.buffer(R)) if hasattr(VT,'query') else []
    best=None
    for i in idx:
        d=abs(VA[i]-abs(turn))
        if best is None or d<best[0]: best=(d,V[i].distance(m))
    return best
if __name__=='__main__':
    sel=[('s15','s07'),('s15','s33'),('s15','s36'),('datum','x05'),('kn23-b3','c29')]
    F=json.load(open('feat.json')); res={}
    for f in F:
        if f['tdist']>8 or abs(f['turn'])<45: continue
        ln=line(f['src']); tt=turns(ln,f['x'],f['y']); tt.sort(key=lambda t:t[2].distance(Point(f['x'],f['y'])))
        s,d,m=tt[0]; b=mirror(m,d)
        f['mir']=b
        res[(f['pack'],f['crop'])]=f
    ok=[f['mir'] for f in res.values() if f['v']=='OK' and f['mir']]
    print('OK n',len(ok),'angle-match<15 & <12m:',sum(1 for b in ok if b[0]<15)/len(ok), 'match<15 & <3m',sum(1 for b in ok if b[0]<15 and b[1]<3)/len(ok))
    for k in sel+[('canopy','')]:
        f=res.get(k); 
        if f: print(k,f['turn'],f['mir'])
    # kn24/s11 excluded
