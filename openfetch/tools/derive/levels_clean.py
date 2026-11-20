#!/usr/bin/env python3
"""Clean roofer LoD1.3 roof levels into stepped buildings, with general rules only (no per-building or per-box values).

Used by levels.py (docs/playbooks/derive-roofs.md "Stepped buildings"). Pilot and numbers: research/q3-building-shapes/PILOT-roofer-2026-11-20.md.
A building is a list of levels [z AHD, polygon] inside its outline. Rules, in order:
  1 a tiny level, a level under 1.5 m wide, or a small level far above every touching level takes its neighbour's height (masts, cranes);
  n a level is refused only when it lies in the 1.5 m strip along the outline, is too high for the building and a building within 3 m
    has a level at the same height (that neighbour's wall seen through a slightly offset outline);
  4 every level is backed by the LiDAR under it: a level whose own roof cells sit more than one storey from it (median) takes the
    touching level those cells agree with (deep slots down a tower's wall, ragged crowns), else the building keeps its plain shape;
  3 level edges are squared to the outline's main directions (walls from the levels' own edges, steps at least 1 m);
  6 a level high above every touching level whose height goes on 2-6 m outside the outline is a neighbour's roof: plain shape;
  7 a level above the mapped height + max(10 m, 30 %) covering under 10 % of the roof (crane, mast) takes the lower height;
  5 a level under 3 m wide along the outline (facade fins, recesses) takes its neighbour's height: no ribbed walls;
then the gates: a building whose levels explain under FIT_MIN of its roof cells, whose level edges are ragged (over RAGGED under 1 m),
that still holds a neighbour's wall, whose LiDAR top is far below its mapped height (built
since the capture) or that is under MIN_TOP keeps its plain one-height shape (dropped here: the app draws it as before).
"""
import math
import numpy as np
import shapely
from shapely import affinity, contains_xy
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union as _uu

SPIKE_AREA = 25.0    # m2: smaller than a small room; a level this small standing far above the rest is a mast, crane or leak
THIN = 1.5           # m: a level narrower than this everywhere is a wall top or edge strip, not a roof
SPIKE_STEP = 8.0     # m: more than two storeys above every touching level
TINY_AREA = 5.0      # m2: below this a level holds fewer than ~40 LiDAR points and cannot be a real roof plane
EDGE_BAND = 1.5      # m: a strip this close to the outline is where a neighbour's wall leaks in
OSM_SLACK = (10.0, 0.30)  # a level more than max(10 m, 30 %) above the building's mapped height disagrees with it
SAME_Z = 0.25        # m: touching pieces this close in height are one level
NB_GAP = 3.0         # m: buildings this close can see each other's walls in the LiDAR
NB_MATCH = 2.0       # m: a level within this of a neighbour's level height may be that neighbour's points
AXIS_TOL = 20.0      # degrees: an edge this close to one of the outline's two main directions is a wall along it
LINE_GAP = 1.0       # m: wall lines closer than this are one wall (no step narrower than 1 m)
MIXED = 0.75         # a cell where no level covers 3/4 holds an edge at another angle: it keeps the measured edge
LINE_MIN = 1.0       # m: total wall length a line needs to count
STOREY = 3.0         # m: a level's own roof cells (median) further than this from it are not that level
FIT_TOL = 1.5        # m: a roof cell within this of its level's top is explained by it
FIT_MIN = 0.5        # share of roof cells the levels must explain, else the building keeps its plain shape
BACKED = 0.3         # share of a level's own roof cells within 1.5 m of it that backs it whatever their median
SLIVER = 2.0         # m2: a piece this small touching no other level is dropped (left open)
RIB = 3.0            # m: a strip along the outline narrower than this is a facade rib, not a set-back
MIN_CELLS = 5        # roof cells a level needs before rule 4 judges it
MIN_TOP = 10.0       # m above ground: lower buildings (houses, pitched roofs) keep their plain shape
NEWER = (10.0, 0.6)  # LiDAR top this far below the mapped height (and under 60 % of it): built since the capture, plain shape
SPILL = (2.0, 6.0, 0.5)  # m, m, share: roof cells 2-6 m outside the outline at a level's height mean that level is a neighbour's roof
OVER_SHARE = 0.10     # a level above the mapped height + OSM_SLACK covering under this share of the roof is a crane, mast or neighbour
RAGGED = 0.15        # share of a building's level edges under 1 m (3x the area gate in levels.py): ragged, plain shape


