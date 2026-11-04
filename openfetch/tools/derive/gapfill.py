#!/usr/bin/env python3
"""Fill the gaps: keep community shapes (already moved onto LiDAR by snap_pilot.py) and add traced roofs only where
nobody drew a building.

Usage: python3 tools/derive/gapfill.py snapped.geojson traced.geojson out.geojson [community.geojson [lots.geojson [tile.laz ...]]]

traced.geojson comes from roofs.py --mode br. Each traced roof loses the part already covered by a snapped shape
(+0.3 m); what is left is squared to OSM style (clean.py: no wall under 2 m; an outline left with 2+ short walls is dropped) and kept when it is at least 40 m2, 3 m wide, fills 60 % of its bounding rectangle and runs along
a community shape for at most a quarter of its outline, so the slivers left by small position differences are dropped.
Before squaring, each trace is cut along the NSW cadastre lot lines (lots.py): in new estates houses stand about 1 m apart and
the trace joins 2-3 of them into one blob. Where no house lot holds the trace (no cadastre there, or one big lot with several
houses on it), the LiDAR splits it instead: along ground points inside the trace and roof height steps of a storey or more,
when that leaves 2 or more roofs of 40 m2. A finished gap that still covers 2 or more house lots (100-2000 m2) is dropped.
High-rise (2 Nov 2026, Chatswood P-0098): a trace taller than HIGH_RISE is not traced at all (the trace joins towers into
one blob and lot lines cut it into strips; OSM draws towers well), and every finished gap gets its own heights from the
LiDAR inside it, never the whole trace's, so a strip beside a tower cannot take the tower's height.
"""
import sys, json
import numpy as np
from scipy import ndimage
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree
from clean import osm_clean, short_walls

snapped, traced, out = sys.argv[1:4]
# shapes snap_pilot dropped (no LiDAR roof under them: maybe newer than the LiDAR) still show in the app's community
# layer, so a trace must not be drawn over them either
C = json.load(open(sys.argv[4]))["features"] if len(sys.argv) > 4 else []
_LF = json.load(open(sys.argv[5]))["features"] if len(sys.argv) > 5 else []
LOTS = [shape(f["geometry"]) for f in _LF]
STRATA = [str(f["properties"].get("lot", "")).split("/")[-1].startswith("SP") for f in _LF]  # strata plan: one lot, many homes
LAZ = sys.argv[6:]
lot_tree = STRtree(LOTS) if LOTS else None
import os
HOUSE_LOT = (float(os.environ.get("LOT_MIN", 30)), 2000)  # m2: a lot that holds one house (Gregory Hills median 430 m2); 30, not 100, since RT1 (4 Nov 2026): terrace lots count (Erskineville median 132, 21 % under 100)
house_lots = [g for g in LOTS if HOUSE_LOT[0] <= g.area <= HOUSE_LOT[1]]
hl_tree = STRtree(house_lots) if house_lots else None
S = json.load(open(snapped))["features"]; T = json.load(open(traced))["features"]
# taken space is looked up locally (STRtree) instead of one union of the whole box: a 2 km box has thousands of shapes
# A community shape that snap_pilot could not fit onto any LiDAR roof (Microsoft can sit 10-15 m off on steep slopes)
# blocks a trace only when it covers at least half of that roof (then it is that house, unconfirmed). Otherwise the
# trace is drawn whole and lists the shape's id in `replaces`, so the app can hide the misplaced shape.
SG = [shape(f["geometry"]) for f in S]
stree = STRtree(SG) if SG else None
def fitted(c):
    for i in (stree.query(c.buffer(5.5)) if stree else []):
        s = SG[i]
        if abs(s.area - c.area) <= 0.15 * c.area and s.centroid.distance(c.centroid) <= 5.3:
            return True
    return False
