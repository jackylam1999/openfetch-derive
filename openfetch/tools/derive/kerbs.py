#!/usr/bin/env python3
"""Kerb lines from classified LiDAR ground points (class 2) and NSW cadastre lots, for the "Kerbs (OpenFetch)" layer.

Usage: python3 tools/derive/kerbs.py out.geojson xmin ymin xmax ymax lots.geojson tiles.laz... [--roads roads.geojson] [--ground cache.npz]

Kerbs lie in the road reserve (the space between cadastre lots), roughly parallel to the lot frontages. Every 1 m along each
frontage a 2 m wide profile runs up to 8 m into the reserve; the kerb is the strongest 0.06-0.30 m drop from the verge to a
flat road surface, most of it within 0.4 m. Positions are then smoothed along the frontage (running median over 7 m, outliers
over 0.35 m dropped) and joined into lines across gaps up to 6 m (driveway laybacks, trees). Pieces under 4 m are dropped.
lots.geojson comes from lots.py; --roads (roads.py) keeps only kerbs within 12 m of a street centreline. --ground caches the box's ground points so a rerun skips reading the tiles.
Output grid and datum = the tile's (NSW: GDA2020 MGA, AHD). Properties: length, step (median, m), z (road level, AHD).
"""
import sys, json, os
import numpy as np
import laspy
from scipy.spatial import cKDTree
from shapely.geometry import LineString, shape, mapping, box as sbox
from shapely.ops import unary_union
from shapely import contains_xy

RISE_MIN, RISE_MAX, BEND, FLAT = 0.04, 0.40, 0.03, 0.08
REACH, HALF, BIN, SPACING = 11.0, 2.5, 0.1, 1.0
WIN, OUTLIER, GAP, MIN_LEN, ROAD_NEAR = 9, 0.35, 12.0, 4.0, 12.0


