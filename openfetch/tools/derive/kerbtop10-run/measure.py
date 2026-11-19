"""Usable-kerb measure per suburb (Jacky 19 Nov 2026: top suburbs "in usable stage").
Denominator: both sides of every built street (NSW road centrelines, functionhierarchy 2-6 = primary to local, operational, on
the ground or on a bridge) inside the suburb, sampled every 5 m. Left out: motorways (1), lanes, tracks, paths, busways and
access ways (7-11), proposed / notional / closed streets, tunnels, 15 m either side of a junction (the mouth), a side whose ray
meets another centreline before a lot (median of a divided road), a side with no lot within 45 m (no frontage).
A side is covered when an official or OpenFetch kerb line crosses the ray between the centreline and the lot line (+2 m).
    python3 measure.py in kerbs.geojson.gz official.json[,..] out.json sub,sub,..
"""
import json, sys, gzip, glob, math, collections
import numpy as np, shapely
from shapely.geometry import shape, LineString, Point
from shapely.strtree import STRtree
from pyproj import Transformer
T = Transformer.from_crs(4326, 7856, always_xy=True)
W, KF, OF, OUT, SUBS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5].split(',')
STEP, JUNC, RAY = 5.0, 15.0, 45.0


def mga(g):
    return shapely.transform(g, lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))


def lines(fc, conv):
    out = []
    for f in fc['features']:
        if not f.get('geometry'): continue
        g = shape(f['geometry']); g = mga(g) if conv else g
        for p in getattr(g, 'geoms', [g]):
            if p.geom_type == 'LineString' and p.length > 0: out.append(p)
            elif p.geom_type == 'Polygon': out.append(p.exterior)
    return out


K = lines(json.load(gzip.open(KF)), True); src = ['ofk'] * len(K)
for o in OF.split(','):
    if o:
        L = lines(json.load(open(o)), True); K += L; src += ['official'] * len(L)
KT = STRtree(K)
R, RP, seen = [], [], set()
for fn in glob.glob(f'{W}/roads/*.json'):
    for f in json.load(open(fn))['features']:
        p = f['properties']; oid = p.get('objectid') or p.get('OBJECTID')
        if oid in seen: continue
        seen.add(oid); g = shape(f['geometry'])
        for q in getattr(g, 'geoms', [g]):
            R.append(q); RP.append(p)
RT = STRtree(R)
LOT, seen = [], set()
for fn in glob.glob(f'{W}/lots/*.json'):
    for f in json.load(open(fn))['features']:
        oid = f['properties'].get('objectid') or f['properties'].get('OBJECTID')
        if oid in seen: continue
        seen.add(oid); g = shape(f['geometry'])
        if not g.is_valid: g = g.buffer(0)
        LOT += [q for q in getattr(g, 'geoms', [g]) if q.area > 1]
ST_ = [R[i] for i in range(len(R)) if RP[i].get('functionhierarchy') in (1, 2, 3, 4, 5, 6, 10) and RP[i].get('roadontype') in (1, 4, 5)]
li, si = STRtree(ST_).query(LOT, predicate='intersects'); run = collections.Counter()
for i, j in zip(li.tolist(), si.tolist()):
    inner = LOT[i].buffer(-3.0)
    if not inner.is_empty: run[i] += ST_[j].intersection(inner).length
LOT = [g for i, g in enumerate(LOT) if run[i] <= 15.0]   # road lots (a street runs inside them): road, not land (same rule as kerblot)
LT = STRtree(LOT)
print('kerbs', len(K), 'roads', len(R), 'lots', len(LOT), flush=True)


def first(ray, geoms, idx, skip=None):
    best = None
    for i in idx:
        if skip is not None and i in skip: continue
        x = ray.intersection(geoms[i].boundary if geoms[i].geom_type == 'Polygon' else geoms[i])
        if x.is_empty: continue
        d = shapely.line_locate_point(ray, shapely.get_parts(x)).min() if x.geom_type != 'Point' else ray.project(x)
        if best is None or d < best: best = d
    return best


res = {}
for s in SUBS:
    sb = json.load(open(f'{W}/sub/{s}.json'))
    S = shapely.unary_union([shape(f['geometry']) for f in sb['features']])
    tot = cov = 0; ex = collections.Counter(); gaps = []
    for ri in RT.query(S, predicate='intersects'):
        p = RP[ri]; fh = p.get('functionhierarchy'); st = p.get('operationalstatus'); on = p.get('roadontype')
        g = R[ri].intersection(S)
        for seg in getattr(g, 'geoms', [g]):
            if seg.is_empty or seg.length < 1: continue
            n = int(seg.length / STEP) + 1
            if fh not in (2, 3, 4, 5, 6): ex[f'fh{fh}'] += 2 * n * STEP; continue
            if st != 1: ex['not built (status %s)' % st] += 2 * n * STEP; continue
            if on not in (1, 2, 4, 5): ex['tunnel etc'] += 2 * n * STEP; continue
            for i in range(n):
                d = min(i * STEP + STEP / 2, seg.length); pt = seg.interpolate(d)
                a = seg.interpolate(max(d - 1, 0)); b = seg.interpolate(min(d + 1, seg.length))
                tx, ty = b.x - a.x, b.y - a.y; L = math.hypot(tx, ty)
                if L == 0: continue
                nx, ny = -ty / L, tx / L
                near = [j for j in RT.query(pt.buffer(JUNC)) if j != ri and RP[j].get('functionhierarchy') in (1, 2, 3, 4, 5, 6, 10)
                        and (RP[j].get('roadnameoid') != p.get('roadnameoid') or not p.get('roadnameoid')) and R[j].distance(pt) < JUNC]
                if near: ex['junction mouth'] += 2 * STEP; continue
                for side in (1, -1):
                    ray = LineString([(pt.x + nx * side * 0.3, pt.y + ny * side * 0.3), (pt.x + nx * side * RAY, pt.y + ny * side * RAY)])
                    if LT.query(Point(pt.x + nx * side * 0.3, pt.y + ny * side * 0.3), predicate='within').size:
                        ex['centreline inside a lot'] += STEP; continue
                    dl = first(ray, LOT, LT.query(ray))
                    if dl is None: ex['no lot within 45 m'] += STEP; continue
                    dc = first(ray, R, [j for j in RT.query(ray) if j != ri])
                    if dc is not None and dc < dl: ex['median / other carriageway'] += STEP; continue
                    tot += STEP
                    dk = first(LineString([ray.coords[0], ray.interpolate(dl + 2).coords[0]]), K, KT.query(ray))
                    if dk is not None:
                        cov += STEP
                    else:
                        gaps.append([round(pt.x, 1), round(pt.y, 1), side, round(dl, 1), fh, int(ri), p.get('roadnamebase'), round(pt.x + nx * side * (dl + 1), 1), round(pt.y + ny * side * (dl + 1), 1)])
    res[s] = {'street_side_km': round(tot / 1000, 2), 'covered_km': round(cov / 1000, 2), 'pct': round(100 * cov / tot, 1) if tot else None,
              'left_out_km': {k: round(v / 1000, 2) for k, v in ex.items()}, 'gaps': gaps}
    print(s, res[s]['street_side_km'], res[s]['covered_km'], res[s]['pct'], flush=True)
json.dump(res, open(OUT, 'w'))