CG = [shape(f["geometry"]) for f in C]
loose = [i for i, c in enumerate(CG) if not fitted(c)]
fixed = [CG[i] for i in range(len(CG)) if i not in set(loose)]
LG = [CG[i] for i in loose]; LID = [C[i]["properties"].get("id") for i in loose]
ltree = STRtree(LG) if LG else None
CP = [g.buffer(0.3, join_style=2) for g in SG + fixed]
tree = STRtree(CP)
near = lambda g, d=0.0: [CP[i] for i in tree.query(g.buffer(d) if d else g)]


def by_lots(d):
    """The trace cut along lot lines, one piece per lot. Where the cadastre has no lots under most of it, the trace stays whole."""
    if not lot_tree or d.is_empty:
        return [d]
    parts = [d.intersection(LOTS[i]) for i in lot_tree.query(d)]
    parts = [p for p in parts if p.area >= 1]
    if sum(p.area for p in parts) < 0.5 * d.area:
        return [d]
    return parts


THIN_W, THIN_H = 4.0, 12.0  # m: a gap narrower than this (2 x area / perimeter) and taller is the edge of a taller roof (tools/mirror/roofs-check.py)
HIGH_RISE = 25.0  # m roof above ground: over this the trace is a tower block, not a house (same cap as the app, src/regions/nsw/roofs.js)
HKEYS = ("n_roof", "n_ground", "density", "area_m2", "eave", "ridge", "roof_mean", "ground", "h_max", "h_eave", "h_mean")
CELL, STEP, MIN_PART = 0.5, 2.5, 40  # m grid; m roof height jump (a storey) that parts two roofs; m2 smallest roof kept apart


def lidar_points(geoms):
    """Ground and building points around the given outlines, from the LAZ tiles (GDA94 tiles moved to GDA2020)."""
    from roofs import read_points, to_gda2020
    b = unary_union(geoms).bounds
    P = to_gda2020(read_points(LAZ, [b[0] - 5, b[1] - 5, b[2] + 5, b[3] + 5]))
    o = np.argsort(P["x"])  # sorted by x, so each trace reads only its own strip
    return {k: P[k][o] for k in "xyzc"}


def by_lidar(d, P):
    """Split one trace where the LiDAR shows ground, or a roof height jump of a storey, between two roofs."""
    import rasterio.features
    from rasterio.transform import from_origin
    x0, y0, x1, y1 = d.bounds
    s = slice(*np.searchsorted(P["x"], [x0 - 1, x1 + 1]))
    x, y, z, c = P["x"][s], P["y"][s], P["z"][s], P["c"][s]
    m = (y >= y0 - 1) & (y <= y1 + 1)
    x, y, z, c = x[m], y[m], z[m], c[m]
    nr, nc = int((y1 - y0) / CELL) + 5, int((x1 - x0) / CELL) + 5
    ox, oy = x0 - 2 * CELL, y1 + 2 * CELL
    r, k = ((oy - y) / CELL).astype(int), ((x - ox) / CELL).astype(int)
    dsm = np.full((nr, nc), np.nan); ground = np.zeros((nr, nc), bool)
    b = c == 6
    np.fmax.at(dsm, (r[b], k[b]), z[b])
    ground[r[c == 2], k[c == 2]] = True
    tf = from_origin(ox, oy, CELL, CELL)
    inside = rasterio.features.rasterize([d], out_shape=(nr, nc), transform=tf).astype(bool)
    roof = inside & ~np.isnan(dsm) & ~ground
    # height steps: a cell whose 4-neighbour roof is a storey higher or lower
    step = np.zeros_like(roof)
    for dr, dk in ((0, 1), (1, 0)):
        a, bb = dsm[:nr - dr, :nc - dk], dsm[dr:, dk:]
        j = np.abs(a - bb) > STEP
        step[:nr - dr, :nc - dk] |= j; step[dr:, dk:] |= j
    cut = ndimage.binary_dilation(ground | step) & inside
    if STEP_FINE:
        cut |= _fine_lines(d, dsm, roof, tf)
    lab, n = ndimage.label(roof & ~cut)
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)) * CELL * CELL
    keep = [i + 1 for i, a in enumerate(sizes) if a >= MIN_PART]
    if len(keep) < 2:
        return [d]
    seeds = np.isin(lab, keep)
    _, (ir, ik) = ndimage.distance_transform_edt(~seeds, return_indices=True)
    owner = np.where(inside, lab[ir, ik], 0).astype(np.int32)  # every cell of the trace goes to its nearest roof
    parts = [shape(g).intersection(d) for g, v in rasterio.features.shapes(owner, mask=owner > 0, transform=tf)]
    parts = [p for p in parts if p.area >= 1]
    return parts or [d]


