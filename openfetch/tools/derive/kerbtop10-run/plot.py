"""plot.py in kerbs.geojson.gz official m.json suburb out.png  (overview: lots grey, streets thin, kerbs blue, gap sides red)"""
import json, sys, gzip, glob
import numpy as np, shapely, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape, box
from pyproj import Transformer
T = Transformer.from_crs(4326, 7856, always_xy=True)
W, KF, OF, M, S, OUT = sys.argv[1:7]
sb = shapely.unary_union([shape(f['geometry']) for f in json.load(open(f'{W}/sub/{S}.json'))['features']])
x0, y0, x1, y1 = sb.bounds; B = box(x0 - 50, y0 - 50, x1 + 50, y1 + 50)
fig, ax = plt.subplots(figsize=(max(6, (x1 - x0) / 120), max(6, (y1 - y0) / 120)), dpi=100)
for fn in glob.glob(f'{W}/lots/*.json'):
    for f in json.load(open(fn))['features']:
        g = shape(f['geometry'])
        if not g.intersects(B): continue
        for p in getattr(g, 'geoms', [g]):
            ax.fill(*p.exterior.xy, color='#e6e6e6', lw=0)
for fn in glob.glob(f'{W}/roads/*.json'):
    for f in json.load(open(fn))['features']:
        g = shape(f['geometry'])
        if not g.intersects(B): continue
        fh = f['properties'].get('functionhierarchy')
        for p in getattr(g, 'geoms', [g]):
            ax.plot(*p.xy, color='#999' if fh in (2, 3, 4, 5, 6) else '#ddd', lw=0.6)
for fn, col in ((KF, '#1565c0'), (OF, '#2e7d32')):
    if not fn: continue
    d = json.load(gzip.open(fn)) if fn.endswith('.gz') else json.load(open(fn))
    for f in d['features']:
        g = shapely.transform(shape(f['geometry']), lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))
        if not g.intersects(B): continue
        for p in getattr(g, 'geoms', [g]):
            ax.plot(*(p.exterior.xy if p.geom_type == 'Polygon' else p.xy), color=col, lw=1.0)
ax.plot(*sb.exterior.xy if sb.geom_type == 'Polygon' else max(sb.geoms, key=lambda q: q.area).exterior.xy, color='k', lw=0.8, ls='--')
G = json.load(open(M))[S]['gaps']
ax.scatter([g[0] for g in G], [g[1] for g in G], s=3, c='red', zorder=5)
ax.set_xlim(x0 - 50, x1 + 50); ax.set_ylim(y0 - 50, y1 + 50); ax.set_aspect('equal'); ax.axis('off')
plt.savefig(OUT, bbox_inches='tight')
