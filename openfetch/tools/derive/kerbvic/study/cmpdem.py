import json, sys, numpy as np
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic")
import mbdem
dem = mbdem.Dem(sys.argv[2]); R = json.load(open(sys.argv[1]))
g = {}
for r in R:
    if r['w'] is None or r['c'] is None or r['c'] > 31 or r['w'] > 69 or not r['road']: continue
    g.setdefault((r['b'], r['road']), []).append(r)
out = []
for k, G in g.items():
    if len(G) < 6: continue
    P = np.array([[r['x'], r['y']] for r in G]); N = np.array([[r['nx'], r['ny']] for r in G]); C = np.array([r['c'] for r in G])
    W = np.median([r['w'] for r in G])
    dd = mbdem.side_width(dem, P, N, np.array([r['w'] for r in G]) / 2)
    s = [r['s'] for r in G if r.get('s') and 0.5 < r['s'] < min(8, .35 * W)]
    so = 2.17 * np.median(s) if len(s) >= max(5, .4 * len(G)) else None
    out.append((k[1], len(G), W, dd, so))
both = [(a, b, c, d, e) for a, b, c, d, e in out if d is not None and e is not None]
print("sides", len(out), "dem measured", sum(o[3] is not None for o in out), "osm measured", sum(o[4] is not None for o in out), "either", sum(o[3] is not None or o[4] is not None for o in out))
E = np.array([d - e for a, b, c, d, e in both]); L = np.array([b for a, b, c, d, e in both])
print("both", len(both), "dem-osm |diff| <1m %.2f <1.5m %.2f >3m %.2f median diff %.2f" % ((L*(abs(E)<1)).sum()/L.sum(), (L*(abs(E)<1.5)).sum()/L.sum(), (L*(abs(E)>3)).sum()/L.sum(), np.median(E)))
for x in both[:15]: print(x[0], x[1], round(x[2],1), round(x[3],2), round(x[4],2))