STEP_FINE = float(os.environ.get("STEP_FINE", 0))  # RT2 (4 Nov 2026): m, smallest roof step a parapet or party wall makes (0 = off, the control); the kerb step detector lesson
STEP_FINE_MS = os.environ.get("STEP_FINE_MS", "0") == "1"  # RT2: also part Microsoft outlines with it
# RT4 (4 Nov 2026): Microsoft outlines drawn over two homes that share a wall (semis, duplexes, unit rows: Gosford 24 of 28
# merged official houses). lots = cut at the lot line when every piece is a real share of it (MS_PIECE of the outline and 35 m2+;
# a house drawn 1 m over its neighbour's lot leaves only a sliver there); lots+rows = also the party-wall cut on strata/shared lots
MS_SPLIT = os.environ.get("MS_SPLIT", "0")
MS_PIECE = float(os.environ.get("MS_PIECE", 0.3))
STEP_ACROSS = 0.7  # share of the piece's depth a parapet line must cross


def _fine_lines(d, dsm, roof, tf):
    """Cells on a parapet or party-wall line: the 0.5 m DSM jumps STEP_FINE-STEP m between the cells 1 m either side, and the
    jump runs straight across the piece (at right angles to its long axis) over STEP_ACROSS of its depth. Roof furniture
    (a skylight, an air conditioner) jumps too but over a few cells only, so it never makes a line."""
    c = np.asarray(d.minimum_rotated_rectangle.exterior.coords)[:3]
    e = [c[1] - c[0], c[2] - c[1]]
    u = max(e, key=np.linalg.norm); u = u / np.linalg.norm(u); v = np.array([-u[1], u[0]])
    rr, kk = np.nonzero(roof)
    if len(rr) < 50:
        return np.zeros_like(roof)
    xs, ys = tf.c + (kk + 0.5) * CELL, tf.f - (rr + 0.5) * CELL
    o = np.asarray(d.centroid.coords[0])
    ps, pt = (xs - o[0]) * u[0] + (ys - o[1]) * u[1], (xs - o[0]) * v[0] + (ys - o[1]) * v[1]
    i, j = ((ps - ps.min()) / CELL).astype(int), ((pt - pt.min()) / CELL).astype(int)
    ns, nt = i.max() + 1, j.max() + 1
    H = np.full((ns, nt), np.nan); H[i, j] = dsm[rr, kk]
    w = 2
    lines = np.zeros(ns, bool)
    for k in range(w, ns - w):
        with np.errstate(all="ignore"):
            left, right = np.nanmedian(H[k - w:k], axis=0), np.nanmedian(H[k + 1:k + 1 + w], axis=0)
        ok = ~np.isnan(left) & ~np.isnan(right)
        if ok.sum() < 6:  # 3 m of depth at least
            continue
        jump = np.abs(right - left)
        hit = (jump >= STEP_FINE) & (jump <= STEP) & ok
        # the line crosses from edge to edge: most of the depth, and both ends of it
        if hit.sum() >= STEP_ACROSS * ok.sum():
            lines[k] = True
    # one cut per line (the strongest run of neighbouring columns is one parapet), at least a frontage from the ends
    ks = np.flatnonzero(lines)
    cut = np.zeros_like(roof)
    if not len(ks):
        return cut
    runs = np.split(ks, np.flatnonzero(np.diff(ks) > 1) + 1)
    pick = [int(np.median(r)) for r in runs]
    pick = [k for k in pick if k * CELL >= FRONT[0] and (ns - 1 - k) * CELL >= FRONT[0]]
    on = np.isin(i, pick)
    cut[rr[on], kk[on]] = True
    return ndimage.binary_dilation(cut) & roof  # a diagonal line of cells must still part the roof (4-neighbour labels)


