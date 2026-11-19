"""join3.py: 18-c plus lot-front rings both close-up reviewers passed (keep5.json) -> v19/kerbs-nsw.geojson.gz, v19/added.json"""
import sys, json, gzip, os, glob
sys.path.insert(0, '..')
import numpy as np, shapely
from shapely.geometry import LineString, shape
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
prev = json.load(gzip.open('/mnt/project-files/derived-layers/kerbs/nsw-2026-11-18-c/kerbs-nsw.geojson.gz', 'rt'))['features']
PG = [LineString([to(*c) for c in f['geometry']['coordinates']]) for f in prev]; PT = STRtree(PG)
roads = [(g, fh) for g, fh in ka.load_roads('in/roads') if fh not in ka.SKIP_FH]
RG = [g for g, _ in roads]; RF = [fh for _, fh in roads]; RT = STRtree(RG)
SUB = []
for fn in glob.glob('../kerbuse/in/sub/*.json'):
    s = shapely.unary_union([shape(f['geometry']) for f in json.load(open(fn))['features']])
    SUB.append((os.path.basename(fn)[:-5].title(), shapely.transform(s, lambda a: np.column_stack(Transformer.from_crs(4326, 7856, always_xy=True).transform(a[:, 0], a[:, 1])))))
def road_of(g):
    P = shapely.points(np.asarray([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, max(2, int(g.length // 2)))]))
    fhs = set()
    for k in RT.query(g.buffer(15)):
        if (shapely.distance(P, RG[int(k)]) < {1: 14, 2: 11, 3: 11, 4: 8.5}.get(RF[int(k)], 9)).any(): fhs.add(RF[int(k)])
    return "main" if fhs & {1, 2, 3, 4} else "collector" if 5 in fhs else "local"
new, NG, left = [], [], []
for f in json.load(open('keep5.json'))['features']:
    cs = [[round(v, 7) for v in c] for c in f['geometry']['coordinates']]
    g = LineString([to(*c) for c in cs])
    if not g.is_simple or any(PG[int(k)].distance(g) < 0.5 for k in PT.query(g.buffer(1))) or any(h.distance(g) < 0.5 for h in NG):
        left.append(f['properties']['id']); continue
    NG.append(g)
    ar = ', '.join(n for n, s in SUB if s.intersects(g)) or min(SUB, key=lambda t: t[1].distance(g))[0]
    new.append({"type": "Feature", "properties": {"road": road_of(g), "source": "model", "length_m": round(g.length, 1), "areas": ar},
                "geometry": {"type": "LineString", "coordinates": cs}, "id_": f['properties']['id']})
ids = [f.pop('id_') for f in new]
json.dump({"type": "FeatureCollection", "features": prev + new}, gzip.open('v19/kerbs-nsw.geojson.gz', 'wt'))
json.dump({"type": "FeatureCollection", "features": new}, open('v19/added.json', 'w'))
json.dump(ids, open('v19/added-ids.json', 'w'))
print('added', len(new), 'left out', left, 'km', round(sum(f['properties']['length_m'] for f in new) / 1000, 1),
      'total km', round(sum(f['properties']['length_m'] for f in prev + new) / 1000, 1))