def unary_union(gs):
    try: return _uu(gs)
    except shapely.errors.GEOSException:
        try: return _uu([shapely.make_valid(g).buffer(0) for g in gs])
        except shapely.errors.GEOSException: return _uu([shapely.make_valid(g).buffer(0.001, join_style=2) for g in gs])


def polys(g):
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    if isinstance(g, MultiPolygon): return list(g.geoms)
    return [p for p in getattr(g, 'geoms', []) if isinstance(p, Polygon)]


def shared(a, b):
    i = a.boundary.intersection(b.boundary)
    return i.length if not i.is_empty else 0.0


def dissolve(P):
    """Join touching pieces of (almost) the same height into one level."""
    changed = True
    while changed:
        changed = False
        for i in range(len(P)):
            for j in range(i+1, len(P)):
                if abs(P[i][0]-P[j][0]) <= SAME_Z and shared(P[i][1], P[j][1]) > 0.05:
                    a = P[i][1].area; b = P[j][1].area
                    P[i] = [(P[i][0]*a+P[j][0]*b)/(a+b), unary_union([P[i][1], P[j][1]]).buffer(0)]
                    del P[j]; changed = True; break
            if changed: break
    return [[z, p] for z, g in P for p in polys(g) if p.area > 0.01]


def merge_into(P, i, j):
    P[j] = [P[j][0], unary_union([P[j][1], P[i][1]]).buffer(0)]; del P[i]


def merge_into_neighbour(P, i, prefer_lower=False):
    nb = [(shared(P[i][1], P[j][1]), j) for j in range(len(P)) if j != i]
    nb = [(s, j) for s, j in nb if s > 0.05 and (not prefer_lower or P[j][0] < P[i][0])]
    if not nb: return False
    merge_into(P, i, max(nb)[1]); return True


def rule1(P):
    """Rule 1: a tiny level, a level under 1.5 m wide, or a small level far above every touching level, takes its neighbour's height."""
    while True:
        P = dissolve(P); hit = None
        for i, (z, g) in enumerate(P):
            nbz = [P[j][0] for j in range(len(P)) if j != i and shared(g, P[j][1]) > 0.05]
            if not nbz: continue
            if g.area < TINY_AREA or g.buffer(-THIN/2, join_style=2).is_empty or (g.area < SPIKE_AREA and z >= max(nbz)+SPIKE_STEP): hit = i; break
        if hit is None or not merge_into_neighbour(P, hit): return P


def rule_leak(P, F, ground, h, nbr):
    """Rule n: refuse a level only when it sits in the 1.5 m band along the outline, is too high for this building (above its mapped
    height + max(10 m, 30 %), or 8 m above its main level when none is mapped), and a building within 3 m has a level at that height."""
    if ground is None: return P
    band = F.difference(F.buffer(-EDGE_BAND, join_style=2))
    while True:
        main = max(P, key=lambda q: q[1].area)
        lim = ground + h + max(OSM_SLACK[0], OSM_SLACK[1]*h) if h else main[0] + SPIKE_STEP
        bad = None
        for i, (z, g) in enumerate(P):
            if P[i] is main or z <= lim or g.intersection(band).area < 0.5*g.area: continue
            if any(abs(z-zn) <= NB_MATCH and gn.distance(g) <= NB_GAP for Pn in nbr for zn, gn in Pn): bad = i; break
        if bad is None or not merge_into_neighbour(P, bad, prefer_lower=True): return P
        P = dissolve(P)


class Cells:
    """roof cell tops (x, y, z) in 50 m buckets, so a building reads only the cells near it (a CBD area holds ~25 million)"""
    B = 50.0

    def __init__(self, T):
        self.T = T; k = np.floor(T[:, 0]/self.B).astype(np.int64)*1_000_000+np.floor(T[:, 1]/self.B).astype(np.int64)
        o = np.argsort(k, kind="stable"); k = k[o]; u, st = np.unique(k, return_index=True)
        self.at = {int(a): o[s:e] for a, s, e in zip(u, st, list(st[1:])+[len(k)])}

    def near(self, x0, y0, x1, y1):
        ids = [self.at[i*1_000_000+j] for i in range(int(np.floor(x0/self.B)), int(np.floor(x1/self.B))+1)
               for j in range(int(np.floor(y0/self.B)), int(np.floor(y1/self.B))+1) if i*1_000_000+j in self.at]
        return self.T[np.concatenate(ids)] if ids else self.T[:0]