ROW_SPLIT = os.environ.get("ROW_SPLIT", "1") == "1"  # roof tracing rounds switch (docs/handoffs/roof-tracing-rounds.md): 0 = no row cuts, the control
FRONT = (3.5, 12.0)  # m: frontage of one terrace or townhouse (Paddington 4-6 m, newer townhouses up to ~10 m)
ROW_STEP, ROW_VALLEY, ROW_ACROSS = 0.4, 0.3, 0.6  # m step, m gutter depth, share of the row's depth a party wall crosses


def by_rows(d, P):
    """Split a terrace or townhouse row into its dwellings where the cadastre has one lot for the whole row (strata plans,
    old shared lots). Each dwelling has its own roof: at a party wall the roof steps (a row on a slope) or dips into a
    gutter between two roofs, along a straight line right across the row. A ridge is a peak, not a dip, so a single house
    whose ridge crosses it is not cut. Cuts are kept only when they give 2+ dwellings of a frontage FRONT wide that are
    about the same width (a row is built from one plan); otherwise the piece stays whole."""
    if d.geom_type != "Polygon" or d.area < 2 * 35:
        return [d]
    c = np.asarray(d.minimum_rotated_rectangle.exterior.coords)[:3]
    best = None
    for a, b in ((c[0], c[1]), (c[1], c[2])):  # cut across either side of the rectangle
        u = (b - a) / np.linalg.norm(b - a); v = np.array([-u[1], u[0]])
        cut = _row_cuts(d, P, u, v)
        if cut and (best is None or cut[0] > best[0]):
            best = cut + (u,)
    if not best:
        return [d]
    _, s_cuts, u = best
    from shapely.geometry import Polygon
    v = np.array([-u[1], u[0]]); big = 1e3
    o = np.asarray(d.centroid.coords[0])
    edges = [-big] + list(s_cuts) + [big]
    parts = []
    for s0, s1 in zip(edges[:-1], edges[1:]):
        q = [o + s0 * u - big * v, o + s1 * u - big * v, o + s1 * u + big * v, o + s0 * u + big * v]
        p = d.intersection(Polygon(q))
        if not p.is_empty:
            parts.append(p if p.geom_type == "Polygon" else max(p.geoms, key=lambda g: g.area))
    return parts if len(parts) >= 2 else [d]


