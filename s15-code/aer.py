import json, os, io, time, urllib.request, numpy as np
from PIL import Image
from pyproj import Transformer
INV = Transformer.from_crs(7856, 3857, always_xy=True); ORG = 20037508.342789244
_C={}
def tile(Z,ty,tx):
    k=(Z,ty,tx)
    if k in _C: return _C[k]
    fn=f'tc/{Z}_{ty}_{tx}.jpg'
    if not os.path.exists(fn):
        u=f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{Z}/{ty}/{tx}"
        for i in range(4):
            try: open(fn,'wb').write(urllib.request.urlopen(u,timeout=20).read()); break
            except Exception: time.sleep(1+i)
    try: t=np.asarray(Image.open(fn).convert('RGB')).astype(np.int16)
    except Exception: t=None
    if len(_C)>3000: _C.clear()
    _C[k]=t; return t
def rgb(X,Y,Z=19):
    X=np.asarray(X,float);Y=np.asarray(Y,float)
    mx,my=INV.transform(X,Y); res=2*ORG/256/2**Z
    c=((mx+ORG)/res).astype(int); r=((ORG-my)/res).astype(int)
    out=np.full(X.shape+(3,),-1,np.int16)
    for tx in np.unique(c//256):
        for ty in np.unique(r//256):
            m=(c//256==tx)&(r//256==ty)
            if not m.any(): continue
            t=tile(Z,int(ty),int(tx))
            if t is not None: out[m]=t[r[m]%256,c[m]%256]
    return out
def asphalt(px):
    v=px.mean(-1); s=px.max(-1)-px.min(-1)
    ok=(px[...,0]>=0)&(v>=VMIN)
    yb=px[...,2]-(px[...,0]+px[...,1])/2
    return ok&(s<28)&(v<130)&(yb>=YB), ok
YB=-3
VMIN=25
