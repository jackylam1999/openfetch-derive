import json,glob,numpy as np
from shapely.geometry import shape,LineString,Point,MultiPoint
from shapely.strtree import STRtree
import shapely
lots=[];seen=set()
for fn in sorted(glob.glob('in/lots/*.json')):
    for f in json.load(open(fn))['features']:
        o=f['properties'].get('OBJECTID')
        if o in seen or not f.get('geometry'): continue
        seen.add(o); g=shape(f['geometry'])
        if g.area>5e5: continue
        lots.append(g)
print('lots',len(lots))
bnd=[g.boundary for g in lots]
BT=STRtree(bnd)
V=[];
for g in lots:
    for p in getattr(g,'geoms',[g]):
        for r in [p.exterior]+list(p.interiors):
            c=np.array(r.coords)[:-1]
            # drop collinear vertices (<5 deg turn)
            n=len(c)
            for i in range(n):
                a=c[i]-c[i-1]; b=c[(i+1)%n]-c[i]
                ang=abs((np.degrees(np.arctan2(b[1],b[0])-np.arctan2(a[1],a[0]))+180)%360-180)
                if ang>=10: V.append(Point(c[i]))
VT=STRtree(V); print('vertices',len(V))
H=json.load(open('h.json'));N=json.load(open('n20.json'));D=json.load(open('drop.json'))
def line(src):
    k,i=src
    return LineString({'h':H,'n20':N}[k][i] if k!='drop' else D[str(i)])
def turns(ln,cx,cy,R=15,TURN=20,WIN=10):
    n=int(ln.length)
    if n<2*WIN: return []
    P=np.array([ln.interpolate(s).coords[0] for s in range(n+1)])
    h=np.degrees(np.arctan2(*np.diff(P,axis=0).T[::-1]))
    out=[]
    for i in range(0,len(h)-WIN):
        d=(h[i+WIN-1]-h[i]+180)%360-180
        if abs(d)>TURN:
            m=P[i+WIN//2]
            if np.hypot(m[0]-cx,m[1]-cy)<=R+10: out.append((i+WIN//2,d))
    # merge consecutive -> take max
    res=[];cur=[]
    for s,d in out:
        if cur and s-cur[-1][0]<=2: cur.append((s,d))
        else:
            if cur: res.append(cur)
            cur=[(s,d)]
    if cur: res.append(cur)
    r=[]
    for c in res:
        s,d=max(c,key=lambda t:abs(t[1])); m=ln.interpolate(s)
        r.append((s,d,m))
    return r
def feats(ln,s,m):
    f1=V[VT.nearest(m)].distance(m)
    seg=[ln.interpolate(t) for t in np.arange(max(0,s-8),min(ln.length,s+8)+.1,1.0)]
    P=shapely.points([(p.x,p.y) for p in seg])
    idx=BT.nearest(P); d=shapely.distance(P,np.array(bnd,dtype=object)[idx])
    f2=float((d<0.6).mean()); f2b=float(np.median(d))
    return round(f1,1),round(f2,2),round(f2b,1)
if __name__=='__main__':
    L=json.load(open('labels-raw.json')); out=[]
    for l in L:
        try: ln=line(l['src'])
        except Exception as e: continue
        tt=turns(ln,l['x'],l['y'])
        if not tt: continue
        tt.sort(key=lambda t:Point(t[2]).distance(Point(l['x'],l['y'])))
        s,d,m=tt[0]; dist=m.distance(Point(l['x'],l['y']))
        f=feats(ln,s,m)
        out.append({**l,'turn':round(d),'tdist':round(dist,1),'f1':f[0],'f2':f[1],'f2b':f[2]})
    json.dump(out,open('feat.json','w')); print(len(out))