def _row_cuts(d, P, u, v):
    """Party-wall cut positions across direction u (metres from the centroid), with a score; None when it is not a row."""
    from shapely import contains_xy
    x0, y0, x1, y1 = d.bounds
    s = slice(*np.searchsorted(P["x"], [x0, x1]))
    x, y, z, cl = P["x"][s], P["y"][s], P["z"][s], P["c"][s]
    m = (y >= y0) & (y <= y1) & (cl == 6)
    x, y, z = x[m], y[m], z[m]
    if len(x) < 50:
        return None
    m = contains_xy(d, x, y); x, y, z = x[m], y[m], z[m]
    if len(x) < 50:  # a piece with no roof points of its own (Gosford)
        return None
    o = np.asarray(d.centroid.coords[0])
    ps, pt = (x - o[0]) * u[0] + (y - o[1]) * u[1], (x - o[0]) * v[0] + (y - o[1]) * v[1]
    smin, smax = ps.min(), ps.max(); tmin, tmax = pt.min(), pt.max()
    length, depth = smax - smin, tmax - tmin
    if length < 2 * FRONT[0] or depth < 5:
        return None
    ns, nt = int(length / CELL) + 1, int(depth / CELL) + 1
    i, j = ((ps - smin) / CELL).astype(int), ((pt - tmin) / CELL).astype(int)
    H = np.full((ns, nt), np.nan); np.fmax.at(H, (i, j), z)
    # fill single empty cells along the row (point spacing), so a missing cell is not read as a break
    Hf = H.copy()
    for k in range(1, ns - 1):
        e = np.isnan(Hf[k]); Hf[k, e] = np.fmax(H[k - 1, e], H[k + 1, e])
    H = Hf
    w = 2  # cells (1 m) on each side of a party wall
    score = np.zeros(ns)
    for k in range(w, ns - w):
        with np.errstate(all="ignore"):
            left, right = np.nanmean(H[k - w:k], axis=0), np.nanmean(H[k + 1:k + 1 + w], axis=0)
        mid = H[k]
        ok = ~np.isnan(left) & ~np.isnan(right)
        if ok.sum() < 0.5 * nt:
            continue
        step = np.abs(right - left) > ROW_STEP
        with np.errstate(invalid="ignore"):
            dip = (np.fmin(left, right) - mid) > ROW_VALLEY
            gap = np.isnan(mid)
        score[k] = ((step | dip | gap) & ok).sum() / ok.sum()
    # strongest lines first, at least one narrow frontage apart
    cand = [k for k in np.argsort(-score) if score[k] >= ROW_ACROSS]
    pick = []
    for k in cand:
        if all(abs(k - q) * CELL >= FRONT[0] for q in pick):
            pick.append(k)
    pick.sort()
    if not pick:
        return None
    pos = [smin + (k + 0.5) * CELL for k in pick]
    widths = np.diff([smin] + pos + [smax])
    if widths.min() < FRONT[0] or widths.max() > FRONT[1]:
        return None
    if widths.max() / widths.min() > 1.6:  # dwellings of one row are about the same width
        return None
    if widths.max() > 0.9 * depth:  # a dwelling is deeper than its frontage: a cut along a house's depth is its back wing
        return None
    return (float(np.mean(score[pick])) * len(pick), pos)


ONE_HOME = 250  # m2: an inner-city lot under this holds one terrace or house


def one_home_lot(g):
    return any(LOTS[i].area < ONE_HOME and LOTS[i].intersection(g).area >= 0.5 * g.area for i in (lot_tree.query(g) if lot_tree else []))


def on_strata(g):
    return any(STRATA[i] and LOTS[i].intersection(g).area >= 0.5 * g.area for i in (lot_tree.query(g) if lot_tree else []))


ROW_MAPPED = os.environ.get("ROW_MAPPED", "row3")  # which mapped outlines the row cut may cut (RT1, 4 Nov 2026): row3 = only one covering 3+ one-home lots (a drawn row; 2 lots is usually 1 m drawing error), all, ms (Microsoft only)


def n_home_lots(g):
    return sum(1 for i in (lot_tree.query(g) if lot_tree else []) if LOTS[i].area < ONE_HOME and LOTS[i].intersection(g).area >= max(15, 0.4 * LOTS[i].area))


def whole_pieces(parts, g):
    """Lot pieces of a mapped outline without the slivers its drawing leaves over a neighbour's lot: a piece under 15 m2
    or 2.5 m across joins the piece it touches most."""
    small = lambda p: p.area < 15 or 2 * p.area / p.length < 1.25
    big = [p for p in parts if not small(p)]
    if len(big) < 2:
        return [g]
    for p in parts:
        if small(p):
            j = max(range(len(big)), key=lambda i: big[i].buffer(0.05).intersection(p).area + big[i].distance(p) * -1e-6)
            u = unary_union([big[j], p]).buffer(0.01, join_style=2).buffer(-0.01, join_style=2)
            big[j] = u if u.geom_type == "Polygon" else max(u.geoms, key=lambda q: q.area)
    return big


