import json,gzip,glob,math,sys,os
import numpy as np
from shapely.geometry import shape,box,LineString,Point,MultiLineString
from shapely.strtree import STRtree
from shapely import ops
from pyproj import Transformer
IN='/tmp/claude-0/s/in'; K='/mnt/project-files/.notes/kerb-k/'
tr=Transformer.from_crs(4326,7856,always_xy=True)
def prj(g): return ops.transform(lambda x,y,z=None:tr.transform(x,y),g)
def load(p,proj):
    d=json.load(gzip.open(p) if p.endswith('gz') else open(p)); out=[]
    for f in d['features']:
        g=shape(f['geometry']); 
        if proj: g=prj(g)
        out.append((g,f['properties']))
    return out
out=[g for g,_ in load(K+'kerbs-nsw-k.geojson.gz',True)]
raw=[g for g,_ in load(IN+'/nsw-traced-raw.json',True)]
print(len(out),len(raw),file=sys.stderr)
to=STRtree(out); tw=STRtree(raw)
rc={}
def roads(x0,y0,x1,y1):
    res=[]
    for cx in range(int(x0//1000)*1000,int(x1//1000)*1000+1,1000):
        for cy in range(int(y0//1000)*1000,int(y1//1000)*1000+1,1000):
            k=(cx,cy)
            if k not in rc:
                p=f'{IN}/roads/{cx}_{cy}.json'
                rc[k]=[(shape(f['geometry']),f['properties']) for f in json.load(open(p))['features']] if os.path.exists(p) else []
            res+=rc[k]
    return res
def clipl(tree,lines,b):
    return [lines[i].intersection(b) for i in tree.query(b) if not lines[i].intersection(b).is_empty]
def pts(geoms,step=2):
    P=[]
    for g in geoms:
        for l in ([g] if g.geom_type=='LineString' else getattr(g,'geoms',[])):
            if l.geom_type!='LineString': continue
            n=max(2,int(l.length/step)+1)
            P+= [l.interpolate(i*l.length/(n-1)).coords[0] for i in range(n)]
    return np.array(P) if P else np.zeros((0,2))
def bothsided(samples,P,R=15):
    ok=0
    for (x,y,dx,dy) in samples:
        if len(P)==0: continue
        v=P-[x,y]; d=np.hypot(v[:,0],v[:,1]); m=(d<=R)&(d>=1.5)
        if not m.any(): continue
        s=dx*v[m,1]-dy*v[m,0]  # cross
        # need lateral offset >=1.5 on both sides
        if (s>1.5).any() and (s<-1.5).any(): ok+=1
    return ok
def feat(x,y,m=70):
    b=box(x-m/2,y-m/2,x+m/2,y+m/2); bb=b.buffer(20)
    o=clipl(to,out,b); Lo=sum(g.length for g in o)
    r=pts(clipl(tw,raw,bb),1.0)
    seen=0; 
    if Lo>0:
        rl=[raw[i] for i in tw.query(bb)]
        from shapely.ops import unary_union
        ru=unary_union(rl).buffer(1.5) if rl else None
        seen=sum(g.intersection(ru).length for g in o)/Lo if ru is not None else 0
    rd=[(g,p) for g,p in roads(x-60,y-60,x+60,y+60) if p.get('roadontype',1)==1]
    samples=[];mainlen=0;loc=0
    for g,p in rd:
        c=g.intersection(b)
        for l in ([c] if c.geom_type=='LineString' else getattr(c,'geoms',[])):
            if l.geom_type!='LineString' or l.length<3: continue
            fh=p.get('functionhierarchy',9)
            if fh<=4: mainlen+=l.length; continue
            loc+=l.length
            n=max(1,int(l.length/5))
            for i in range(n):
                a=l.interpolate((i+.5)*l.length/n); a2=l.interpolate(min(l.length,(i+.5)*l.length/n+1)); a1=l.interpolate(max(0,(i+.5)*l.length/n-1))
                dx,dy=a2.x-a1.x,a2.y-a1.y; h=math.hypot(dx,dy) or 1
                samples.append((a.x,a.y,dx/h,dy/h))
    P=pts(o,2)
    nb=bothsided(samples,P); nr=bothsided(samples,r)
    ns=len(samples)
    return dict(Lo=Lo,seen=seen,ns=ns,both_out=nb/ns if ns else None,both_raw=nr/ns if ns else None,main=mainlen,loc=loc)
if __name__=='__main__':
    rv=json.load(open(K+'reviewer-independent/review.json'))
    ver=json.load(open(K+'reviewer-independent/verdicts.json'))
    rr=json.load(open(K+'reviewer-independent/random-40/random.json'))['spots']
    rver=json.load(open(K+'reviewer-independent/random-40/verdicts.json'))
    rows=[]
    for v in ver:
        s=rv['sheet_spots'][v['tile']-1]; rows.append(dict(set='A',tile=v['tile'],kind=s['kind'],verdict=v['verdict'],x=s['x'],y=s['y']))
    for v in rver:
        s=rr[v['tile']-1]; rows.append(dict(set='R',tile=v['tile'],kind=s['kind'],verdict=v['verdict'],x=s['x'],y=s['y']))
    for r in rows: r.update(feat(r['x'],r['y']))
    json.dump(rows,open('/tmp/claude-0/s/w/rows.json','w'))
    print(len(rows))
