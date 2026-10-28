#!/usr/bin/env python3
"""Roof outlines with heights from classified LiDAR point clouds (offline, no AI).

Usage: python3 tools/derive/roofs.py out.geojson tile1.laz [tile2.laz ...] [--cell 0.5] [--min-area 20]
       [--bbox xmin ymin xmax ymax] [--epsg 7856] [--shrink 0.3]

Input: LAS/LAZ with ASPRS classes (2 ground, 6 building), metres, heights in the file's datum (NSW: AHD).
Output: GeoJSON polygons in the tile's grid (metres) with ground, eave and ridge levels (same datum),
heights above ground, point counts and a quality flag. Nothing is traced by hand or by a model: the
outline is the footprint of the building-class points on a `cell` metre grid, cleaned, polygonised,
simplified and squared where the walls are near right angles.
Steps: read -> grid mask -> close 1 cell, drop blobs < min-area -> polygonise -> simplify (0.75 cell)
-> regularise (straight walls, square corners, rectangles) -> heights from the points inside -> drop roofs on water.
"""
import sys, json, math
import numpy as np
import laspy
from scipy import ndimage
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
import rasterio.features
from rasterio.transform import from_origin

CLASS_GROUND, CLASS_BUILDING, CLASS_WATER = 2, 6, 9
CLASS_UNCLASSIFIED, CLASS_VEG, CLASS_OVERLAP = 1, (3, 4, 5), 12
# Thin LiDAR (28 Oct 2026). A grid cell must be about as wide as the spacing of the roof points, or the outline is mostly holes:
# Bowral 2014 has 0.9-1.7 building points per m2 on roofs: the 0.5 m grid found 22 % of the OSM/Microsoft roof area, 0.75 m 61 %, 1.0 m 67 %.
# Dense LiDAR (2019+ Spatial Services, 4+ pts/m2 on roofs) keeps the 0.5 m grid and its own classes, so its output is unchanged.
DENSE_ROOF = 3.2            # building points per m2 of roof from which the survey's own classes are used as they are
CELL_K = 1.3                # cell = CELL_K / sqrt(roof density), between 0.5 and 1.0 m
MIN_HAG = 2.0               # m above ground for a roof point of our own
MAX_PLANE_RMS = 0.1         # m, spread of a point's 10 neighbours about their plane (roofs ~0.03, tree crowns 0.3+)


def cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def args(argv):
    o = {"cell": 0.5, "min_area": 20.0, "bbox": None, "epsg": None, "files": [], "out": None, "shrink": 0.3, "mode": "rect", "cell_set": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cell": o["cell"] = float(argv[i + 1]); o["cell_set"] = True; i += 2
        elif a == "--min-area": o["min_area"] = float(argv[i + 1]); i += 2
        elif a == "--mode": o["mode"] = argv[i + 1]; i += 2
        elif a == "--shrink": o["shrink"] = float(argv[i + 1]); i += 2
        elif a == "--epsg": o["epsg"] = int(argv[i + 1]); i += 2
        elif a == "--bbox": o["bbox"] = [float(v) for v in argv[i + 1:i + 5]]; i += 5
        elif o["out"] is None: o["out"] = a; i += 1
        else: o["files"].append(a); i += 1
    if not o["out"] or not o["files"]:
        sys.exit(__doc__)
    return o


def read_points(files, bbox):
    """All points of the given classes from every file, clipped to bbox. Returns dict of arrays."""
    xs, ys, zs, cs, ns = [], [], [], [], []
    crs = None
    for f in files:
        with laspy.open(f) as rd:
            if crs is None:
                try: crs = rd.header.parse_crs()
                except Exception: crs = None
            for pts in rd.chunk_iterator(5_000_000):
                c = np.asarray(pts.classification)
                keep = np.isin(c, (CLASS_GROUND, CLASS_BUILDING, CLASS_WATER, CLASS_UNCLASSIFIED, CLASS_OVERLAP) + CLASS_VEG)
                x = np.asarray(pts.x)[keep]; y = np.asarray(pts.y)[keep]
                z = np.asarray(pts.z)[keep]; c = c[keep]; n = np.asarray(pts.number_of_returns)[keep]
                if bbox:
                    m = (x >= bbox[0]) & (x <= bbox[2]) & (y >= bbox[1]) & (y <= bbox[3])
                    x, y, z, c, n = x[m], y[m], z[m], c[m], n[m]
                xs.append(x); ys.append(y); zs.append(z); cs.append(c); ns.append(n)
    P = {"x": np.concatenate(xs), "y": np.concatenate(ys), "z": np.concatenate(zs), "c": np.concatenate(cs), "n": np.concatenate(ns)}
    P["crs"] = crs
    return P


def to_gda2020(P):
    """Tiles older than ~2018 are GDA94 MGA (EPSG 283zz): move them to GDA2020 MGA (EPSG 78zz, ~1.8 m) so every
    source shares the grid of the reference layers. Heights (AHD) are unchanged."""
    epsg = P["crs"].to_epsg() if P["crs"] is not None else None
    if epsg and 28348 <= epsg <= 28358:
        from pyproj import Transformer
        t = Transformer.from_crs(epsg, epsg - 28348 + 7848, always_xy=True)
        P["x"], P["y"] = t.transform(P["x"], P["y"])
        P["crs"] = None
        print(f"shifted GDA94 MGA {epsg} -> GDA2020 {epsg - 28348 + 7848}", file=sys.stderr)
    return P


def roof_density(P):
    """Building points per m2 of roof: building points over the area of the 2 m cells holding 3 or more of them."""
    b = P["c"] == CLASS_BUILDING
    if b.sum() < 100:
        return 0.0
    k = np.unique(np.floor(P["x"][b] / 2).astype(np.int64) * 10_000_000 + np.floor(P["y"][b] / 2).astype(np.int64), return_counts=True)[1]
    return float(k[k >= 3].sum() / (4.0 * max(1, (k >= 3).sum())))


def own_buildings(P):
    """Thin LiDAR: mark overlap (class 12) and unclassified points as building when they are roofs by our own test. A roof
    point stands MIN_HAG m or more above the ground (2 m ground grid from the class 2 points), is the only return of its
    pulse (leaves give several), lies on a plane with its 10 nearest roof-candidate or building neighbours (spread at most
    MAX_PLANE_RMS m) and has fewer vegetation than building points among the survey's classified points within 1.5 m."""
    from scipy.spatial import cKDTree
    c = P["c"]; g = c == CLASS_GROUND
    if g.sum() < 100:
        return 0
    x0, y0 = P["x"].min(), P["y"].min()
    gi, gj = ((P["x"][g] - x0) // 2).astype(int), ((P["y"][g] - y0) // 2).astype(int)
    nr, nc = int((P["x"].max() - x0) // 2) + 1, int((P["y"].max() - y0) // 2) + 1
    dem = np.full((nr, nc), np.inf)
    np.minimum.at(dem, (gi, gj), P["z"][g])
    empty = ~np.isfinite(dem)
    if empty.any():
        _, (ii, jj) = ndimage.distance_transform_edt(empty, return_indices=True)
        dem = dem[ii, jj]
    hag = P["z"] - dem[((P["x"] - x0) // 2).astype(int).clip(0, nr - 1), ((P["y"] - y0) // 2).astype(int).clip(0, nc - 1)]
    cand = np.isin(c, (CLASS_OVERLAP, CLASS_UNCLASSIFIED)) & (hag >= MIN_HAG) & (P["n"] == 1)
    ci = np.nonzero(cand)[0]
    if not len(ci):
        return 0
    pool = np.nonzero(cand | (c == CLASS_BUILDING))[0]
    xyz = np.column_stack([P["x"][pool], P["y"][pool], P["z"][pool]])
    d, nb = cKDTree(xyz).query(np.column_stack([P["x"][ci], P["y"][ci], P["z"][ci]]), k=10, distance_upper_bound=2.0)
    full = np.isfinite(d).all(axis=1)
    planar = np.zeros(len(ci), bool)
    if full.any():
        Q = xyz[nb[full]]
        Q = Q - Q.mean(axis=1, keepdims=True)
        ev = np.linalg.eigvalsh(np.einsum("nki,nkj->nij", Q, Q) / Q.shape[1])
        planar[full] = np.sqrt(np.maximum(ev[:, 0], 0)) <= MAX_PLANE_RMS
    lab = np.nonzero(np.isin(c, CLASS_VEG + (CLASS_BUILDING,)))[0]
    tv = cKDTree(np.column_stack([P["x"][lab], P["y"][lab]]))
    near = tv.query_ball_point(np.column_stack([P["x"][ci[planar]], P["y"][ci[planar]]]), r=1.5)
    isveg = np.isin(c[lab], CLASS_VEG)
    ok = np.array([isveg[k].sum() < (len(k) - isveg[k].sum()) or not k for k in near], bool) if len(near) else np.zeros(0, bool)
    roof = ci[planar][ok]
    c[roof] = CLASS_BUILDING
    return len(roof)


def ring_density(P, poly):
    """Points of any class per m2 in the 1-4 m ring around a roof."""
    from shapely import contains_xy
    ring = poly.buffer(4).difference(poly.buffer(1))
    a, b, c, d = ring.bounds
    m = np.nonzero((P["x"] >= a) & (P["x"] <= c) & (P["y"] >= b) & (P["y"] <= d))[0]
    return contains_xy(ring, P["x"][m], P["y"][m]).sum() / ring.area if ring.area else 0


def building_mask(P, cell):
    """Boolean grid of cells holding building points, closed by one cell. Returns mask, transform, origin."""
    b = P["c"] == CLASS_BUILDING
    if not b.any():
        return None, None, None
    x0 = math.floor(P["x"].min() / cell) * cell - cell
    y1 = math.ceil(P["y"].max() / cell) * cell + cell
    ncol = int(math.ceil((P["x"].max() - x0) / cell)) + 2
    nrow = int(math.ceil((y1 - P["y"].min()) / cell)) + 2
    col = ((P["x"][b] - x0) / cell).astype(int)
    row = ((y1 - P["y"][b]) / cell).astype(int)
    mask = np.zeros((nrow, ncol), dtype=bool)
    mask[row, col] = True
    # close 1-cell gaps (sparse returns on dark roofs), then open to drop 1-cell specks
    r = 1  # 1 cell: a wider closing joined neighbouring buildings at Tweed Heads
    disk = np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
    mask = ndimage.binary_closing(mask, structure=disk, iterations=1)
    mask = ndimage.binary_fill_holes(mask)
    mask = ndimage.binary_opening(mask, structure=np.ones((2, 2)))
    return mask, from_origin(x0, y1, cell, cell), (x0, y1)


def polygons(mask, transform, cell, min_area, shrink=0.3, P_b=None, mode="rect"):
    """Polygonise the mask; drop small blobs; simplify and square each outline."""
    out = []
    for geom, val in rasterio.features.shapes(mask.astype(np.uint8), mask=mask, transform=transform, connectivity=4):
        if val != 1:
            continue
        poly = shape(geom)
        if poly.area < min_area:
            continue
        # cells reach past the true edge: pull the outline back (0.3 cell gave area ratio 1.00 on the synthetic tile)
        poly = poly.buffer(-shrink * cell, join_style=2)
        if poly.geom_type != "Polygon":
            poly = max(poly.geoms, key=lambda g: g.area) if not poly.is_empty else poly
        if poly.is_empty or poly.area < min_area:
            continue
        if mode == "br":
            pass  # squared later, all at once, by the Building-Regulariser library (see regularise_all)
        elif mode == "rect" and P_b is not None:
            r = rectilinear(poly, P_b)
            poly = r if r is not None and r.area >= min_area else regularise(poly)
        else:
            poly = regularise(poly)
        if not poly.is_empty:
            out.append(poly)
    return out


def regularise_all(polys, epsg):
    """Square every outline with Building-Regulariser (DPIRD-DMA, MIT, pip install buildingregulariser): edges snap to
    the building's main directions (45 degrees allowed, round buildings kept round) and neighbours share a direction."""
    import geopandas as gpd
    from buildingregulariser import regularize_geodataframe
    # 1 m open + close first: removes the one-cell teeth that sparse LiDAR (4 pts/m2) leaves along walls
    sm = [p.buffer(-1, join_style=2).buffer(1, join_style=2).buffer(1, join_style=2).buffer(-1, join_style=2) for p in polys]
    sm = [g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area) for g in sm if not g.is_empty]
    gdf = gpd.GeoDataFrame(geometry=sm, crs=f"EPSG:{epsg or 7856}")
    out = regularize_geodataframe(gdf, simplify_tolerance=1.5, neighbor_alignment=True, neighbor_search_distance=40)
    return [g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area) for g in out.geometry]


def rectilinear(poly, P_b, cell=0.5, notch=1.5):
    """Clean, OSM-like outline for one building: turn its building points into the building's own wall frame, grid them
    there at `cell` m (so every grid edge is parallel to a wall), close and open with a `notch` m square (removes
    wobble and notches smaller than that), polygonise, and turn back. Every edge comes out straight and every corner
    square. Oblique or curved walls become small steps of at least `notch` m."""
    from shapely.geometry import shape as shp_
    from shapely import contains_xy
    from shapely.affinity import rotate
    a = main_axis(poly.simplify(0.7))
    x, y = P_b
    minx, miny, maxx, maxy = poly.buffer(1.0).bounds
    m = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    if m.sum() < 10:
        return None
    xs, ys = x[m], y[m]
    k = contains_xy(poly.buffer(cell), xs, ys)
    xs, ys = xs[k], ys[k]
    if len(xs) < 10:
        return None
    cx, cy = poly.centroid.x, poly.centroid.y
    ca, sa = math.cos(-a), math.sin(-a)
    u = (xs - cx) * ca - (ys - cy) * sa
    v = (xs - cx) * sa + (ys - cy) * ca
    u0, v1 = u.min() - 2 * notch, v.max() + 2 * notch
    nc = int((u.max() + 2 * notch - u0) / cell) + 1
    nr = int((v1 - (v.min() - 2 * notch)) / cell) + 1
    g = np.zeros((nr, nc), bool)
    g[((v1 - v) / cell).astype(int), ((u - u0) / cell).astype(int)] = True
    n = max(1, int(round(notch / cell)))
    st = np.ones((n, n), bool)
    g = ndimage.binary_closing(g, structure=st)
    g = ndimage.binary_fill_holes(g)
    g = ndimage.binary_opening(g, structure=st)
    best = None
    for geom, val in rasterio.features.shapes(g.astype(np.uint8), mask=g, transform=from_origin(u0, v1, cell, cell), connectivity=4):
        q = shp_(geom)
        if best is None or q.area > best.area:
            best = q
    if best is None:
        return None
    best = best.simplify(0.01)  # drop collinear grid vertices only
    # cells reach past the true edge on every side by about 0.3 cell (same pull-back as the main mask)
    best = best.buffer(-0.3 * cell, join_style=2)
    if best.is_empty:
        return None
    if best.geom_type == "MultiPolygon":
        best = max(best.geoms, key=lambda q: q.area)
    out = rotate(best, math.degrees(a), origin=(0, 0), use_radians=False)
    from shapely.affinity import translate
    return translate(out, cx, cy)


def regularise(poly, dp=0.7, ang_tol=20.0, merge_off=0.9):
    """Straight walls, square corners. Douglas-Peucker (dp m), snap edges within ang_tol deg of the building's two main
    directions, merge neighbouring parallel walls closer than merge_off m, put a short perpendicular step between
    parallel walls further apart, then rebuild corners as line intersections. A rectangle-like building (fills 92 %
    of its minimum rotated rectangle) becomes that rectangle. Falls back to the simplified outline when the result
    moves more than 1.5 m or changes the area by more than 12 %."""
    from shapely.geometry import Polygon as P_
    simple = poly.simplify(dp, preserve_topology=True)
    if simple.geom_type != "Polygon" or simple.is_empty:
        return poly
    mrr = poly.minimum_rotated_rectangle
    if mrr.area > 0 and poly.area / mrr.area >= 0.92:
        return mrr
    a = main_axis(simple)
    ca, sa = math.cos(-a), math.sin(-a)
    ring = np.asarray(simple.exterior.coords)[:-1]
    R = np.column_stack([ring[:, 0] * ca - ring[:, 1] * sa, ring[:, 0] * sa + ring[:, 1] * ca])
    n = len(R)
    if n < 3:
        return simple
    tol = math.radians(ang_tol)
    E = []  # [kind, offset_or_None, length, p, q]
    for i in range(n):
        p, q = R[i], R[(i + 1) % n]
        d = q - p; L = math.hypot(*d)
        if L < 1e-6:
            continue
        ang = math.atan2(d[1], d[0]) % math.pi
        if min(ang, math.pi - ang) <= tol:
            E.append(["h", (p[1] + q[1]) / 2, L, p, q])
        elif abs(ang - math.pi / 2) <= tol:
            E.append(["v", (p[0] + q[0]) / 2, L, p, q])
        else:
            E.append(["o", None, L, p, q])
    # drop short oblique edges between snapped ones (pixel stair-steps)
    E = [e for e in E if not (e[0] == "o" and e[2] < 1.5)] or E
    # merge consecutive same-kind walls with close offsets (cyclic)
    changed = True
    while changed and len(E) > 3:
        changed = False
        for i in range(len(E)):
            j = (i + 1) % len(E)
            e, f = E[i], E[j]
            if e[0] == f[0] and e[0] != "o" and abs(e[1] - f[1]) < merge_off:
                off = (e[1] * e[2] + f[1] * f[2]) / (e[2] + f[2])
                E[i] = [e[0], off, e[2] + f[2], e[3], f[4]]
                del E[j]
                changed = True
                break
    # parallel neighbours far apart: insert a perpendicular step at the junction
    F = []
    for i in range(len(E)):
        e, f = E[i], E[(i + 1) % len(E)]
        F.append(e)
        if e[0] == f[0] and e[0] != "o":
            jx, jy = e[4]
            F.append(["v", jx, 0.0, e[4], f[3]] if e[0] == "h" else ["h", jy, 0.0, e[4], f[3]])
    E = F
    if len(E) < 3:
        return simple
    def line(e):
        if e[0] == "h": return np.array([0.0, e[1]]), np.array([1.0, 0.0])
        if e[0] == "v": return np.array([e[1], 0.0]), np.array([0.0, 1.0])
        d = e[4] - e[3]; return (e[3] + e[4]) / 2, d / np.linalg.norm(d)
    pts = []
    for i in range(len(E)):
        (p1, d1), (p2, d2) = line(E[i]), line(E[(i + 1) % len(E)])
        den = cross(d1, d2)
        if abs(den) < 1e-6:
            pts.append(E[i][4]); continue
        t = cross(p2 - p1, d2) / den
        pts.append(p1 + t * d1)
    V = np.asarray(pts)
    ca, sa = math.cos(a), math.sin(a)
    W = np.column_stack([V[:, 0] * ca - V[:, 1] * sa, V[:, 0] * sa + V[:, 1] * ca])
    out = P_(W)
    if not out.is_valid:
        out = out.buffer(0)
        if out.geom_type == "MultiPolygon":
            out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty or out.geom_type != "Polygon":
        return simple
    if abs(out.area / poly.area - 1) > 0.12 or out.hausdorff_distance(poly) > 1.5:
        return simple
    return out


def main_axis(poly):
    """Dominant wall direction (radians, in [0, pi/2)) weighted by edge length."""
    ring = np.asarray(poly.exterior.coords)
    d = np.diff(ring, axis=0)
    ang = np.arctan2(d[:, 1], d[:, 0]) % (math.pi / 2)
    w = np.hypot(d[:, 0], d[:, 1])
    # circular mean on a quarter turn
    s = (w * np.sin(4 * ang)).sum(); c = (w * np.cos(4 * ang)).sum()
    return (math.atan2(s, c) / 4) % (math.pi / 2)


def square(poly, tol_deg):
    """Make edges within tol_deg of the main axes exactly axis-parallel; keep other edges as they are."""
    if poly.geom_type != "Polygon":
        return None
    a = main_axis(poly)
    ca, sa = math.cos(-a), math.sin(-a)
    ring = np.asarray(poly.exterior.coords)[:-1]
    R = np.column_stack([ring[:, 0] * ca - ring[:, 1] * sa, ring[:, 0] * sa + ring[:, 1] * ca])
    n = len(R)
    if n < 4:
        return None
    lines = []  # each edge as (point, direction) in the rotated frame
    tol = math.radians(tol_deg)
    for i in range(n):
        p, q = R[i], R[(i + 1) % n]
        d = q - p
        L = math.hypot(*d)
        if L == 0:
            continue
        ang = math.atan2(d[1], d[0])
        k = round(ang / (math.pi / 2))
        if abs(ang - k * math.pi / 2) <= tol:
            d = np.array([math.cos(k * math.pi / 2), math.sin(k * math.pi / 2)])
        else:
            d = d / L
        lines.append(((p + q) / 2, d))
    # merge consecutive parallel lines (same axis) by averaging their offsets
    merged = []
    for m, d in lines:
        if merged and abs(cross(merged[-1][1], d)) < 1e-6:
            pm, dm = merged[-1]
            merged[-1] = ((pm + m) / 2, dm)
        else:
            merged.append((m, d))
    if len(merged) > 1 and abs(cross(merged[0][1], merged[-1][1])) < 1e-6:
        pm, dm = merged.pop()
        merged[0] = ((merged[0][0] + pm) / 2, merged[0][1])
    if len(merged) < 3:
        return None
    pts = []
    for i in range(len(merged)):
        (p1, d1), (p2, d2) = merged[i], merged[(i + 1) % len(merged)]
        den = cross(d1, d2)
        if abs(den) < 1e-6:
            return None
        t = cross(p2 - p1, d2) / den
        pts.append(p1 + t * d1)
    V = np.asarray(pts)
    ca, sa = math.cos(a), math.sin(a)
    W = np.column_stack([V[:, 0] * ca - V[:, 1] * sa, V[:, 0] * sa + V[:, 1] * ca])
    sq = Polygon(W)
    if not sq.is_valid:
        sq = sq.buffer(0)
    return sq if sq.geom_type == "Polygon" else None


def heights(P, polys, cell):
    """Ground (ring 1-4 m outside), eave (10th pct), ridge (98th pct) and mean roof levels per polygon."""
    from shapely.strtree import STRtree
    from shapely.geometry import Point
    b = P["c"] == CLASS_BUILDING
    g = P["c"] == CLASS_GROUND
    w = P["c"] == CLASS_WATER
    wx, wy = P["x"][w], P["y"][w]
    bx, by, bz = P["x"][b], P["y"][b], P["z"][b]
    gx, gy, gz = P["x"][g], P["y"][g], P["z"][g]
    rows = []
    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        m = (bx >= minx) & (bx <= maxx) & (by >= miny) & (by <= maxy)
        inside = m.copy()
        idx = np.nonzero(m)[0]
        if len(idx):
            from shapely import contains_xy
            inside[idx] = contains_xy(poly, bx[idx], by[idx])
        zb = bz[inside]
        ring = poly.buffer(4).difference(poly.buffer(1))
        rminx, rminy, rmaxx, rmaxy = ring.bounds
        gm = (gx >= rminx) & (gx <= rmaxx) & (gy >= rminy) & (gy <= rmaxy)
        gidx = np.nonzero(gm)[0]
        zg = np.array([])
        if len(gidx):
            from shapely import contains_xy
            keep = contains_xy(ring, gx[gidx], gy[gidx])
            zg = gz[gidx][keep]
        nw = 0
        wm = (wx >= rminx) & (wx <= rmaxx) & (wy >= rminy) & (wy <= rmaxy)
        if wm.any():
            from shapely import contains_xy
            nw = int(contains_xy(ring, wx[wm], wy[wm]).sum())
        r = {"n_roof": int(len(zb)), "n_ground": int(len(zg)), "n_water": nw, "area_m2": round(poly.area, 1)}
        r["ground_density"] = round(len(zg) / ring.area, 2) if ring.area else 0
        r["density"] = round(len(zb) / poly.area, 2) if poly.area else 0
        if len(zb) >= 10:
            r["eave"] = round(float(np.percentile(zb, 10)), 2)
            r["ridge"] = round(float(np.percentile(zb, 98)), 2)
            r["roof_mean"] = round(float(zb.mean()), 2)
        if len(zg) >= 5:
            r["ground"] = round(float(np.median(zg)), 2)
        if "ground" in r and "ridge" in r:
            r["h_max"] = round(r["ridge"] - r["ground"], 2)
            r["h_eave"] = round(r["eave"] - r["ground"], 2)
            r["h_mean"] = round(r["roof_mean"] - r["ground"], 2)
        r["on_water"] = nw > max(20, len(zg))  # final call in main(): also too little ground around it
        r["quality"] = "ok" if r["n_roof"] >= 10 and r["n_ground"] >= 5 and r["density"] >= 1 and not r["on_water"] else "low"
        rows.append(r)
    return rows


def main():
    o = args(sys.argv[1:])
    P = read_points(o["files"], o["bbox"])
    P = to_gda2020(P)
    print(f"points kept: {len(P['x'])} (ground {(P['c']==CLASS_GROUND).sum()}, building {(P['c']==CLASS_BUILDING).sum()}), crs {P['crs']}", file=sys.stderr)
    d = roof_density(P)
    thin = d < DENSE_ROOF and not o["cell_set"]
    if thin:
        n = own_buildings(P)
        d = roof_density(P)
        o["cell"] = float(np.clip(round(CELL_K / math.sqrt(max(d, 0.1)) * 4) / 4, 0.5, 1.0))
        print(f"thin LiDAR: {n} overlap/unclassified points made building by our own test, roof density {d:.1f} pts/m2, grid {o['cell']} m", file=sys.stderr)
    mask, transform, _ = building_mask(P, o["cell"])
    b = P["c"] == CLASS_BUILDING
    polys = polygons(mask, transform, o["cell"], o["min_area"], o["shrink"], (P["x"][b], P["y"][b]), o["mode"]) if mask is not None else []
    epsg = o["epsg"] or (P["crs"].to_epsg() if P["crs"] is not None else None)  # None after a GDA94 shift: pass --epsg
    if o["mode"] == "br" and polys:
        polys = regularise_all(polys, epsg)
    rows = heights(P, polys, o["cell"])
    pd = len(P["x"]) / max(1.0, (P["x"].max() - P["x"].min()) * (P["y"].max() - P["y"].min()))
    feats = []
    # boats, pontoons and jetties stand on water, which LiDAR rarely returns as ground: a roof whose 1-4 m ring holds
    # less than a quarter of the box's usual ground density is not on land (Tweed Heads 2023: real buildings >= 8/m2)
    gd = np.median([r["ground_density"] for r in rows]) if rows else 0
    for poly, r in zip(polys, rows):
        if r["ground_density"] < 0.25 * gd:
            # thin LiDAR has few ground points beside walls in town centres: there a roof is on water only when its ring
            # holds few points of any class too (Bowral 2014 lost whole shop blocks as boats)
            r["on_water"] = bool(not thin or ring_density(P, poly) < 0.25 * pd)
    dropped = 0
    for poly, r in zip(polys, rows):
        if r.get("on_water"):
            dropped += 1; continue
        r.update({"source": "OpenFetch derived from NSW Spatial Services LiDAR (ELVIS, CC BY 4.0)", "method": "roofs.py v3 " + o["mode"]})
        feats.append({"type": "Feature", "geometry": mapping(poly), "properties": r})
    fc = {"type": "FeatureCollection", "features": feats}
    if epsg:
        fc["crs"] = {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}}
    with open(o["out"], "w") as f:
        json.dump(fc, f)
    print(f"{len(feats)} roofs -> {o['out']} ({dropped} on water dropped: boats, pontoons)", file=sys.stderr)


if __name__ == "__main__":
    main()
