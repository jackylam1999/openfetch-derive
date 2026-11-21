import json, sys, numpy as np
from shapely.geometry import LineString
from aer import rgb, asphalt
TURN=30.0; WIN=10.0; STEP=2.0; BOTH=0.7; RUN=6.0
def corner_stretches(ln):
    n=int(ln.length)
    if n<2*WIN+2: return []
    P=np.array([ln.interpolate(s).coords[0] for s in range(n+1)])
    h=np.degrees(np.arctan2(*np.diff(P,axis=0).T[::-1]))
    out=[];cur=None
    w=int(WIN)
    for i in range(w,len(h)-w):
        d=(h[i+w-1]-h[i-w]+180)%360-180
        if abs(d)>TURN:
            if cur and i-cur[1]<=2: cur[1]=i
            else:
                cur=[i,i]; out.append(cur)
    return [(max(0,a-w),min(n,b+w)) for a,b in out]
def score(ln,a,b):
    S=np.arange(a,b+0.01,STEP); both=[];fr=[]
    for s in S:
        p=ln.interpolate(s); q=ln.interpolate(min(ln.length,s+1)); p0=ln.interpolate(max(0,s-1))
        t=np.array([q.x-p0.x,q.y-p0.y]); t/=np.linalg.norm(t)+1e-9; nv=np.array([-t[1],t[0]])
        f=[]
        for side in (-1,1):
            o=np.arange(0.5,3.01,0.5)*side; ds=np.arange(-1,1.01,0.5)
            O,D=np.meshgrid(o,ds); X=p.x+nv[0]*O+t[0]*D; Y=p.y+nv[1]*O+t[1]*D
            A,ok=asphalt(rgb(X,Y)); f.append(A.sum()/ok.sum() if ok.sum()>5 else np.nan)
        fr.append(f); both.append(min(f)>BOTH if not np.isnan(f).any() else False)
    best=k=0
    for v in both:
        k=k+1 if v else 0; best=max(best,k)
    return best*STEP, fr
JD=30.0
_J=None
def near_junction(p):
    global _J
    if _J is None:
        import junc; _J=junc.junctions()
    t,pts=_J; i=t.nearest(p)
    return pts[i].distance(p)<=JD
def run(lines):
    res=[]
    for j,c in enumerate(lines):
        ln=LineString(c)
        for a,b in corner_stretches(ln):
            m=ln.interpolate((a+b)/2)
            if not near_junction(m): continue
            r,fr=score(ln,a,b)
            res.append(dict(line=j,a=a,b=b,run=r,x=round(m.x,1),y=round(m.y,1),flag=r>=RUN))
    return res
if __name__=='__main__':
    lines=json.load(open(sys.argv[1])); 
    if len(sys.argv)>3: lines=[lines[i] for i in map(int,sys.argv[3].split(','))]
    R=run(lines); json.dump(R,open(sys.argv[2],'w'))
    print(len(R),sum(r['flag'] for r in R))
