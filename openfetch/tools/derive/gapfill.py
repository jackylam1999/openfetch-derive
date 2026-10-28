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
LOTS = [shape(f["geometry"]) for f in json.load(open(sys.argv[5]))["features"]] if len(sys.argv) > 5 else []
LAZ = sys.argv[6:]
lot_tree = STRtree(LOTS) if LOTS else None
HOUSE_LOT = (100, 2000)  # m2: a lot that holds one house (Gregory Hills median 430 m2)
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


def lots_spanned(g):
    """House lots holding a real part of the outline (at least 15 m2 and a tenth of it)."""
    return sum(1 for i in (hl_tree.query(g) if hl_tree else []) if house_lots[i].intersection(g).area >= max(15, 0.1 * g.area))
gap, gap_geoms, n_span = [], [], 0
def house_lot(g):
    return any(house_lots[i].intersection(g).area >= 0.5 * g.area for i in (hl_tree.query(g) if hl_tree else []))


# each lot's piece of a trace is judged on its own: a loose community house on one lot blocks only that piece
work = [(f, p) for f in T for p in by_lots(shape(f["geometry"]))]
n_lidar = 0
if LAZ:  # pieces on no house lot that could hold 2+ houses: split by the LiDAR
    todo = [i for i, (f, p) in enumerate(work) if p.area >= 2 * MIN_PART + 20 and not house_lot(p)]
    if todo:
        P = lidar_points([work[i][1] for i in todo])
        for i in todo:
            parts = by_lidar(work[i][1], P)
            if len(parts) > 1:
                n_lidar += 1; work[i] = [(work[i][0], q) for q in parts]
        work = [w for x in work for w in (x if isinstance(x, list) else [x])]
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
for f in S:
    f["properties"]["kind"] = "community shape moved onto LiDAR"
json.dump({"type": "FeatureCollection", "features": S + gap}, open(out, "w"))
print(f"{len(S)} community shapes + {len(gap)} traced gap roofs -> {out} ({len(LOTS)} lots; {n_span} gaps over 2+ house lots dropped; {n_lidar} traces split by the LiDAR)", file=sys.stderr)
