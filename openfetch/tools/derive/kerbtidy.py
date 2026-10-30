#!/usr/bin/env python3
"""Tidy traced kerb lines the way a drafter would (Jacky 30 Oct 2026): join short gaps where two ends carry on in the same direction,
make straight runs exactly straight (a best-fit line through the traced points), and smooth the curves between them.

tidy(lines, gap, straight, tol) -> lines   (shapely LineStrings in metres)
  gap       join ends up to this far apart (m) when they line up (kerb hidden under a car or a tree)
  straight  a run counts as straight when it is at least this long (m) and no traced point is more than tol m off its chord
"""
import numpy as np
from shapely.geometry import LineString


def fit(P):
    """Best-fit straight segment through points P (total least squares), from the first to the last point's projection."""
    c = P.mean(0); u = np.linalg.svd(P - c, full_matrices=False)[2][0]
    t = (P - c) @ u
    return c + np.outer([t[0], t[-1]], u)


def runs(P, tol):
    """Split a traced polyline at its corners (Douglas-Peucker with tol); returns index ranges of the pieces."""
    keep = [0, len(P) - 1]; stack = [(0, len(P) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        d = P[b] - P[a]; n = np.hypot(*d)
        q = P[a + 1:b] - P[a]
        off = np.abs(d[0] * q[:, 1] - d[1] * q[:, 0]) / n if n > 1e-9 else np.hypot(q[:, 0], q[:, 1])
        k = int(np.argmax(off))
        if off[k] > tol:
            keep.append(a + 1 + k); stack += [(a, a + 1 + k), (a + 1 + k, b)]
    keep = sorted(set(keep))
    return list(zip(keep[:-1], keep[1:]))


def chaikin(P, n=2):
    for _ in range(n):
        if len(P) < 3:
            return P
        Q = np.empty((2 * (len(P) - 1), 2))
        Q[0::2] = 0.75 * P[:-1] + 0.25 * P[1:]; Q[1::2] = 0.25 * P[:-1] + 0.75 * P[1:]
        P = np.vstack([P[:1], Q, P[-1:]])
    return P


def shape_line(l, straight, tol):
    P = np.asarray(l.coords)
    if len(P) < 3:
        return l
    out = []
    for a, b in runs(P, tol):
        seg = P[a:b + 1]
        if np.hypot(*(seg[-1] - seg[0])) >= straight:
            out.append(("s", fit(seg)))
        else:
            out.append(("c", seg))
    pts = []
    for i, (kind, seg) in enumerate(out):
        if kind == "c":
            seg = chaikin(seg)
        pts.append(seg if not pts else seg[1:] if kind == "c" else seg)
    Q = np.vstack(pts)
    keep = np.r_[True, np.hypot(*np.diff(Q, axis=0).T) > 0.05]
    return LineString(Q[keep]) if keep.sum() > 1 else l


def join(ls, gap, side=0.6):
    """Join line ends up to gap m apart when the second end lies on the straight carry-on of the first (within side m) and both
    ends face each other: a kerb hidden under a car, a tree or a shadow."""
    from shapely.ops import linemerge
    ends = []
    for i, l in enumerate(ls):
        c = np.asarray(l.coords)
        if len(c) < 2 or l.length < 3:
            continue
        for e, f in ((c[0], c[np.searchsorted(np.r_[0, np.cumsum(np.hypot(*np.diff(c, axis=0).T))], 3.0).clip(1, len(c) - 1)]),
                     (c[-1], c[::-1][np.searchsorted(np.r_[0, np.cumsum(np.hypot(*np.diff(c[::-1], axis=0).T))], 3.0).clip(1, len(c) - 1)])):
            d = e - f; ends.append((i, e, d / max(np.hypot(*d), 1e-6)))
    if not ends:
        return ls
    E = np.array([e[1] for e in ends]); new, used = [], set()
    for a, (i, e, d) in enumerate(ends):
        if a in used:
            continue
        v = E - e; dist = np.hypot(v[:, 0], v[:, 1]); along = v @ d; off = np.abs(v[:, 0] * d[1] - v[:, 1] * d[0])
        ok = [b for b in np.argsort(dist) if b != a and b not in used and ends[b][0] != i and 0 < along[b] <= gap
              and off[b] <= side and ends[b][2] @ d < -0.95]
        if ok:
            used |= {a, ok[0]}; new.append(LineString([e, E[ok[0]]]))
    m = linemerge(ls + new)
    return list(getattr(m, "geoms", [m]))


def tidy(lines, gap=6.0, straight=8.0, tol=0.25):
    ls = join(list(lines), gap) if gap else list(lines)
    return [shape_line(l, straight, tol) for l in ls]