def ground_points(paths, x0, y0, x1, y1, cache=None):
    if cache and os.path.exists(cache):
        d = np.load(cache)
        return d["x"], d["y"], d["z"]
    xs, ys, zs = [], [], []
    for p in paths:
        with laspy.open(p) as f:
            for ch in f.chunk_iterator(5_000_000):
                c = np.asarray(ch.classification)
                x, y = np.asarray(ch.x), np.asarray(ch.y)
                k = (c == 2) & (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
                xs.append(x[k]); ys.append(y[k]); zs.append(np.asarray(ch.z)[k])
    x, y, z = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
    if cache:
        np.savez(cache, x=x, y=y, z=z)
    return x, y, z


def frontages(lots, clip):
    road = clip.difference(unary_union(lots).buffer(0.05)).buffer(-0.05)
    edges = road.boundary.intersection(clip.buffer(-0.5))
    out = []
    for g in getattr(edges, "geoms", [edges]):
        if g.geom_type == "LineString" and g.length >= MIN_LEN:
            out.append(g)
    return road, out


def profile(o, z):
    """Kerb line (gutter at the kerb foot) along one profile: (offset, verge rise, road level) or None."""
    nb = int(REACH / BIN) + 1
    b = np.clip((o / BIN).astype(int), 0, nb - 1)
    C = np.r_[0, np.cumsum(np.bincount(b, minlength=nb))]; S = np.r_[0, np.cumsum(np.bincount(b, z, minlength=nb))]
    def mean(lo, hi, need=2):
        lo = np.clip(lo, 0, nb); hi = np.clip(hi, 0, nb)
        n = C[hi] - C[lo]
        return np.where(n >= need, (S[hi] - S[lo]) / np.maximum(n, 1), np.nan)
    f = lambda m: int(round(m / BIN))
    p = np.arange(f(0.6), nb - f(2.0))
    gut = mean(p - f(0.25), p + f(0.25), 3)
    verge = mean(p - f(1.2), p - f(0.6), 3) - gut
    road = mean(p + f(1.0), p + f(2.0), 3) - gut
    far = mean(p + f(2.0), p + f(3.0), 3) - gut
    bend = verge / 0.9 - road / 1.5
    ok = (verge >= RISE_MIN) & (verge <= RISE_MAX) & (road >= -0.02) & (road <= 0.15) & (bend >= BEND) & (np.abs(far - road) < FLAT)
    if not np.any(ok):
        return None
    k = int(np.nanargmax(np.where(ok, verge + road, -1)))
    return lowest(o, z, p[k] * BIN + BIN / 2), float(verge[k]), float(gut[k])


def lowest(o, z, p0):
    """Refine the kerb line: lowest point of the gutter near p0, then back towards the verge to half the verge rise."""
    best, q0 = np.inf, p0
    for q in np.arange(p0 - 0.8, p0 + 0.41, 0.05):
        m = np.abs(o - q) <= 0.2
        if m.sum() >= 2 and z[m].mean() < best:
            best, q0 = z[m].mean(), q
    top = z[(o > q0 - 1.2) & (o < q0 - 0.6)]
    if len(top) < 2:
        return q0
    half = (best + top.mean()) / 2
    for q in np.arange(q0, q0 - 0.81, -0.05):
        m = np.abs(o - q) <= 0.15
        if m.sum() >= 1 and z[m].mean() >= half:
            return q
    return q0


def runmed(v, win):
    h = win // 2; out = np.full(len(v), np.nan)
    for i in range(len(v)):
        seg = v[max(0, i - h): i + h + 1]; seg = seg[~np.isnan(seg)]
        if len(seg) >= 3:
            out[i] = np.median(seg)
    return out


def kerbs_along(edge, road, tree, x, y, z):
    n = int(edge.length / SPACING)
    t = (np.arange(n) + 0.5) * SPACING
    P = np.array([edge.interpolate(v).coords[0] for v in t])
    A = np.array([edge.interpolate(max(v - 1, 0)).coords[0] for v in t]); B = np.array([edge.interpolate(min(v + 1, edge.length)).coords[0] for v in t])
    U = B - A; U /= np.linalg.norm(U, axis=1)[:, None] + 1e-9
    N = np.c_[-U[:, 1], U[:, 0]]
    flip = ~contains_xy(road, P[:, 0] + 0.5 * N[:, 0], P[:, 1] + 0.5 * N[:, 1])
    N[flip] *= -1
    off = np.full(n, np.nan); st = np.full(n, np.nan); zr = np.full(n, np.nan)
    for i in range(n):
        c = P[i] + N[i] * REACH / 2
        idx = tree.query_ball_point(c, np.hypot(REACH / 2, HALF))
        if len(idx) < 10:
            continue
        d = np.c_[x[idx], y[idx]] - P[i]
        s, o = d @ U[i], d @ N[i]
        k = (np.abs(s) <= HALF) & (o >= 0) & (o < REACH)
        r = profile(o[k], z[idx][k])
        if r:
            off[i], st[i], zr[i] = r
    med = runmed(off, WIN)
    good = ~np.isnan(off) & (np.abs(off - med) <= OUTLIER)
    off = np.where(good, off, np.nan)
    sm = runmed(off, 5)
    use = good & ~np.isnan(sm)
    lines, cur = [], []
    for i in np.nonzero(use)[0]:
        if cur and t[i] - t[cur[-1]] > GAP:
            lines.append(cur); cur = []
        cur.append(i)
    if cur:
        lines.append(cur)
    res = []
    for ids in lines:
        ids = np.array(ids)
        pts = P[ids] + N[ids] * sm[ids][:, None]
        if len(pts) >= 2:
            res.append((LineString(pts), float(np.median(st[ids])), float(np.median(zr[ids]))))
    return res


def main():
    a = sys.argv[1:]
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    cache, roads = opt("--ground"), opt("--roads")
    pos = [s for k, s in enumerate(a) if not s.startswith("--") and (k == 0 or a[k - 1] not in ("--ground", "--roads"))]
    out, (bx0, by0, bx1, by1), lots, tiles = pos[0], list(map(float, pos[1:5])), pos[5], pos[6:]
    m = REACH + 2
    x, y, z = ground_points(tiles, bx0 - m, by0 - m, bx1 + m, by1 + m, cache)
    tree = cKDTree(np.c_[x, y])
    clip = sbox(bx0, by0, bx1, by1)
    polys = [shape(f["geometry"]) for f in json.load(open(lots))["features"]]
    road, edges = frontages(polys, clip.buffer(m - 1, join_style=2))
    if roads:
        rl = [shape(f["geometry"]) for f in json.load(open(roads))["features"]]
        if rl:
            clip = clip.intersection(unary_union(rl).buffer(ROAD_NEAR))
    feats = []
    for e in edges:
        for l, st, zr in kerbs_along(e, road, tree, x, y, z):
            g = l.simplify(0.1).intersection(clip)
            for gg in getattr(g, "geoms", [g]):
                if gg.geom_type == "LineString" and gg.length >= MIN_LEN:
                    feats.append({"type": "Feature", "geometry": mapping(gg), "properties": {
                        "length": round(gg.length, 1), "step": round(st, 3), "z": round(zr, 2)}})
    inb = (x >= bx0) & (x < bx1) & (y >= by0) & (y < by1)
    dens = inb.sum() / ((bx1 - bx0) * (by1 - by0))
    json.dump({"type": "FeatureCollection", "name": "Kerbs (OpenFetch)", "ground_density": round(float(dens), 2),
               "features": feats}, open(out, "w"))
    print(f"{len(feats)} kerb lines, {sum(f['properties']['length'] for f in feats) / 1000:.2f} km, "
          f"ground {dens:.1f} pts/m2 -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
