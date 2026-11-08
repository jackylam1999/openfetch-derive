#!/usr/bin/env python3
"""Fill kerbs the model could not see (cars, trees, shadow) the way a person would (Jacky 1 Nov 2026): along a street the kerb
runs parallel to the property line at the same verge width, so where a stretch of kerb is missing it is drawn from the lot
frontage, set back by the verge width measured on the visible kerb of the same frontage (or, failing that, the same street).

fill(lines, lots, roads, **opts) -> new lines (shapely LineStrings, metres) to add to the kerb layer; the drawn lines are kept.
  lines  the model's kerb lines; lots  lot polygons; roads  official road centrelines (may be empty)
  opts   step (sample spacing, m), wmin/wmax (verge widths believed), seen (a frontage point counts as having kerb when a
         drawn line is this close to its set-back point), gap (no kerb within this of the set-back point = missing),
         maxgap (longest stretch filled, m), ends (2 = kerb seen on both sides of the gap, 1 = on one side),
         need (share of a frontage run with kerb seen before its verge width is trusted), turn (degrees: a frontage run ends
         at a corner this sharp)

Command line (scores a box with and without the fill, no GPU):
  python3 kerbfill.py derived.geojson lots.geojson roads.geojson kerbs.geojson xmin ymin xmax ymax [opts as JSON]
"""
import sys, json
import numpy as np
import shapely
from shapely.geometry import LineString, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

OPTS = {"step": 1.0, "wmin": 1.0, "wmax": 8.0, "seen": 1.0, "gap": 2.0, "maxgap": 40.0, "ends": 2, "need": 0.3, "turn": 30.0,
        "minrun": 8.0, "road": 2.0, "spread": 1.0}


