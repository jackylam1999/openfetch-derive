import sys,json,glob,os,pickle,collections
sys.path.insert(0,'/home/user/openfetch-derive/openfetch/tools/derive')
sys.argv=['x','--cl-band']
import kerblot as kl, kerbregular as kr, kerbcad as kc, kerbface as kf, kerbaudit as ka
from shapely.geometry import shape,LineString,Polygon
from pyproj import Transformer
to=Transformer.from_crs(4326,7856,always_xy=True).transform
lots=[g for g in kr.load_faces('in/lots') if g.geom_type=='Polygon']
streets=[];seen=set()
for fn in sorted(glob.glob('in2/roads/*.json')):
    for f in json.load(open(fn))['features']:
        p=f['properties'];o=p.get('OBJECTID',p.get('objectid'))
        if o in seen or not f.get('geometry'): continue
        seen.add(o)
        fh=p.get('functionhierarchy')
        if fh in ka.SKIP_FH or fh==7 or p.get('operationalstatus')!=1: continue
        g=shape(f['geometry'])
        for q in getattr(g,'geoms',[g]):
            if q.geom_type=='LineString' and q.length>0: streets.append((q,p.get('lanecount'),fh))
print(len(streets),'streets',flush=True)
ground=[g for g,_,_ in streets]
lots2,road_lots=kl.drop_road_lots(lots,ground)
cad=kc.Cad('in/cad',road_lots)
ctx=kf.context(streets,cad,lots2,[])
pickle.dump(None,open('/dev/null','wb'))
rings=json.load(open('r/rings_kept.json'))['features']
res={}
for f in rings:
    ring=[to(*c) for c in f['geometry']['coordinates']]
    res[f['properties']['id']]=kf.check(ring,ctx)
json.dump(res,open('r/face_eval.json','w'))
print('done')
