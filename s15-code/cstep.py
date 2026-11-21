import sys, json, glob, numpy as np, shapely
sys.path.insert(0,'/tmp/claude-0/w/s12/openfetch/tools/derive')
import kerbpcw
from kerbstate import GSTEP, GOFF, GSHARE
from shapely.geometry import shape, LineString
from shapely.strtree import STRtree
import corners
RD=None
def roads():
    global RD
    if RD is None:
        G=[];seen=set()
        for fn in glob.glob('in/roads/*.json'):
            for f in json.load(open(fn))['features']:
                p=f['properties']; o=p.get('objectid')
                if o in seen or not f.get('geometry'): continue
                seen.add(o)
                if p.get('functionhierarchy') in (8,9,10,11) or p.get('roadontype')!=1: continue
                g=shape(f['geometry']); G+=list(getattr(g,'geoms',[g]))
        RD=(G,STRtree(G))
    return RD
O=np.arange(-6,6.01,0.5)
def offsets(ground, ln, a, b, win=3):
    G,T=roads(); prof=[]
    for sd in np.arange(max(1,a),min(ln.length-1,b),2.0):
        p=ln.interpolate(sd); pa=ln.interpolate(sd-1); pb=ln.interpolate(sd+1)
        tv=np.array([pb.x-pa.x,pb.y-pa.y]); tv/=max(np.hypot(*tv),1e-9); n=np.array([-tv[1],tv[0]])
        near=[G[i] for i in T.query(p.buffer(30))]
        if not near: continue
        q=shapely.ops.nearest_points(min(near,key=lambda g:g.distance(p)),p)[0]
        if n@[q.x-p.x,q.y-p.y]<0: n=-n
        prof.append(ground.height(p.x+n[0]*O,p.y+n[1]*O))
    offs=[]
    for w in range(0,len(prof)-win+1,win):
        Z=np.stack(prof[w:w+win])
        if np.isnan(Z).all(0).mean()>0.3: continue
        Z=np.nanmedian(Z,axis=0); f=np.nan
        cand=[O[i-1] for i in range(2,len(O)-2) if not np.isnan(Z[i-2:i+3]).any() and GSTEP[0]<=Z[i-2]-Z[i]<=GSTEP[1] and abs(Z[i+2]-Z[i])<0.05]
        if cand: f=min(cand,key=abs)
        offs.append(f)
    return offs
def judge(offs):
    o=np.array(offs); fin=o[~np.isnan(o)]
    if len(o)<2 or len(fin)<0.5*len(o): return None   # no verdict
    return bool((np.abs(fin)<=GOFF).mean()<GSHARE)    # True = step mostly >3 m away: odd corner
def run(lines, gdir):
    ground=kerbpcw.Ground(gdir); res=[]
    for j,c in enumerate(lines):
        ln=LineString(c)
        if not ground.covers(np.array(c)): continue
        for a,b in corners.corner_stretches(ln):
            m=ln.interpolate((a+b)/2)
            if not corners.near_junction(m): continue
            o=offsets(ground,ln,a,b)
            res.append(dict(line=j,a=a,b=b,x=round(m.x,1),y=round(m.y,1),offs=[None if np.isnan(v) else float(v) for v in o],flag=judge(o)))
    return res
if __name__=='__main__':
    R=run(json.load(open(sys.argv[1])),sys.argv[2]); json.dump(R,open(sys.argv[3],'w'))
    import collections; print(len(R),collections.Counter(r['flag'] for r in R))