def blocks(lots):
    """Block outlines: the lots merged (slivers between neighbouring lots closed), as rings with the block on the left."""
    u = unary_union([g.buffer(0.3) for g in lots]).buffer(-0.3)
    rings = []
    for p in getattr(u, "geoms", [u]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        p = shapely.geometry.polygon.orient(p, 1.0)
        rings += [p.exterior] + list(p.interiors)
    return rings


def samples(ring, step):
    """Points every step m along a ring, the unit normal pointing away from the block (toward the road), and the tangent."""
    n = max(int(ring.length // step), 4)
    t = np.linspace(0, ring.length, n, endpoint=False)
    P = np.array([ring.interpolate(v).coords[0] for v in t])
    T = np.roll(P, -1, 0) - np.roll(P, 1, 0); T /= np.maximum(np.hypot(T[:, 0], T[:, 1]), 1e-9)[:, None]
    N = np.column_stack([T[:, 1], -T[:, 0]])  # right of travel = outside the block (block on the left)
    return P, N, T


def runs(T, step, turn):
    """Split a ring's samples into straight-ish frontage runs at corners (direction change over 3 m above turn degrees)."""
    k = max(int(round(3 / step)), 1)
    a = np.degrees(np.arccos(np.clip((T * np.roll(T, -k, 0)).sum(1), -1, 1)))
    cut = a > turn
    lab = np.zeros(len(T), int); r = 0
    for i in range(len(T)):
        if cut[i] and (i == 0 or not cut[i - 1]):
            r += 1
        lab[i] = -1 if cut[i] else r
    if len(T) and lab[0] >= 0 and lab[-1] >= 0 and not cut[0] and not cut[-1]:
        lab[lab == lab[-1]] = lab[0]  # the run that wraps past the ring's start is one run
    return lab


def nearest(tree, geoms, P):
    """Distance from each point to the nearest line, and that nearest point."""
    pts = shapely.points(P); idx = tree.nearest(pts)
    sl = shapely.shortest_line(pts, np.asarray(geoms, dtype=object)[idx])
    Q = shapely.get_coordinates(shapely.get_point(sl, 1))
    return np.hypot(*(Q - P).T), Q


def fill(lines, lots, roads=(), **kw):
    o = {**OPTS, **kw}
    lines = [l for l in lines if l.length > 0]
    if not lines or not lots:
        return []
    tree = STRtree(lines); rtree = STRtree(list(roads)) if len(roads) else None
    lot_tree = STRtree(lots)
    out = []
    for ring in blocks(lots):
        if ring.length < o["minrun"]:
            continue
        P, N, T = samples(ring, o["step"])
        lab = runs(T, o["step"], o["turn"])
        d, Q = nearest(tree, lines, P)
        V = Q - P; along = (V * N).sum(1)
        w = np.where((d >= o["wmin"]) & (d <= o["wmax"]) & (along > 0.8 * d), d, np.nan)  # kerb seen out from the frontage
        rd = nearest(rtree, list(roads), P)[0] if rtree is not None else np.full(len(P), np.inf)
        for r in set(lab[lab >= 0]):
            m = lab == r
            if m.sum() * o["step"] < o["minrun"]:
                continue
            idx = np.flatnonzero(m); wr = w[m]; ok = ~np.isnan(wr)
            if ok.mean() < o["need"]:
                continue
            ok &= np.abs(np.nan_to_num(wr) - np.nanmedian(wr)) <= o["spread"]  # a median strip or a far kerb is not this verge
            if ok.sum() < 3:
                continue
            k = np.arange(len(wr))
            W = np.interp(k, k[ok], wr[ok])  # verge carried from the kerb before the gap to the kerb after it
            S = P[m] + N[m] * W[:, None]
            ds = nearest(tree, lines, S)[0]
            seen, miss = ds <= o["seen"], ds > o["gap"]
            miss &= rd[m] > W + o["road"]  # the set-back point must stay off the road centreline
            if miss.any():
                miss &= np.array([not len(lot_tree.query(p, predicate="intersects")) for p in shapely.points(S)])
            out += stretches(S, idx, miss, seen, o)
    return out


def stretches(S, idx, miss, seen, o):
    """Consecutive missing set-back points (in ring order) -> lines, kept when short enough and bounded by seen kerb."""
    res = []; n = len(miss); i = 0
    order = np.argsort(idx)  # idx is ascending already; kept explicit for clarity
    miss, seen, S, idx = miss[order], seen[order], S[order], idx[order]
    while i < n:
        if not miss[i]:
            i += 1; continue
        j = i
        while j + 1 < n and miss[j + 1] and idx[j + 1] == idx[j] + 1:
            j += 1
        L = (j - i + 1) * o["step"]
        before = i > 0 and seen[max(i - 3, 0):i].any() and idx[i - 1] == idx[i] - 1
        after = j + 1 < n and seen[j + 1:j + 4].any() and idx[j + 1] == idx[j] + 1
        if o["step"] * 2 <= L <= o["maxgap"] and int(bool(before)) + int(bool(after)) >= o["ends"]:
            a, b = max(i - 1, 0), min(j + 1, n - 1)
            if b > a:
                res.append(LineString(S[a:b + 1]))
        i = j + 1
    return res


def load(path):
    return [shape(f["geometry"]) for f in json.load(open(path))["features"] if f.get("geometry")]


def flat(gs, kind):
    return [p for g in gs for p in getattr(g, "geoms", [g]) if p.geom_type == kind and not p.is_empty]


def fill_file(der, lots, roads, **kw):
    """Add the filled lines to a derived.geojson in place (same kerb layer, Jacky 1 Nov: no separate 'estimated' layer)."""
    fc = json.load(open(der))
    add = fill(flat([shape(f["geometry"]) for f in fc["features"] if f.get("geometry")], "LineString"),
               flat(load(lots), "Polygon"), flat(load(roads), "LineString") if roads else [], **kw)
    fc["features"] += [{"type": "Feature", "geometry": shapely.geometry.mapping(l), "properties": {"filled": 1}} for l in add]
    json.dump(fc, open(der, "w"))
    return sum(l.length for l in add)


if __name__ == "__main__":
    import os, subprocess, tempfile, shutil
    der, lots, roads, ref = sys.argv[1:5]; b = sys.argv[5:9]; kw = json.loads(sys.argv[9]) if len(sys.argv) > 9 else {}
    cmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare_kerbs.py")
    sc = lambda p: json.loads(subprocess.run([sys.executable, cmp, p, ref, *b], capture_output=True, text=True).stdout)
    tmp = tempfile.mktemp(suffix=".geojson"); shutil.copy(der, tmp)
    m = fill_file(tmp, lots, roads, **kw)
    print(json.dumps({"before": sc(der), "after": sc(tmp), "filled_m": round(m)}))