def cells_in(T, g):
    """roof cell tops (1 m, highest building point per cell) inside g; T is a Cells or an (n, 3) array"""
    if g.is_empty: return np.zeros(0)
    x0, y0, x1, y1 = g.bounds
    Q = T.near(x0, y0, x1, y1) if isinstance(T, Cells) else T
    m = (Q[:, 0] > x0) & (Q[:, 0] < x1) & (Q[:, 1] > y0) & (Q[:, 1] < y1); Q = Q[m]
    return Q[contains_xy(g, Q[:, 0], Q[:, 1])][:, 2] if len(Q) else Q[:, 2]


def rule4(P, T):
    """Rule 4: a level must be backed by the LiDAR under it. A level is unbacked when the median of its own roof cells is more than a
    storey from it and under BACKED of them are within 1.5 m of it (deep slots down a tower's wall, ragged crowns). It takes the touching
    level that is nearer its cells' median than itself. Returns (levels, True) when an unbacked level has no such neighbour: then the
    building keeps its plain shape."""
    while True:
        P = dissolve(P); hit = None
        for i, (z, g) in enumerate(P):
            c = cells_in(T, g)
            if len(c) < MIN_CELLS: continue
            m = float(np.median(c))
            if abs(m - z) <= STOREY or np.mean(np.abs(c - z) <= FIT_TOL) >= BACKED: continue
            nb = [(abs(P[j][0]-m), j) for j in range(len(P)) if j != i and shared(g, P[j][1]) > 0.05 and abs(P[j][0]-m) < abs(z-m)]
            if not nb: return P, True
            hit = (i, min(nb)[1]); break
        if hit is None: return P, False
        merge_into(P, *hit)


def rule6(P, F, T):
    """Rule 6: a neighbour's roof seen through the outline. A level standing a storey-step above every touching level whose height goes on
    outside the outline (half the roof cells 2-6 m beyond it within 1.5 m of the level; outline errors stay under 2 m) is a tower next
    door or a roof shared with the next outline: no one can tell which, so the building keeps its plain shape (True)."""
    out = F.buffer(SPILL[0], join_style=2)
    for i, (z, g) in enumerate(P):
        nbz = [P[j][0] for j in range(len(P)) if j != i and shared(g, P[j][1]) > 0.05]
        if not nbz or z < max(nbz) + SPIKE_STEP: continue
        c = cells_in(T, g.buffer(SPILL[1], join_style=2).difference(out))
        if len(c) >= MIN_CELLS and np.mean(np.abs(c - z) <= FIT_TOL) >= SPILL[2]: return True
    return False


def rule7(P, ground, h):
    """Rule 7: a small level far above the mapped height. A level above the building's mapped height + max(10 m, 30 %) that covers under
    OVER_SHARE of its roof is a crane, mast or a neighbour's tower (the map and the rest of the LiDAR both say the building is lower there):
    it takes the lower touching level's height. Nothing changes when no height is mapped."""
    if not h: return P
    lim = ground + h + max(OSM_SLACK[0], OSM_SLACK[1]*h)
    while True:
        P = dissolve(P); tot = sum(g.area for _, g in P)
        hit = next((i for i, (z, g) in enumerate(P) if z > lim and g.area < OVER_SHARE*tot), None)
        if hit is None or not merge_into_neighbour(P, hit, prefer_lower=True): return P


def rule5(P, F):
    """Rule 5: no ribs. A level under 3 m wide (it vanishes when shrunk 1.5 m) lying mostly in the 3 m strip along the outline is a facade
    fin, recess or balcony line seen from above, not a set-back: it takes the height of the touching level it shares most edge with."""
    band = F.difference(F.buffer(-RIB, join_style=2))
    while True:
        P = dissolve(P); hit = None
        for i, (z, g) in enumerate(P):
            if len(P) > 1 and g.buffer(-RIB/2, join_style=2).is_empty and g.intersection(band).area >= 0.5*g.area: hit = i; break
        if hit is None or not merge_into_neighbour(P, hit): return P


def main_angle(F):
    c = list(F.exterior.coords); hist = np.zeros(90)
    for a, b in zip(c, c[1:]):
        L = math.hypot(b[0]-a[0], b[1]-a[1]); t = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 90
        for d in range(-3, 4): hist[int(round(t+d)) % 90] += L * (4-abs(d))
    return float(np.argmax(hist))


