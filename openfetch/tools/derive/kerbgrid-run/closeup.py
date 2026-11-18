"""Close-up sheets: one block per 800 px tile, 2x2 per sheet. Draws the block (magenta), other drafted blocks (cyan thin),
official/drawn kerbs (yellow), Overture footprints (thin white outline). args: blocks.json outprefix"""
import json, sys, os, time, urllib.request
from pyproj import Transformer
from PIL import Image, ImageDraw
from shapely.geometry import LineString, shape, Polygon
from shapely.strtree import STRtree
from concurrent.futures import ThreadPoolExecutor
to=Transformer.from_crs(4326,7856,always_xy=True).transform
F=json.load(open(sys.argv[1]))['features']; out=sys.argv[2]; PX=800
G=[LineString([to(*c) for c in f['geometry']['coordinates']]) for f in F]; GT=STRtree(G)
O=[LineString([to(*c[:2]) for c in f['geometry']['coordinates']]) for f in json.load(open('off/official.json'))['features']]
O+= [LineString([to(*c[:2]) for c in f['geometry']['coordinates']]) for f in json.load(open('final/0_0.json'))['features']]
OT=STRtree(O)
def img(x0,y0,M,cf):
    u=f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+M},{y0+M}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image"
    for t in range(6):
        if os.path.exists(cf) and open(cf,'rb').read(2)==b'\xff\xd8': break
        try: open(cf,'wb').write(urllib.request.urlopen(u,timeout=120).read())
        except Exception: time.sleep(min(30,3*(t+1)))
        else: time.sleep(1)
    try: return Image.open(cf).convert('RGB')
    except Exception: return Image.new('RGB',(PX,PX),(90,90,90))
def tile(i):
    g=G[i]; b=g.bounds; M=max(b[2]-b[0],b[3]-b[1])+60; c=g.centroid; x0,y0=c.x-M/2,c.y-M/2
    im=img(round(x0,1),round(y0,1),round(M,1),f"cache/cu-{F[i]['properties']['id']}.jpg"); dr=ImageDraw.Draw(im); s=PX/M
    q=lambda a,b_:((a-x0)*s,(y0+M-b_)*s)
    for k in OT.query(g.buffer(M)): dr.line([q(*p) for p in O[int(k)].coords],fill=(255,230,0),width=2)
    for k in GT.query(g.buffer(M)):
        if int(k)!=i: dr.line([q(*p) for p in G[int(k)].coords],fill=(0,220,255),width=1)
    dr.line([q(*p) for p in g.coords],fill=(255,0,255),width=3)
    dr.rectangle((0,0,230,22),fill=(0,0,0)); dr.text((5,5),f"{F[i]['properties']['id']}   {M:.0f} m across",fill=(255,255,0))
    return im
with ThreadPoolExecutor(4) as ex: ims=list(ex.map(tile,range(len(G))))
for s0 in range(0,len(ims),4):
    sh=Image.new('RGB',(2*PX,2*PX))
    for j,im in enumerate(ims[s0:s0+4]): sh.paste(im,((j%2)*PX,(j//2)*PX))
    sh.save(f"{out}-{s0//4+1:03d}.jpg",quality=82)
print(len(ims))
