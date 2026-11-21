import json,glob,os,numpy as np
from shapely.geometry import LineString,Point,box
from shapely.strtree import STRtree
IG={}
def ig(i,j):
    if (i,j) not in IG:
        fn=None
        for d in glob.glob('/tmp/claude-0/ig/*/'):
            if os.path.exists(d+'%d_%d.npz'%(i,j)): fn=d+'%d_%d.npz'%(i,j)
        IG[(i,j)]=np.load(fn)['i'] if fn else None
    return IG[(i,j)]
def samp(X,Y):
    X=np.asarray(X,float);Y=np.asarray(Y,float);out=np.full(X.shape,np.nan)
    I=np.floor(X/1000).astype(int);J=np.floor(Y/1000).astype(int)
    for i,j in set(zip(I.ravel().tolist(),J.ravel().tolist())):
        g=ig(i,j)
        if g is None: continue
        k=(I==i)&(J==j); c=((X[k]-i*1000)/.5).astype(int).clip(0,1999); r=((Y[k]-j*1000)/.5).astype(int).clip(0,1999)
        v=g[r,c].astype(float); v[v>=255]=np.nan; out[k]=v
    return out
CL=[]
for f in glob.glob('in/roads/*.json'):
    for g in json.load(open(f))['features']:
        p=g['properties']
        if (p.get('functionhierarchy') or 9)<=7 and p.get('roadontype',1)==1 and g['geometry']['type']=='LineString': CL.append(LineString(g['geometry']['coordinates']))
TREE=STRtree(CL)
CAL={}
def cal(i,j):
    if (i,j) in CAL: return CAL[(i,j)]
    v=[]
    for k in TREE.query(box(i*1000,j*1000,i*1000+1000,j*1000+1000)):
        L=CL[k]; s=np.arange(0,L.length,1.0); P=np.array([L.interpolate(t).coords[0] for t in s])
        m=(P[:,0]//1000==i)&(P[:,1]//1000==j)
        if m.any(): q=samp(P[m,0],P[m,1]); v+=list(q[np.isfinite(q)])
    r=(np.median(v),max(2.0,1.4826*np.median(np.abs(np.array(v)-np.median(v))))) if len(v)>=100 else None
    CAL[(i,j)]=r; return r
DT=0.25
def road(X,Y):
    I=np.floor(X/1000).astype(int);J=np.floor(Y/1000).astype(int);a=samp(X,Y);out=np.full(X.shape,np.nan)
    for i,j in set(zip(I.tolist(),J.tolist())):
        c=cal(i,j); k=(I==i)&(J==j)
        if c is None: continue
        m,s=c; ok=np.isfinite(a[k]); sub=out[k]; sub[ok]=(np.abs(a[k][ok]-m)<=2.5*s).astype(float); out[k]=sub
    return out
def offset(Q):
    """line point -> (offset m: dist of line from centreline minus walked road edge) or None"""
    near=TREE.query(Point(Q).buffer(25))
    if len(near)==0: return None
    k=min(near,key=lambda k:CL[k].distance(Point(Q)))
    C=np.array(CL[k].interpolate(CL[k].project(Point(Q))).coords[0]); v=Q-C; dq=np.hypot(*v)
    if dq<1.5: return None
    u=v/dq; tt=np.arange(0,dq+6,DT); X=C[0]+u[0]*tt; Y=C[1]+u[1]*tt
    rc=road(X,Y)
    if np.isfinite(rc).mean()<0.3: return None
    n=int(1/DT); sm=np.array([np.nanmean(rc[max(0,i-n//2):i+n//2+1]) if np.isfinite(rc[max(0,i-n//2):i+n//2+1]).any() else np.nan for i in range(len(rc))])
    for i in range(int(1.5/DT),len(sm)-n):
        if np.all(np.nan_to_num(sm[i:i+n],nan=1.0)<0.5): return float(dq-tt[i])
    return None
def scan(ln,s0=0,s1=None,step=2.0):
    s1=ln.length if s1 is None else s1
    S=np.arange(max(0,s0),min(ln.length,s1),step); res=[]
    for s in S:
        res.append(offset(np.array(ln.interpolate(s).coords[0])))
    return S,res
def longest_run(S,res,thr=3.0,step=2.0):
    best=cur=0;seen=0
    for r in res:
        if r is None: cur=0; continue
        seen+=1
        if abs(r)>thr: cur+=step; best=max(best,cur)
        else: cur=0
    return best,seen
def win_runs(v,W=10,ST=5,THR=3.0,MINSEEN=5):
    """v: offsets (nan = none) every 2 m. Windows of W samples (20 m) every ST samples (10 m); a window is off when its median |off|>THR and >=MINSEEN seen.
    Returns (longest run of consecutive off windows, list of (start_sample,end_sample) of runs>=3 windows)."""
    flags=[]
    for a in range(0,max(0,len(v)-W+1),ST):
        x=v[a:a+W]; ok=np.isfinite(x)
        flags.append((a,bool(ok.sum()>=MINSEEN and abs(np.nanmedian(x))>THR)))
    best=cur=0;runs=[];st=None
    for a,f in flags+[(None,False)]:
        if f:
            if cur==0: st=a
            cur+=1; best=max(best,cur)
        else:
            if cur>=3: runs.append((st,last+W))
            cur=0
        last=a
    return best,runs