def wall_lines(geoms):
    """Wall positions along the two main directions (rotated frame), from the levels' and outline's own edges, clustered
    (length-weighted) until no two lines are closer than 1 m."""
    cand = {0: [], 1: []}
    for g in geoms:
        for p in polys(g):
            for r in [p.exterior, *p.interiors]:
                c = list(r.coords)
                for a, b in zip(c, c[1:]):
                    dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy)
                    if L < 1e-6: continue
                    t = math.degrees(math.atan2(abs(dy), abs(dx)))
                    if t <= AXIS_TOL: cand[1].append(((a[1]+b[1])/2, L))
                    elif t >= 90-AXIS_TOL: cand[0].append(((a[0]+b[0])/2, L))
    out = {}
    for k, v in cand.items():
        v.sort(); merged = True
        while merged:
            merged = False; cl = []
            for x, w in v:
                if cl and x - cl[-1][0] < LINE_GAP: X, W_ = cl[-1]; cl[-1] = ((X*W_+x*w)/(W_+w), W_+w); merged = True
                else: cl.append((x, w))
            v = cl
        out[k] = [x for x, w in v if w >= LINE_MIN]
    return out


def snap_vertices(P, F):
    """Join level corners closer than 1 m. Outline corners never move; other corners move to the nearest outline corner, or to the
    first corner of their group, so neighbouring levels keep sharing their edges."""
    fixed = [tuple(c) for c in F.exterior.coords[:-1]] + [tuple(c) for r in F.interiors for c in r.coords[:-1]]
    pts = sorted({tuple(c) for _, g in P for p in polys(g) for r in [p.exterior, *p.interiors] for c in r.coords[:-1]} - set(fixed))
    to, reps = {}, list(fixed)
    for q in pts:
        d = [math.dist(q, r) for r in reps]
        if d and min(d) < LINE_GAP: to[q] = reps[int(np.argmin(d))]
        else: reps.append(q); to[q] = q
    out = []
    for z, g in P:
        for p in polys(g):
            def m(r):
                c = [to.get(tuple(x), tuple(x)) for x in r.coords[:-1]]; c = [x for i, x in enumerate(c) if x != c[i-1]]
                return c if len(c) >= 3 else None
            ext = m(p.exterior)
            if not ext: continue
            q = Polygon(ext, [h for h in (m(r) for r in p.interiors) if h]).buffer(0).intersection(F)
            out += [[z, x] for x in polys(q) if x.area > 0.01]
    return dissolve(out)


def fill(P, F, open_before):
    """A clean partition again after squaring: overlaps go to the lower level; any part of the outline left without a level takes the
    level it shares most edge with, except open ground roofer found (courtyards, lanes)."""
    P = sorted(P, key=lambda q: q[0]); seen = Polygon(); Q = []
    for z, g in P:
        r = g.difference(seen); seen = unary_union([seen, g])
        Q += [[z, p] for p in polys(r) if p.area > 0.01]
    P = Q
    for h in polys(F.difference(unary_union([g for _, g in P])).difference(open_before)):
        if h.area < 0.01 or not P: continue
        best = max(range(len(P)), key=lambda k: (shared(P[k][1], h), -P[k][1].distance(h)))
        P[best] = [P[best][0], unary_union([P[best][1], h]).buffer(0)]
    return dissolve(P)


def rule3(P, F):
    """Rule 3: square level edges to the outline's main directions; every cell between wall lines takes the level covering most of it."""
    if len(P) < 2: return P
    th = main_angle(F); c = F.centroid
    R = [[z, shapely.make_valid(affinity.rotate(g, -th, origin=c)).buffer(0)] for z, g in P]
    FR = shapely.make_valid(affinity.rotate(F, -th, origin=c)).buffer(0)
    op = FR.difference(unary_union([g for _, g in R]))
    if op.area > 0.01: R.append([None, op])
    x0, y0, x1, y1 = FR.bounds; Ls = wall_lines([g for _, g in R] + [FR])
    xs = sorted({x0, x1, *[x for x in Ls[0] if x0 < x < x1]}); ys = sorted({y0, y1, *[y for y in Ls[1] if y0 < y < y1]})
    cells = {k: [] for k in range(len(R))}
    for xa, xb in zip(xs, xs[1:]):
        for ya, yb in zip(ys, ys[1:]):
            cb = box(xa, ya, xb, yb)
            if not cb.intersects(FR): continue
            parts = [g.intersection(cb) for _, g in R]; ar = [p.area for p in parts]
            if max(ar) <= 1e-6: continue
            if max(ar) >= MIXED*sum(ar): cells[int(np.argmax(ar))].append(cb)
            else:
                for k, p in enumerate(parts):
                    if p.area > 1e-6: cells[k].append(p)
    out = []
    for k, (z, _) in enumerate(R):
        if z is None or not cells[k]: continue
        g = affinity.rotate(unary_union(cells[k]).intersection(FR), th, origin=c)
        out += [[z, p] for p in polys(g.buffer(0)) if p.area > 0.01]
    return dissolve(out)


