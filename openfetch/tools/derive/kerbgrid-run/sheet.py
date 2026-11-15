import json, sys, io, urllib.request
sys.path.insert(0,'code/openfetch/tools/derive'); import kerbgrid as kg
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor
to=Transformer.from_crs(4326,7856,always_xy=True).transform
D=kg.read_drawn('final',to); t=STRtree(D)
K=[LineString([to(*c) for c in f['geometry']['coordinates']]) for f in json.load(open(sys.argv[1]))['features']]
kt=STRtree(K); PX=450; out=sys.argv[2]
def tile(i):
    g=K[i]; c=g.centroid; M=max(g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1])+50; x0,y0=c.x-M/2,c.y-M/2
    u=f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+M},{y0+M}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image"
    import os, time
    cf=f"gridall/cache/{i}.jpg"
    if not os.path.exists(cf):
        for t_ in range(6):
            try:
                open(cf,'wb').write(urllib.request.urlopen(u,timeout=120).read()); break
            except Exception:
                time.sleep(3*(t_+1))
    im=Image.open(cf).convert('RGB'); dr=ImageDraw.Draw(im); s=PX/M
    q=lambda a,b:((a-x0)*s,(y0+M-b)*s)
    for k in t.query(g.buffer(M)): dr.line([q(*xy) for xy in D[int(k)].coords],fill=(0,255,255),width=2)
    dr.line([q(*xy) for xy in g.coords],fill=(255,0,255),width=3)
    dr.rectangle((0,0,150,16),fill=(0,0,0)); dr.text((4,2),f"G{i}  {c.x:.0f},{c.y:.0f}",fill=(255,255,0))
    return im
with ThreadPoolExecutor(6) as ex: ims=list(ex.map(tile,range(len(K))))
for s0 in range(0,len(ims),9):
    sh=Image.new('RGB',(3*PX,3*PX))
    for j,im in enumerate(ims[s0:s0+9]): sh.paste(im,((j%3)*PX,(j//3)*PX))
    sh.save(f"{out}-{s0//9+1}.jpg",quality=85)
print(len(ims))
