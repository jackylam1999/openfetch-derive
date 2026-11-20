import urllib.error,json,io,os,sys,time,urllib.request,numpy as np
from PIL import Image,ImageDraw
from pyproj import Transformer
from shapely.geometry import LineString,Polygon
from shapely.strtree import STRtree
from concurrent.futures import ThreadPoolExecutor
new,old,out=sys.argv[1:4]; os.makedirs(out,exist_ok=True); os.makedirs('tilecache',exist_ok=True)
to=Transformer.from_crs(4326,7856,always_xy=True).transform
INV=Transformer.from_crs(7856,3857,always_xy=True); ORG=20037508.342789244
def tile(z,tx,ty):
    fn=f'tilecache/{z}_{tx}_{ty}.jpg'
    if os.path.exists(fn):
        try: return np.asarray(Image.open(fn).convert('RGB'))
        except Exception: pass
    if os.path.exists(fn+'.404'): return None
    u=f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{ty}/{tx}"
    for k in range(3):
        try:
            b=urllib.request.urlopen(u,timeout=25).read(); open(fn,'wb').write(b); return np.asarray(Image.open(io.BytesIO(b)).convert('RGB'))
        except urllib.error.HTTPError as e:
            if e.code==404: open(fn+'.404','w').close(); return None
            time.sleep(2*(k+1))
        except Exception: time.sleep(2*(k+1))
    return None
def crop(cx,cy,S,PX,Z=20):
    xs=cx-S/2+(np.arange(PX)+.5)*S/PX; ys=cy+S/2-(np.arange(PX)+.5)*S/PX
    X,Y=np.meshgrid(xs,ys); mx,my=INV.transform(X,Y); o=np.full((PX,PX,3),-1,np.int16)
    for z in (Z,Z-1,Z-2,Z-3):
        res=2*ORG/256/2**z
        c=((mx+ORG)/res).astype(int); r=((ORG-my)/res).astype(int)
        need=(o[:,:,0]<0)
        if not need.any(): break
        for tx in range(c.min()//256,c.max()//256+1):
            for ty in range(r.min()//256,r.max()//256+1):
                m=(c//256==tx)&(r//256==ty)&need
                if not m.any(): continue
                t=tile(z,tx,ty)
                if t is not None: o[m]=t[(((ORG-my[m])/res-ty*256)*1).astype(int).clip(0,255),(((mx[m]+ORG)/res-tx*256)).astype(int).clip(0,255)]
    o[o<0]=128
    return Image.fromarray(o.astype(np.uint8))
ids=set(json.load(open(os.environ.get('DRAW','draw.json')))['ids']); F=[f for f in json.load(open(new))['features'] if f['properties']['id'] in ids]
O=[Polygon([to(*c[:2]) for c in f['geometry']['coordinates']]).buffer(0) for f in json.load(open(old))['features']]
OT=STRtree(O)
D=[LineString([to(*c[:2]) for c in f['geometry']['coordinates']]) for f in json.load(open('drawn-merged.geojson'))['features'] if f['geometry']['type']=='LineString']
DT=STRtree(D)
rows=[]
def one(i):
    f=F[i]; g=LineString([to(*c[:2]) for c in f['geometry']['coordinates']]); p=Polygon(g).buffer(0)
    bar='both' if any(O[int(k)].intersection(p).area>.5*min(p.area,O[int(k)].area) for k in OT.query(p)) else 'new'
    b=g.bounds; S=max(80.0,max(b[2]-b[0],b[3]-b[1])+30); S=min(S,260.0); PX=800
    cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2; x0,y0=cx-S/2,cy-S/2; k=PX/S
    im=crop(cx,cy,S,PX); dr=ImageDraw.Draw(im)
    for q in DT.query(g.buffer(S)):
        dr.line([((x-x0)*k,(y0+S-y)*k) for x,y in D[int(q)].coords],fill=(255,255,0),width=2)
    dr.line([((x-x0)*k,(y0+S-y)*k) for x,y in g.coords],fill=(255,0,255),width=3)
    id=f['properties']['id']; fn=f'{out}/{id}.jpg'; im.save(fn,quality=80)
    return dict(id=id,src=f['properties'].get('src'),bar=bar,len_m=round(g.length),scale_m=round(S),cell=f['properties'].get('cell'),lonlat=[round(v,6) for v in Transformer.from_crs(7856,4326,always_xy=True).transform(cx,cy)])
with ThreadPoolExecutor(8) as ex: rows=list(ex.map(one,range(len(F))))
json.dump(rows,open(f'{out}/index.json','w')); print(len(rows),sum(r['bar']=='new' for r in rows),'new-bar only')
