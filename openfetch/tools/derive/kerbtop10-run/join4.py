"""join4.py prev.geojson.gz rings.json[,..] ids.json sub_dir(MGA56 suburb outlines) out_dir
Adds the rings both close-up reviewers passed (ids.json) to the previous version, whole (never cut); a ring that is not simple
or touches a line already there is left out. Writes out_dir/kerbs-nsw.geojson.gz, added.json, added-ids.json."""
import sys, json, gzip, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import shapely
from shapely.geometry import LineString, shape
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
PREV, RINGS, IDS, SUBD, OUT = sys.argv[1:6]
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
prev = json.load(gzip.open(PREV, 'rt'))['features']
PG = [LineString([to(*c) for c in f['geometry']['coordinates']]) for f in prev]; PT = STRtree(PG)
roads = [(g, fh) for g, fh in ka.load_roads('in/roads') if fh not in ka.SKIP_FH]
RG = [g for g, _ in roads]; RF = [fh for _, fh in roads]; RT = STRtree(RG)
import numpy as np
SUB = [(os.path.basename(fn)[:-5].title(), shapely.unary_union([shape(f['geometry']) for f in json.load(open(fn))['features']])) for fn in glob.glob(SUBD + '/*.json')]
def road_of(g):
    P = shapely.points(np.asarray([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, max(2, int(g.length // 2)))]))
    fhs = set()
    for k in RT.query(g.buffer(15)):
        if (shapely.distance(P, RG[int(k)]) < {1: 14, 2: 11, 3: 11, 4: 8.5}.get(RF[int(k)], 9)).any(): fhs.add(RF[int(k)])
    return "main" if fhs & {1, 2, 3, 4} else "collector" if 5 in fhs else "local"
want = set(json.load(open(IDS)))
new, NG, left, ids = [], [], [], []
for fn in RINGS.split(','):
    for f in json.load(open(fn))['features']:
        if f['properties']['id'] not in want: continue
        cs = [[round(v, 7) for v in c] for c in f['geometry']['coordinates']]
        g = LineString([to(*c) for c in cs])
        if not g.is_simple or any(PG[int(k)].distance(g) < 0.5 for k in PT.query(g.buffer(1))) or any(h.distance(g) < 0.5 for h in NG):
            left.append(f['properties']['id']); continue
        NG.append(g); ids.append(f['properties']['id'])
        ar = ', '.join(n for n, s in SUB if s.intersects(g)) or min(SUB, key=lambda t: t[1].distance(g))[0]
        new.append({"type": "Feature", "properties": {"road": road_of(g), "source": "model", "length_m": round(g.length, 1), "areas": ar},
                    "geometry": {"type": "LineString", "coordinates": cs}})
os.makedirs(OUT, exist_ok=True)
json.dump({"type": "FeatureCollection", "features": prev + new}, gzip.open(OUT + '/kerbs-nsw.geojson.gz', 'wt'))
json.dump({"type": "FeatureCollection", "features": new}, open(OUT + '/added.json', 'w'))
json.dump(ids, open(OUT + '/added-ids.json', 'w'))
print('added', len(new), 'left out', left, 'km', round(sum(f['properties']['length_m'] for f in new) / 1000, 1),
      'total km', round(sum(f['properties']['length_m'] for f in prev + new) / 1000, 1))
