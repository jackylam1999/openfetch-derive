#!/usr/bin/env python3
"""Make a traced outline look like a hand-drawn (OSM-style) one: no wall shorter than MIN_EDGE.

Used by gapfill.py on every traced gap roof. The outline is turned so its longest wall is level; each wall then becomes a
line (level, upright, or slanted). Notches narrower than 2 m are closed first. Repeatedly the shortest wall under MIN_EDGE is removed:
- a short step between two parallel walls (a 1-2 m jog) -> the two walls become one, at their length-weighted position;
- a short cap of a narrow tab or notch -> the tab or notch goes;
- a short slanted wall (a cut corner) -> its neighbours meet in a square corner.
The result must still cover the trace (shape overlap at least MIN_IOU), otherwise the plain trace is kept and the pipeline
gate reports it.
"""
import math
import numpy as np
from shapely.geometry import Polygon
from shapely import affinity

MIN_EDGE = 2.0     # m, shortest wall kept (OSM houses: about 5 % of walls are under 2 m)
AXIS_TOL = 20.0    # degrees from the main axes that still count as level/upright
MIN_IOU = 0.85


def _lines(coords):
    """Polygon ring (closed, turned) -> list of [normal, offset, kind, length]; kind 'h', 'v' or 'd'."""
    L = []
    for p, q in zip(coords[:-1], coords[1:]):
        d = q - p; n = math.hypot(*d)
        if n < 1e-6:
            continue
        a = math.degrees(math.atan2(d[1], d[0])) % 180
        if min(a, 180 - a) <= AXIS_TOL: k, nv = "h", np.array([0.0, 1.0])
        elif abs(a - 90) <= AXIS_TOL: k, nv = "v", np.array([1.0, 0.0])
        else: k, nv = "d", np.array([-d[1], d[0]]) / n
        c = float(nv @ ((p + q) / 2))
        L.append([nv, c, k, n])
    return L


def _merge(a, b):
    w = a[3] + b[3]
    return [a[0], (a[1] * a[3] + b[1] * b[3]) / w, a[2], w]


def _join_parallel(L):
    """Neighbouring lines of the same kind (slanted ones only when nearly parallel) become one."""
    changed = True
    while changed and len(L) > 3:
        changed = False
        for i in range(len(L)):
            j = (i + 1) % len(L)
            dot = float(L[i][0] @ L[j][0])
            if L[i][2] == L[j][2] and (L[i][2] != "d" or abs(dot) > 0.97):
                b = L[j] if dot > 0 else [-L[j][0], -L[j][1], "d", L[j][3]]
                L[i] = _merge(L[i], b); del L[j]; changed = True; break
    return L


def _meet(a, b):
    M = np.array([a[0], b[0]])
    if abs(np.linalg.det(M)) < 1e-6:
        return None
    return np.linalg.solve(M, [a[1], b[1]])


def _vertices(L):
    V = [_meet(L[i - 1], L[i]) for i in range(len(L))]
    return None if any(v is None for v in V) else V


def osm_clean(poly, min_edge=MIN_EDGE):
    if poly.is_empty or poly.geom_type != "Polygon":
        return poly
    shut = Polygon(poly.exterior).buffer(1, join_style=2).buffer(-1, join_style=2)  # close notches under 2 m wide
    if shut.geom_type == "Polygon" and not shut.is_empty:
        poly = shut
    c = np.asarray(poly.exterior.coords)
    d = np.diff(c, axis=0); k = int(np.argmax(np.hypot(*d.T)))
    ang = math.degrees(math.atan2(d[k][1], d[k][0])); o = poly.centroid
    r = affinity.rotate(Polygon(poly.exterior), -ang, origin=o)
    L = _join_parallel(_lines(np.asarray(r.exterior.coords)))
    for _ in range(200):
        if len(L) <= 4:
            break
        V = _vertices(L)
        if V is None:
            return poly
        n = len(L)
        lens = [float(np.hypot(*(V[(i + 1) % n] - V[i]))) for i in range(n)]
        for i in range(n):
            L[i][3] = max(lens[i], 1e-3)
        i = int(np.argmin(lens))
        if lens[i] >= min_edge:
            break
        del L[i]
        L = _join_parallel(L)
    V = _vertices(L)
    if V is None or len(V) < 3:
        return poly
    out = Polygon(V).buffer(0)
    if out.geom_type == "MultiPolygon":
        out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty:
        return poly
    out = affinity.rotate(out, ang, origin=o).simplify(0.05)
    inter = out.intersection(poly).area; uni = out.union(poly).area
    return out if uni > 0 and inter / uni >= MIN_IOU else poly


def short_walls(poly, limit=MIN_EDGE):
    c = np.asarray(poly.exterior.coords)
    return int((np.hypot(*np.diff(c, axis=0).T) < limit).sum())


def edge_share(geoms, limit):
    """Share of outline edges shorter than limit metres."""
    e = []
    for g in geoms:
        for p in (g.geoms if hasattr(g, "geoms") else [g]):
            c = np.asarray(p.exterior.coords); e.extend(np.hypot(*np.diff(c, axis=0).T))
    return float((np.array(e) < limit).mean()) if e else 0.0