def local_heights(roofs, P, geoms, cell=100.0):
    """roofs.heights, read 100 m square by square: it scans every point once per outline, too slow for a box's thousands
    of terrace houses. Same answers (each outline needs points 4 m around it at most)."""
    if not geoms:
        return []
    o = np.argsort(P["x"]); Q = {k: P[k][o] for k in "xyzc"}
    groups = {}
    for i, g in enumerate(geoms):
        c = g.centroid; groups.setdefault((int(c.x // cell), int(c.y // cell)), []).append(i)
    out = [None] * len(geoms)
    for idx in groups.values():
        b = unary_union([geoms[i] for i in idx]).bounds
        s = slice(*np.searchsorted(Q["x"], [b[0] - 5, b[2] + 5]))
        m = (Q["y"][s] >= b[1] - 5) & (Q["y"][s] <= b[3] + 5)
        sub = {k: Q[k][s][m] for k in "xyzc"}
        for i, r in zip(idx, roofs.heights(sub, [geoms[i] for i in idx], CELL)):
            out[i] = r
    return out


def lots_spanned(g):
    """House lots holding a real part of the outline (at least 15 m2 and a tenth of it)."""
    return sum(1 for i in (hl_tree.query(g) if hl_tree else []) if house_lots[i].intersection(g).area >= max(15, 0.1 * g.area))
gap, gap_geoms, n_span = [], [], 0
def house_lot(g):
    return any(house_lots[i].intersection(g).area >= 0.5 * g.area for i in (hl_tree.query(g) if hl_tree else []))


# each lot's piece of a trace is judged on its own: a loose community house on one lot blocks only that piece
low = [f for f in T if (f["properties"].get("h_max") or 0) <= HIGH_RISE]
n_high = len(T) - len(low)
work = [(f, p) for f in low for p in by_lots(shape(f["geometry"]))]
n_lidar = n_rows = n_fine_ms = n_ms_split = 0
rows_of = {}  # index in S -> the mapped row's dwellings
if LAZ and (work or SG):
    P = lidar_points([p for f, p in work] + SG)
    # pieces on no house lot that could hold 2+ houses: split where the LiDAR shows ground or a storey step
    for i, (f, p) in enumerate(work):
        if p.area >= 2 * MIN_PART + 20 and not house_lot(p):
            parts = by_lidar(p, P)
            if len(parts) > 1:
                n_lidar += 1; work[i] = [(f, q) for q in parts]
    work = [w for x in work for w in (x if isinstance(x, list) else [x])]
    # terrace and townhouse rows on one lot (strata plans, old shared lots): split along the party walls (Paddington, 4 Nov 2026)
    for i, (f, p) in enumerate(work):
        if not ROW_SPLIT or one_home_lot(p):  # a lot of one dwelling's size: the lot lines already split this row
            continue
        parts = by_rows(p, P)
        if len(parts) > 1:
            n_rows += 1; work[i] = [(f, q) for q in parts]
    work = [w for x in work for w in (x if isinstance(x, list) else [x])]
    # mapped rows: OpenStreetMap often draws a whole terrace row as one building; cut it the same way, so each dwelling
    # gets its own LiDAR height and the row is not one big property (Paddington, 4 Nov 2026)
    for k, g in enumerate(SG if ROW_SPLIT else []):
        pk = S[k]["properties"]
        if g.geom_type != "Polygon" or g.area < 2 * 35 or pk.get("high_rise") or (pk.get("h_max") or 0) > HIGH_RISE:
            continue  # towers stay whole: lot lines under them are strata lots, not houses (Chatswood P-0098)
        if MS_SPLIT != "0" and pk.get("src") == "ms" and not (ROW_MAPPED == "row3" and n_home_lots(g) >= 3):
            parts = whole_pieces(by_lots(g), g)
            if len(parts) < 2 or min(p.area for p in parts) < max(MS_PIECE * g.area, 35):
                parts = [g]
            if "rows" in MS_SPLIT or "strata" in MS_SPLIT:  # lots+strata: the party-wall cut only on a strata lot
                cut = (lambda p: on_strata(p)) if "strata" in MS_SPLIT else (lambda p: not one_home_lot(p))
                parts = [q for p in parts for q in (by_rows(p, P) if cut(p) else [p])]
                parts = whole_pieces(parts, g) if len(parts) >= 2 else parts
            if len(parts) >= 2:
                rows_of[k] = parts; n_ms_split += 1
            continue
        if (ROW_MAPPED == "row3" and n_home_lots(g) < 3) or (ROW_MAPPED == "ms" and pk.get("src") != "ms"):
            # RT2: a Microsoft outline over a shop row or units (Gosford) has no row of small lots; with STEP_FINE_MS=1 the
            # fine LiDAR step, ground and storey cuts may still part it (Microsoft joins neighbours itself; OSM draws them apart)
            if STEP_FINE and STEP_FINE_MS and pk.get("src") == "ms" and g.area >= 2 * MIN_PART + 20:
                parts = whole_pieces(by_lidar(g, P), g)
                if len(parts) >= 2:
                    rows_of[k] = parts; n_fine_ms += 1
            continue  # RT1b: a mapped shape is cut only when it covers a row (3+ one-home lots), not 2 lots it overlaps by drawing error
        parts = whole_pieces(by_lots(g), g)
        parts = [q for p in parts for q in (by_rows(p, P) if not one_home_lot(p) else [p])]
        parts = whole_pieces(parts, g) if len(parts) >= 2 else parts  # a party-wall cut can leave a corner sliver too
        if len(parts) >= 2:
            rows_of[k] = parts
    del P
for f, t in work:
    hits = [i for i in (ltree.query(t) if ltree else []) if LG[i].intersects(t)]
    block = [LG[i].buffer(0.3, join_style=2) for i in hits if LG[i].intersection(t).area >= 0.5 * t.area]
    replaces = [LID[i] for i in hits if LG[i].intersection(t).area < 0.5 * t.area]
    cov = unary_union(near(t, 2) + block)
    d = t.difference(cov).buffer(-1, join_style=2).buffer(1, join_style=2)
    for g in (d.geoms if hasattr(d, "geoms") else [d]):
        g = osm_clean(g.simplify(0.3))
        # squaring can push a wall over a neighbour: cut it back along the neighbour's wall
        taken = unary_union([cov, *[a for a in gap_geoms if a.intersects(g)]])
        if g.intersection(taken).area > 1:
            g = g.difference(taken)
            if g.is_empty:
                continue
            g = g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area)
            g2 = osm_clean(g.buffer(-0.2, join_style=2).buffer(0.2, join_style=2))  # square the cut wall too
            if g2.geom_type == "Polygon" and g2.intersection(taken).area <= 1:
                g = g2
        # a piece whose outline runs along a community shape for over a quarter of its length is the leftover of
        # that building (its drawing and the LiDAR roof differ a little), not a building of its own
        touch = g.exterior.intersection(cov.buffer(0.7)).length / g.exterior.length if g.area > 0 else 1
        # an outline that still has steps after squaring (shared-wall blocks, odd shapes) is not shown
        if g.area >= 40 and short_walls(g) <= 1 and not g.buffer(-1.5).is_empty and g.area / g.minimum_rotated_rectangle.area > 0.6 and touch <= 0.25:
            if lots_spanned(g) >= 2:  # still joins houses on separate lots: not shown
                n_span += 1
                continue
            gap_geoms.append(g)
            gap.append({"type": "Feature", "geometry": mapping(g), "properties": dict(f["properties"], kind="traced gap", **({"replaces": replaces} if replaces else {}))})
n_tall_piece = 0
row_geoms = [q for k in sorted(rows_of) for q in rows_of[k]]
if gap or row_geoms:  # each gap's own heights: the trace's h_max belongs to the whole blob, not to a piece of it
    if LAZ:
        import roofs
        b = unary_union(gap_geoms + row_geoms).bounds
        P = roofs.to_gda2020(roofs.read_points(LAZ, [b[0] - 5, b[1] - 5, b[2] + 5, b[3] + 5]))
        if roofs.roof_density(P) < roofs.DENSE_ROOF:
            roofs.own_buildings(P)  # thin LiDAR: same roof test as the trace
        rows = local_heights(roofs, P, gap_geoms)
        row_h = iter(local_heights(roofs, P, row_geoms))
        for k in sorted(rows_of):  # a mapped row's dwellings, each with its own heights
            hs = [next(row_h) for _ in rows_of[k]]
            whole = {a: S[k]["properties"][a] for a in HKEYS if a in S[k]["properties"]}
            hs = [r if "h_max" in r else whole for r in hs]  # a dwelling with too few points of its own keeps the row's height
            base = {a: v for a, v in S[k]["properties"].items() if a not in HKEYS}
            # `row` = the mapped outline the dwelling was cut from, so tools/mirror/roofs.py can find its OpenStreetMap / Microsoft id
            base["row"] = [[round(x, 2), round(y, 2)] for x, y in SG[k].exterior.coords]
            rows_of[k] = [{"type": "Feature", "geometry": mapping(q), "properties": dict(base, **{a: r[a] for a in HKEYS if a in r})}
                          for q, r in zip(rows_of[k], hs)]
    else:
        rows = [None] * len(gap)
    keep = []
    for g, ft, r in zip(gap_geoms, gap, rows):
        pr = ft["properties"]
        whole = abs(g.area - (pr.get("area_m2") or 0)) <= 0.1 * g.area  # no LAZ: only an uncut trace keeps its heights
        if r is not None or not whole:
            for k in HKEYS:
                pr.pop(k, None)
            pr.update({k: r[k] for k in HKEYS if r and k in r})
        if (pr.get("h_max") or 0) > HIGH_RISE:  # a piece of a tower block
            n_tall_piece += 1; continue
        if (pr.get("h_max") or 0) > THIN_H and 2 * g.area / g.length < THIN_W:
            # a thin piece (terrace strip, or a strip along a taller roof: Gosford, Chatswood pilots) whose top points are a
            # neighbour's: its 90th percentile when that is a plausible height (Surry Hills terraces), else it is not shown
            h90 = None
            if LAZ and "ground" in pr:
                from shapely import contains_xy
                bm = P["c"] == 6
                zb = P["z"][bm][contains_xy(g, P["x"][bm], P["y"][bm])]
                h90 = float(np.percentile(zb, 90)) - pr["ground"] if len(zb) >= 10 else None
            if h90 is None or h90 > THIN_H:
                n_tall_piece += 1; continue
            pr["h_max"] = round(h90, 2); pr["ridge"] = round(pr["ground"] + h90, 2)
        keep.append(ft)
    gap = keep
S2 = []
for k, f in enumerate(S):
    f["properties"]["kind"] = "community shape moved onto LiDAR"
    for q in rows_of.get(k, [f]):
        q["properties"]["kind"] = f["properties"]["kind"]; S2.append(q)
n_mapped_rows = len(rows_of)
S = S2
json.dump({"type": "FeatureCollection", "features": S + gap}, open(out, "w"))
print(f"{len(S)} community shapes + {len(gap)} traced gap roofs -> {out} ({len(LOTS)} lots; {n_span} gaps over 2+ house lots dropped; {n_lidar} traces split by the LiDAR; {n_rows} traced and {n_mapped_rows} mapped terrace rows split into dwellings; {n_fine_ms} Microsoft outlines parted by the fine LiDAR step; {n_ms_split} Microsoft outlines split (MS_SPLIT); {n_high} high-rise traces and {n_tall_piece} tall pieces not traced)", file=sys.stderr)
