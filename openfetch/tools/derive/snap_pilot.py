# Usage: BOX='xmin ymin xmax ymax' python3 tools/derive/snap_pilot.py community.geojson out.geojson tile.laz [...]
# Move each community footprint (shape unchanged) onto the LiDAR building mask: best shift within +-W m (W=5), 0.25 m steps.
# 5 m, not 3: on steep Pittwater slopes Microsoft shapes sit 3-5 m off their roofs (27 Oct 2026).
W=5
import sys, json, numpy as np, laspy, glob, math
from shapely.geometry import shape, mapping
from shapely.affinity import translate
from shapely import contains_xy
src, out = sys.argv[1], sys.argv[2]; files = sys.argv[3:]
xs=[];ys=[];zs=[];cs=[]
import os
B=tuple(float(v) for v in os.environ.get("BOX","552861 6882513 553545 6883186").split())
B=(B[0]-W-2,B[1]-W-2,B[2]+W+2,B[3]+W+2)  # wider than the shift window plus the ring
for f in files:
    with laspy.open(f) as r:
        for p in r.chunk_iterator(5_000_000):
            c=np.asarray(p.classification); x=np.asarray(p.x); y=np.asarray(p.y)
            k=((c==6)|(c==2))&(x>=B[0])&(x<=B[2])&(y>=B[1])&(y<=B[3])
            xs.append(x[k]); ys.append(y[k]); zs.append(np.asarray(p.z)[k]); cs.append(c[k])
x=np.concatenate(xs); y=np.concatenate(ys); z=np.concatenate(zs); c=np.concatenate(cs)
# 2013/2019 Spatial Services tiles are GDA94 (EPSG 28356): move them to GDA2020 like roofs.py does
with laspy.open(files[0]) as r:
    try: ep=r.header.parse_crs().to_epsg()
    except Exception: ep=None
if ep and 28348<=ep<=28358:
    from pyproj import Transformer
    x,y=Transformer.from_crs(ep,ep-28348+7848,always_xy=True).transform(x,y)
    k=(x>=B[0])&(x<=B[2])&(y>=B[1])&(y<=B[3]); x,y,z,c=x[k],y[k],z[k],c[k]  # the shift moves edge points out of the grid
cell=0.5; x0=B[0]; y1=B[3]; nc=int((B[2]-B[0])/cell)+1; nr=int((B[3]-B[1])/cell)+1
bm=np.zeros((nr,nc),bool); b=c==6
bm[((y1-y[b])/cell).astype(int),((x[b]-x0)/cell).astype(int)]=True
from scipy import ndimage
bm=ndimage.binary_closing(bm,np.ones((3,3)))
gx,gy,gz=x[c==2],y[c==2],z[c==2]; bx,by,bz=x[b],y[b],z[b]
# points sorted by x, so each footprint only tests the points in its own x range (a 2 km box has tens of millions)
og,ob=np.argsort(gx),np.argsort(bx); gx,gy,gz=gx[og],gy[og],gz[og]; bx,by,bz=bx[ob],by[ob],bz[ob]
def inside(geom,X,Y,Z):
    minx,miny,maxx,maxy=geom.bounds; i,j=np.searchsorted(X,[minx,maxx])
    X,Y,Z=X[i:j],Y[i:j],Z[i:j]; k=(Y>=miny)&(Y<=maxy); X,Y,Z=X[k],Y[k],Z[k]
    return Z[contains_xy(geom,X,Y)]
def scorer(g):
    # share of the footprint's grid cells that are building cells, minus building cells just outside (1 m ring).
    # The sample points are found once; a shift only moves them (same points as testing the shifted shape).
    def pts(geom):
        minx,miny,maxx,maxy=geom.bounds
        us=np.arange(minx+cell/2,maxx,cell); vs=np.arange(miny+cell/2,maxy,cell)
        U,V=np.meshgrid(us,vs); U=U.ravel(); V=V.ravel(); k=contains_xy(geom,U,V); return U[k],V[k]
    def hits(P,dx,dy):
        ci=((P[0]+dx-x0)/cell).astype(int); ri=((y1-P[1]-dy)/cell).astype(int)
        ok=(ci>=0)&(ci<nc)&(ri>=0)&(ri<nr); return bm[ri[ok],ci[ok]]
    I=pts(g); R=pts(g.buffer(1.0).difference(g))
    def f(dx=0.0,dy=0.0):
        ins=hits(I,dx,dy); ring=hits(R,dx,dy)
        if len(ins)==0: return -1
        return ins.mean() - (ring.mean() if len(ring) else 0)
    def many(DX,DY):
        # mean building share inside minus in the ring, for every shift at once (cells outside the grid count as empty)
        def share(P):
            if len(P[0])==0: return np.zeros(len(DX))
            ci=((P[0][None,:]+DX[:,None]-x0)/cell).astype(int); ri=((y1-P[1][None,:]-DY[:,None])/cell).astype(int)
            ok=(ci>=0)&(ci<nc)&(ri>=0)&(ri<nr); v=np.zeros(ci.shape,bool); v[ok]=bm[ri[ok],ci[ok]]
            return (v.sum(1))/np.maximum(ok.sum(1),1)
        if len(I[0])==0: return np.full(len(DX),-1.0)
        return share(I)-share(R)
    f.many=many
    return f
