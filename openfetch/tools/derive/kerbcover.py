"""How much of each shipped suburb's streets has an OpenFetch kerb at all (no truth lines needed).

  python3 -I kerbcover.py <version> <suburb,suburb,...> [workdir]

Reads the published kerb tiles (openfetch-data.pages.dev/nsw-kerbs-<version>), the NSW suburb polygon and NSW road
centrelines (function hierarchy 2-6). Samples every 5 m of centreline inside the suburb; covered = a kerb within 15 m.
Also splits the result by 1 km MGA56 squares that were drawn (> 1 km of kerb whose pieces centre there), so a coverage gap
(square never drawn) is told apart from a tracing gap (square drawn, street skipped). Prints CSV:
suburb, street km, covered km, street km inside drawn squares, covered km there.
"""
import json, os, sys, time, collections, urllib.request, urllib.parse
import numpy as np, shapely
from shapely.geometry import shape, LineString
from shapely.strtree import STRtree
from pyproj import Transformer

T = Transformer.from_crs(4326, 7856, always_xy=True)
BASE = 'https://portal.spatial.nsw.gov.au/server/rest/services'


def mga(g):
    return shapely.transform(g, lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))


def get(url, fn):
    if not os.path.exists(fn):
        req = urllib.request.Request(url, headers={'User-Agent': 'openfetch-kerbcover'})
        open(fn, 'wb').write(urllib.request.urlopen(req, timeout=120).read())
        time.sleep(0.2)
    return json.load(open(fn))


def kerbs(folder, version):
    ix = get(f'https://openfetch-data.pages.dev/nsw-kerbs-{version}/index.json', f'{folder}/index.json')
    out = []
    for c in ix['cells']:
        try:
            d = get(f'https://openfetch-data.pages.dev/nsw-kerbs-{version}/c/{c}.json', f'{folder}/{c}.json')
        except Exception:
            continue
        ox, oy = d['o']
        for _, parts in d['f']:
            for p in parts:
                x, y, pts = ox, oy, []
                for i in range(0, len(p), 2):
                    x += p[i]; y += p[i + 1]; pts.append((x / 1e7, y / 1e7))
                if len(pts) > 1:
                    out.append(mga(LineString(pts)))
    return out


def main(version, subs, work):
    os.makedirs(f'{work}/c', exist_ok=True)
    K = kerbs(f'{work}/c', version); kt = STRtree(K)
    sl = collections.Counter()
    for k in K:
        c = k.centroid; sl[(int(c.x // 1000), int(c.y // 1000))] += k.length
    drawn = {q for q, v in sl.items() if v > 1000}
    for s in subs:
        q = urllib.parse.quote(f"suburbname='{s.upper()}'")
        sb = get(f'{BASE}/NSW_Administrative_Boundaries_Theme/FeatureServer/2/query?where={q}&outSR=4326&f=geojson', f'{work}/{s}.sub.json')
        if not sb['features']:
            print(s, 'no suburb'); continue
        Wg = shapely.unary_union([shape(f['geometry']) for f in sb['features']]); x0, y0, x1, y1 = Wg.bounds; W = mga(Wg)
        F, o = [], 0
        while True:
            r = get(f'{BASE}/NSW_Transport_Theme/FeatureServer/5/query?where=functionhierarchy+in+(2,3,4,5,6)&geometry={x0},{y0},{x1},{y1}'
                    f'&geometryType=esriGeometryEnvelope&inSR=4326&outFields=functionhierarchy&outSR=4326&resultRecordCount=2000&resultOffset={o}&f=geojson',
                    f'{work}/{s}.r{o}.json')
            F += r['features']; o += 2000
            if len(r['features']) < 2000:
                break
        tot = cov = ti = ci = 0
        for f in F:
            g = mga(shape(f['geometry'])).intersection(W)
            for seg in getattr(g, 'geoms', [g]):
                if seg.is_empty or seg.length < 1:
                    continue
                for i in range(int(seg.length / 5) + 1):
                    p = seg.interpolate(min(i * 5, seg.length)); tot += 1
                    h = len(kt.query(p, predicate='dwithin', distance=15)) > 0; cov += h
                    if (int(p.x // 1000), int(p.y // 1000)) in drawn:
                        ti += 1; ci += h
        print(f'{s},{tot*5/1000:.1f},{cov*5/1000:.1f},{ti*5/1000:.1f},{ci*5/1000:.1f}', flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2].split(','), sys.argv[3] if len(sys.argv) > 3 else 'kerbcover-work')
