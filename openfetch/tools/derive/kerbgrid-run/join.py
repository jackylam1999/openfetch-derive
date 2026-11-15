import sys, json, glob, gzip
sys.path.insert(0, 'code/openfetch/tools/derive')
import numpy as np, shapely
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
to = Transformer.from_crs(4326, 7856, always_xy=True).transform
A = {}; B = {}
for f in glob.glob('gridall/rev/A-*.json'): A.update(json.load(open(f)))
for f in glob.glob('gridall/rev/B-*.json'): B.update(json.load(open(f)))
grid = json.load(open('gridall/all.json'))['features']
ok = [i for i in range(len(grid)) if A.get(f'G{i}') == 'OK' and B.get(f'G{i}') == 'OK']
prev = json.load(gzip.open('/mnt/project-files/derived-layers/kerbs/nsw-2026-11-15-b/kerbs-nsw.geojson.gz'))['features']
PG = [LineString([to(*c) for c in f['geometry']['coordinates']]) for f in prev]; PT = STRtree(PG)
roads = [(g, fh) for g, fh in ka.load_roads('in/roads') if fh not in ka.SKIP_FH]
RG = [g for g, _ in roads]; RF = [fh for _, fh in roads]; RT = STRtree(RG)
def road_of(g):
    P = shapely.points(np.asarray([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, max(2, int(g.length // 2)))]))
    fhs = set()
    for k in RT.query(g.buffer(15)):
        if (shapely.distance(P, RG[int(k)]) < {1: 14, 2: 11, 3: 11, 4: 8.5}.get(RF[int(k)], 9)).any(): fhs.add(RF[int(k)])
    return "main" if fhs & {1, 2, 3, 4} else "collector" if 5 in fhs else "local"
new = []; NG = []; left = 0
for i in ok:
    cs = [[round(v, 7) for v in c] for c in grid[i]['geometry']['coordinates']]
    g = LineString([to(*c) for c in cs])
    if any(PG[int(k)].distance(g) < 0.5 for k in PT.query(g.buffer(1))) or any(h.distance(g) < 0.5 for h in NG):
        left += 1; continue
    near = min(PT.query(g.buffer(800)), key=lambda k: PG[int(k)].distance(g), default=None)
    ar = prev[int(near)]['properties']['areas'] if near is not None else prev[0]['properties']['areas']
    NG.append(g)
    new.append({"type": "Feature", "properties": {"road": road_of(g), "source": "model", "length_m": round(g.length, 1), "areas": ar},
                "geometry": {"type": "LineString", "coordinates": cs}})
json.dump({"type": "FeatureCollection", "features": prev + new}, gzip.open('gridall/kerbs-nsw-c.geojson.gz', 'wt'))
json.dump({"type": "FeatureCollection", "features": new}, open('gridall/added.json', 'w'))
print('both OK', len(ok), 'touching left out', left, 'added', len(new), 'km', round(sum(f['properties']['length_m'] for f in new) / 1000, 1),
      'total km', round(sum(f['properties']['length_m'] for f in prev + new) / 1000, 1), 'prev keys', list(prev[0]['properties']))