def score(g): return scorer(g)()
F=json.load(open(src))['features']; res=[]; shifts=[]
G=[]; S=[]
for f in F:
    g=shape(f['geometry']); g=g if g.geom_type=='Polygon' else max(g.geoms,key=lambda q:q.area)
    if g.area<10: continue   # pillars, kiosks, map slivers: not a building outline worth keeping
    # all shifts scored; among those within 0.02 of the best, the smallest shift wins (a footprint smaller than its
    # roof fits equally well over a range of shifts: taking the first found biased every shift to the -3 m corner)
    # coarse 1 m grid over the window, then 0.25 m steps around the coarse picks (about 8x fewer tests than a full 0.25 m grid)
    sc=scorer(g)
    def pick(sh):
        sh=np.array(sh); v=sc.many(sh[:,0],sh[:,1]); ok=np.flatnonzero(v>=v.max()-0.02)
        return sh, v, ok
    sh,v,ok=pick([(dx,dy) for dx in np.arange(-W,W+0.01,1.0) for dy in np.arange(-W,W+0.01,1.0)])
    fine={(round(a+i,2),round(b+j,2)) for a,b in sh[ok] for i in np.arange(-0.75,0.76,0.25) for j in np.arange(-0.75,0.76,0.25) if abs(a+i)<=W and abs(b+j)<=W}
    sh,v,ok=pick(sorted(fine))
    k=ok[np.argmin(np.hypot(sh[ok,0],sh[ok,1]))]; best=(v[k],sh[k][0],sh[k][1])
    G.append(g); S.append(best)
# Microsoft's error comes from the imagery, so neighbours share it: use the median shift of well-fitting buildings within
# 60 m (its own included) instead of each building's own, which trees, shadows or a neighbour's roof can pull off.
C=np.array([[g.centroid.x,g.centroid.y] for g in G]); D=np.array([[b[1],b[2]] for b in S]); FIT=np.array([b[0] for b in S])
for i,g in enumerate(G):
    near=(np.hypot(*(C-C[i]).T)<60)&(FIT>0.5)
    dx,dy=(np.median(D[near],axis=0) if near.sum()>=3 else D[i])
    s0=S[i][0]
    g2=translate(g,dx,dy); fit=score(g2)
    if s0>fit+0.1:   # its own shift fits clearly better (e.g. a block not drawn from the same image)
        dx,dy=D[i]; g2=translate(g,dx,dy); fit=s0
    if fit<0.3:   # under 30 % of it is LiDAR roof: a tree, pool, car or a demolished building
        continue
    shifts.append(math.hypot(dx,dy))
    zb=inside(g2,bx,by,bz)
    ring=g2.buffer(4).difference(g2.buffer(1)); zg=inside(ring,gx,gy,gz)
    p={}
    if len(zb)>=10 and len(zg)>=5: p={'h_max':round(float(np.percentile(zb,98)-np.median(zg)),2),'h_mean':round(float(zb.mean()-np.median(zg)),2)}
    p['shift_m']=round(shifts[-1],2); p['fit']=round(fit,2)
    res.append({'type':'Feature','geometry':mapping(g2),'properties':p})
# duplicates: OSM and Microsoft often draw the same building, and shifting can push neighbours into each other.
# Best-fitting first; drop one that is mostly covered by an accepted footprint, trim a partial overlap off the weaker one.
from shapely.strtree import STRtree
res.sort(key=lambda r:-r['properties']['fit']); acc=[]; kept=[]; dropped=trimmed=0
for r in res:
    g=shape(r['geometry']).buffer(0)
    hit=[a for a in acc if a.intersects(g)]
    ov=sum(g.intersection(a).area for a in hit)
    if ov>0.5*g.area: dropped+=1; continue
    if ov>0.5:
        for a in hit: g=g.difference(a)
        if g.geom_type!='Polygon': g=max(g.geoms,key=lambda q:q.area)
        g=g.buffer(0.05,join_style=2).buffer(-0.05,join_style=2); trimmed+=1
        if g.is_empty or g.area<10: dropped+=1; continue   # only a sliver left after trimming
        r['geometry']=mapping(g)
    acc.append(g); kept.append(r)
res=kept
print('duplicates dropped',dropped,'overlaps trimmed',trimmed)
json.dump({'type':'FeatureCollection','features':res},open(out,'w'))
print(len(res),'kept of',len(F),'footprints, median shift %.2f m'%np.median(shifts),'with height',sum(1 for r in res if 'h_max' in r['properties']))