def fit(P, T, F):
    """share of the outline's roof cells within 1.5 m of the level drawn over them (cells under no level count as missed)"""
    c_all = cells_in(T, F)
    if not len(c_all): return 0.0
    ok = sum(int(np.sum(np.abs(cells_in(T, g) - z) <= FIT_TOL)) for z, g in P)
    return ok / len(c_all)


def prepare(P):
    return rule1(dissolve([[z, g] for z, g in P]))


def clean(P, F, ground, h, nbr, T):
    """One building: P = rule-1 levels, F = outline, ground (AHD) and mapped height h (m or None), nbr = rule-1 levels of buildings
    within 3 m, T = roof cell tops (x, y, z). Returns (levels, None) for a stepped building, or ([], reason) when it keeps its plain shape."""
    if not P or ground is None: return [], 'no LiDAR levels'
    P = rule_leak(P, F, ground, h, nbr)
    P = rule7(P, ground, h)
    if rule6(P, F, T): return [], "a neighbour's roof goes on outside the outline"
    P, bad = rule4(P, T)
    if bad: return [], 'a level the LiDAR does not back'
    open0 = F.difference(unary_union([g for _, g in P]))
    P = rule1(rule5(rule1(fill(snap_vertices(rule3(P, F), F), F, open0)), F))
    P, bad = rule4(P, T)
    P = [q for q in P if q[1].area >= SLIVER]
    if bad or not P: return [], 'a level the LiDAR does not back'
    top = max(z for z, _ in P) - ground
    if top < MIN_TOP: return [], 'low building'
    if h and h - top > NEWER[0] and top < NEWER[1]*h: return [], 'LiDAR older than the building'
    if len({round(z, 1) for z, _ in P}) < 2: return [], 'one level'
    f = fit(P, T, F)
    if f < FIT_MIN: return [], f'poor fit (under {FIT_MIN})'
    bad = shape_gate(P, F, nbr)
    return ([], bad) if bad else (P, None)


def shape_gate(P, F, nbr):
    """the last check on a cleaned building: ragged level edges or a neighbour's wall still in a level keep the plain shape"""
    sh, n = edges(P)
    if sh > RAGGED*n: return 'ragged level edges'
    if leaks(P, F, nbr): return "a neighbour's wall in a level"


def surface(pts, cell=1.0):
    """roof cell tops: the highest building-class point in each 1 m cell, as (x centre, y centre, z)"""
    ix = np.floor(pts[:, 0]/cell).astype(np.int64); iy = np.floor(pts[:, 1]/cell).astype(np.int64); key = ix*100_000_000+iy
    o = np.lexsort((-pts[:, 2], key)); k = key[o]; first = np.r_[True, k[1:] != k[:-1]]
    return np.c_[(ix[o][first]+0.5)*cell, (iy[o][first]+0.5)*cell, pts[o][first, 2]]


def edges(P):
    s = t = 0
    for _, g in P:
        for p in polys(g.simplify(0.01)):
            for ring in [p.exterior, *p.interiors]:
                c = list(ring.coords)
                for a, b in zip(c, c[1:]): t += 1; s += math.hypot(b[0]-a[0], b[1]-a[1]) < 0.995
    return s, t


def spikes(P):
    n = 0
    for i, (z, g) in enumerate(P):
        nbz = [P[j][0] for j in range(len(P)) if j != i and shared(g, P[j][1]) > 0.05]
        if nbz and g.area < SPIKE_AREA and z >= max(nbz)+SPIKE_STEP: n += 1
    return n


def leaks(P, F, nbr):
    """levels 8 m above the main level, mostly in the 1.5 m band, at the height of a level of a building within 3 m"""
    main = max(P, key=lambda q: q[1].area); band = F.difference(F.buffer(-EDGE_BAND, join_style=2))
    sus = [(z, g) for z, g in P if g is not main[1] and z >= main[0]+SPIKE_STEP and g.intersection(band).area >= 0.5*g.area]
    return sum(1 for z, g in sus if any(abs(z-zn) <= NB_MATCH and gn.distance(g) <= NB_GAP for Pn in nbr for zn, gn in Pn))
