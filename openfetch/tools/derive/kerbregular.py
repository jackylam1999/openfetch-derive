#!/usr/bin/env python3
"""Turn traced kerb lines into drafted ones (Jacky 5 Nov 2026: "either straight or a perfect curve, not a pencil sketch;
where it is unsure, the frontage is obviously straight").

Every kerb becomes a chain of exact straight lines and exact circular arcs that meet without a kink (tangent continuous).
Straight runs that sit beside a straight property frontage (NSW cadastre lot edges, CC BY 4.0) are made exactly parallel to it.
Two pieces on the same frontage at the same distance from it are joined across a gap when the frontage carries on along the whole
gap (a kerb hidden by a car or a tree, never across a side street, where there is no lot edge).

How one line is fitted (fit_lf, used for about 88% of lines):
  1. resample every 0.5 m; heading from a lightly smoothed copy;
  2. split the heading curve into pieces where it is flat (straight) or changes steadily (arc);
  3. each straight is a least-squares line through its own points (so it keeps the trace's sideways position); when it runs
     within 3 degrees of a lot edge beside it, it takes that edge's exact direction; each arc is a least-squares circle;
  4. two straights meet with a tangent arc fitted to the corner points; other neighbours meet where they cross.
  A line fit_lf cannot draw within 0.6 m (rms) falls back to fit_one: a least-squares curve whose heading is constant on straights
  and linear on arcs (tangent continuous everywhere). Parramatta check (5 Nov 2026, council kerbs, 1 m): found 72.0 -> 71.3 %,
  precise 86.6 -> 85.5 %, within 0.5 m 56.9 -> 56.4 %.

  python kerbregular.py run kerbs-in.geojson lots_dir kerbs-out.geojson [--epsg 7856]
      lots_dir holds lot GeoJSON in the same EPSG (any file names); output keeps every property, adds "shape": "regular",
      and lines made by joining get source "street offset" on the joined part (as kerbstreet.py fills).
  python kerbregular.py lots cells.json lots_dir     fetch NSW cadastre lots for 1 km cells [[x, y], ...] (EPSG 7856)
  python kerbregular.py roads cells.json roads_dir   the same for NSW road centrelines (Transport theme layer 5)
"""
import sys, os, json, glob
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares
from shapely.geometry import LineString, shape
from shapely.strtree import STRtree

STEP = 0.5           # resample spacing (m)
SMOOTH = 2.0         # heading smoothing (m, gaussian sigma)
HEAD_TOL = np.radians(4.0)    # heading error allowed inside one piece
STRAIGHT_TURN = np.radians(6.0)  # a piece turning less than this is a straight
MIN_PIECE = 2.0      # m
FACE_MIN = 4.0       # shortest lot edge used as a frontage (m)
FACE_ANG = np.radians(8.0)  # kerb within this angle of a lot edge counts as parallel
FACE_OFF = (0.5, 14.0)      # kerb this far from the lot edge (m)
GAP_MAX = 30.0       # longest gap joined (m)
GAP_LAT = 0.6        # ends this close sideways count as one kerb (m)
GAP_ANG = np.radians(4.0)
GAP_COVER = 0.85     # share of the gap that must run beside the same frontage
MAX_RMS = 1.2        # fit worse than this (m) keeps the traced line, only smoothed


# ---------------------------------------------------------------- frontages (lot edges)
class Faces:
    def __init__(self, polys):
        segs = []
        for g in polys:
            for ring in ([g.exterior] + list(g.interiors)) if g.geom_type == "Polygon" else []:
                c = np.asarray(ring.simplify(0.3).coords)
                for a, b in zip(c[:-1], c[1:]):
                    if np.hypot(*(b - a)) >= FACE_MIN:
                        segs.append((a, b))
        self.a = np.array([s[0] for s in segs]).reshape(-1, 2)
        self.b = np.array([s[1] for s in segs]).reshape(-1, 2)
        d = self.b - self.a
        self.len = np.hypot(d[:, 0], d[:, 1])
        self.u = d / np.maximum(self.len, 1e-9)[:, None]
        self.ang = np.arctan2(self.u[:, 1], self.u[:, 0])
        self.tree = STRtree([LineString([a, b]) for a, b in segs]) if segs else None

    def near(self, p, r):
        if self.tree is None:
            return np.zeros(0, int)
        from shapely.geometry import Point
        return np.asarray(self.tree.query(Point(p).buffer(r)), int)

    def frontage(self, p, theta):
        """Best parallel lot edge for a kerb point p with heading theta: (edge index, signed offset) or (None, None)."""
        best, bo, bd = None, None, 1e9
        for i in self.near(p, FACE_OFF[1]):
            da = abs(((self.ang[i] - theta) + np.pi / 2) % np.pi - np.pi / 2)
            if da > FACE_ANG:
                continue
            q = p - self.a[i]; t = q @ self.u[i]
            if t < -1.0 or t > self.len[i] + 1.0:
                continue
            off = self.u[i][0] * q[1] - self.u[i][1] * q[0]
            if FACE_OFF[0] <= abs(off) <= FACE_OFF[1] and abs(off) < bd:
                best, bo, bd = i, off, abs(off)
        return best, bo

    def covers(self, p, theta, side, off, tol=1.5):
        """True if a lot edge parallel to theta runs beside p on the same side at about the same offset."""
        for i in self.near(p, abs(off) + tol + 1):
            da = abs(((self.ang[i] - theta) + np.pi / 2) % np.pi - np.pi / 2)
            if da > FACE_ANG:
                continue
            q = p - self.a[i]; t = q @ self.u[i]
            if t < -0.5 or t > self.len[i] + 0.5:
                continue
            # offset of p from the edge, measured with the kerb's own normal so the sign is comparable
            n = np.array([-np.sin(theta), np.cos(theta)])
            o = -(q @ n)
            if np.sign(o) == side and abs(abs(o) - abs(off)) <= tol:
                return True
        return False


def load_faces(lots_dir):
    """All geometries in a folder of GeoJSON files (lots or road centrelines), each feature once (cells overlap)."""
    out, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(lots_dir, "*.json")) + glob.glob(os.path.join(lots_dir, "*.geojson"))):
        for f in json.load(open(fn)).get("features", []):
            if not f.get("geometry"):
                continue
            pr = f.get("properties") or {}
            key = pr.get("objectid", pr.get("OBJECTID", f.get("id")))
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            g = shape(f["geometry"])
            out += list(g.geoms) if g.geom_type.startswith("Multi") else [g]
    return out


# ---------------------------------------------------------------- one line
def resample(P, step=STEP):
    d = np.hypot(*np.diff(P, axis=0).T); s = np.r_[0, np.cumsum(d)]
    keep = np.r_[True, d > 1e-6]; P, s = P[keep], s[keep]
    if s[-1] < step:
        return P[[0, -1]], np.array([0, s[-1]])
    t = np.linspace(0, s[-1], max(2, int(round(s[-1] / step)) + 1))
    return np.c_[np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], t


def headings(Q, step=STEP):
    sg = SMOOTH / step
    S = np.c_[gaussian_filter1d(Q[:, 0], sg, mode="nearest"), gaussian_filter1d(Q[:, 1], sg, mode="nearest")]
    d = np.gradient(S, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    ds = np.hypot(*np.diff(S, axis=0).T)
    return th, np.r_[0, np.cumsum(ds)]


def split(s, th, tol=HEAD_TOL):
    """Top-down piecewise-linear fit of heading against length; returns breakpoint indices."""
    keep = {0, len(s) - 1}; stack = [(0, len(s) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2 or s[b] - s[a] < 2 * MIN_PIECE:
            continue
        line = th[a] + (th[b] - th[a]) * (s[a:b + 1] - s[a]) / max(s[b] - s[a], 1e-9)
        e = np.abs(th[a:b + 1] - line); k = int(np.argmax(e))
        if e[k] > tol and MIN_PIECE <= s[a + k] - s[a] and s[b] - s[a + k] >= MIN_PIECE:
            keep.add(a + k); stack += [(a, a + k), (a + k, b)]
    return sorted(keep)


def curve(params, nodes, kinds, groups, fixed, s):
    """Positions along s for start point, node headings (via groups) and a length factor."""
    x0, y0, k = params[0], params[1], params[2]
    th_n = np.empty(len(nodes))
    for gi, members in enumerate(groups):
        th_n[members] = fixed[gi] if fixed[gi] is not None else params[3 + gi]
    th = np.interp(s, s[nodes], th_n)
    mid = 0.5 * (th[1:] + th[:-1]); ds = np.diff(s) * k
    x = x0 + np.r_[0, np.cumsum(np.cos(mid) * ds)]
    y = y0 + np.r_[0, np.cumsum(np.sin(mid) * ds)]
    return np.c_[x, y], th_n


def regular(P, faces):
    """Fit one traced line. Returns (dense polyline, info) or (None, info) if no try fits within MAX_RMS.
    Tries: frontage locks on; locks off (the lot edge is not quite parallel to this kerb); finer pieces without locks."""
    best = None
    for fn, lock, tol in ((fit_lf, True, HEAD_TOL), (fit_lf, True, HEAD_TOL / 2), (fit_lf, True, HEAD_TOL * 2),
                          (fit_lf, False, HEAD_TOL / 4), (fit_one, True, HEAD_TOL), (fit_one, False, HEAD_TOL),
                          (fit_one, False, HEAD_TOL / 2)):
        out, info = fn(P, faces, lock, tol)
        if out is not None:
            info["try"] = (lock, tol, fn.__name__)
            return out, info
        best = info if best is None or info.get("rms", 9) < best.get("rms", 9) else best
    return None, best


def regular_split(P, faces, depth=3):
    """regular(), and if no try fits, cut the line in two at its middle and fit each half (up to depth times).
    Returns (polyline or None, info of the whole: ends from the outer pieces)."""
    out, info = regular(P, faces)
    if out is not None or depth == 0:
        return out, info
    P = np.asarray(P, float); Q, _ = resample(P)
    if len(Q) < 40:
        return None, info
    m = len(Q) // 2
    a, ia = regular_split(Q[:m + 1], faces, depth - 1)
    b, ib = regular_split(Q[m:], faces, depth - 1)
    if a is None or b is None:
        return None, info
    ends = [(ia.get("ends") or [None, None])[0], (ib.get("ends") or [None, None])[1]]
    return np.vstack([a, b[1:]]), {"ends": ends, "pieces": [], "split": True}


def segment(P, faces, tol):
    """Resampled points, smoothed heading, length, piece breakpoints, piece kinds and frontage heading per piece."""
    Q, _ = resample(np.asarray(P, float))
    if len(Q) < 5:
        return Q, None
    th, s = headings(Q)
    br = split(s, th, tol)
    kinds = []
    for a, b in zip(br[:-1], br[1:]):
        kinds.append("straight" if abs(th[b] - th[a]) < STRAIGHT_TURN else "arc")
    # frontage per piece (straights, and near-straight arcs beside a straight frontage)
    face = []
    for i, (a, b) in enumerate(zip(br[:-1], br[1:])):
        hits = []
        for j in range(a, b + 1, 4):
            e, o = faces.frontage(Q[j], th[j])
            if e is not None:
                hits.append((e, o))
        cov = len(hits) / max(1, len(range(a, b + 1, 4)))
        f = None
        if hits and cov >= 0.6:
            angs = np.array([faces.ang[e] for e, _ in hits])
            ref = angs[0]; angs = ref + ((angs - ref + np.pi / 2) % np.pi - np.pi / 2)
            if np.ptp(angs) < np.radians(3):
                f = float(np.median(angs))
        if kinds[i] == "arc" and f is not None and abs(th[b] - th[a]) < np.radians(12) and cov >= 0.8:
            kinds[i] = "straight"
        face.append(f if kinds[i] == "straight" else None)
    # merge neighbouring straights that share a heading (same frontage or within 3 degrees)
    nb, nk, nf = [br[0]], [], []
    for i, kd in enumerate(kinds):
        if nk and kd == "straight" and nk[-1] == "straight":
            h1 = nf[-1] if nf[-1] is not None else th[nb[-1]:br[i] + 1].mean()
            h2 = face[i] if face[i] is not None else th[br[i]:br[i + 1] + 1].mean()
            dd = abs(((h1 - h2) + np.pi / 2) % np.pi - np.pi / 2)
            if dd < np.radians(3):
                nb[-1] = br[i + 1]; nf[-1] = nf[-1] if nf[-1] is not None else face[i]
                continue
        nk.append(kd); nf.append(face[i]); nb.append(br[i + 1])
    br, kinds, face = nb, nk, nf
    return Q, (th, s, br, kinds, face)


def _turn(u, v):
    return float(np.arctan2(u[0] * v[1] - u[1] * v[0], u @ v))


def _fillet(c1, u1, c2, u2, pts):
    """Arc tangent to line 1 (point c1, direction u1) and line 2 that best fits pts. Returns (t1, t2, centre, r, turn) or None."""
    d = _turn(u1, u2)
    if abs(d) < np.radians(2) or abs(d) > np.radians(178):
        return None
    A = np.array([u1, -u2]).T
    try:
        a, _ = np.linalg.solve(A, c2 - c1)
    except np.linalg.LinAlgError:
        return None
    pi = c1 + a * u1
    n1 = np.array([-u1[1], u1[0]]) * np.sign(d)  # towards the inside of the turn
    tanh = np.tan(abs(d) / 2)

    def geo(r):
        T = r * tanh
        t1 = pi - u1 * T; ctr = t1 + n1 * r
        return t1, pi + u2 * T, ctr
    if len(pts) >= 3:
        rs = np.geomspace(0.5, 400, 160)
        err = [np.mean((np.hypot(*(pts - geo(r)[2]).T) - r) ** 2) for r in rs]
        r = float(rs[int(np.argmin(err))])
    else:
        r = 3.0
    t1, t2, ctr = geo(r)
    return t1, t2, ctr, r, d


def _arc_pts(t1, ctr, r, d, step=1.0):
    a0 = np.arctan2(*(t1 - ctr)[::-1])
    n = max(2, int(np.ceil(abs(d) * r / step)))
    a = a0 + np.linspace(0, d, n + 1)
    return np.c_[ctr[0] + r * np.cos(a), ctr[1] + r * np.sin(a)]


def _circle(X):
    """Algebraic (Kasa) circle through X: centre, radius."""
    A = np.c_[2 * X, np.ones(len(X))]; y = (X ** 2).sum(1)
    (cx, cy, c), *_ = np.linalg.lstsq(A, y, rcond=None)
    return np.array([cx, cy]), float(np.sqrt(max(c + cx * cx + cy * cy, 0)))


def _meet(A, B, near):
    """Point where primitive A meets B nearest to the trace point near (None if none within 1.5 m)."""
    cand = []
    if A[0] == "S" and B[0] == "S":
        M = np.array([A[2], -B[2]]).T
        if abs(np.linalg.det(M)) > 1e-6:
            t, _ = np.linalg.solve(M, B[1] - A[1]); cand.append(A[1] + t * A[2])
    else:
        if A[0] == "S" or B[0] == "S":
            L_, C_ = (A, B) if A[0] == "S" else (B, A)
            c, u = L_[1], L_[2]; ctr, r = C_[1], C_[2]
            f = c - ctr; bq = f @ u; disc = bq * bq - (f @ f - r * r)
            if disc >= 0:
                cand += [c + u * (-bq - np.sqrt(disc)), c + u * (-bq + np.sqrt(disc))]
        else:
            c1, r1, c2, r2 = A[1], A[2], B[1], B[2]; d = np.hypot(*(c2 - c1))
            if 1e-9 < d <= r1 + r2 and d >= abs(r1 - r2):
                x = (d * d + r1 * r1 - r2 * r2) / (2 * d); h = np.sqrt(max(r1 * r1 - x * x, 0)); e = (c2 - c1) / d
                m = c1 + e * x; cand += [m + h * np.array([-e[1], e[0]]), m - h * np.array([-e[1], e[0]])]
    cand = [q for q in cand if np.hypot(*(q - near)) <= 1.5]
    return min(cand, key=lambda q: np.hypot(*(q - near))) if cand else None


def _onto(Pr, p):
    if Pr[0] == "S":
        return Pr[1] + Pr[2] * ((p - Pr[1]) @ Pr[2])
    v = p - Pr[1]; n = np.hypot(*v)
    return Pr[1] + v / max(n, 1e-9) * Pr[2]


def fit_lf(P, faces, lock, tol):
    """Each piece fitted on its own points (straights by least squares, curves as circles), so every piece keeps its best
    sideways position; straight-to-straight corners get a tangent arc fitted to the corner points, other joins meet where
    the two pieces cross. Returns None when a piece fits badly (fit_one then draws the line)."""
    Q, sg = segment(P, faces, tol)
    if sg is None:
        return Q[[0, -1]], {"pieces": [("straight", None)], "ends": None, "rms": 0.0}
    th, s, br, kinds, face = sg
    # merge neighbouring arcs that bend the same way at a similar rate
    pcs = []
    for i, k in enumerate(kinds):
        a, b = br[i], br[i + 1]; L_ = s[b] - s[a]; kap = (th[b] - th[a]) / max(L_, 1e-9)
        if pcs and k == "arc" and pcs[-1][0] == "arc":
            pa, pb, pk = pcs[-1][1], pcs[-1][2], pcs[-1][3]
            if np.sign(kap) == np.sign(pk) and 0.6 < kap / pk < 1.6:
                kk = (th[b] - th[pa]) / max(s[b] - s[pa], 1e-9)
                pcs[-1] = ("arc", pa, b, kk, None); continue
        pcs.append((k, a, b, kap, face[i]))
    prims = []
    for k, a, b, kap, f in pcs:
        X = Q[a:b + 1]; L_ = s[b] - s[a]; turn = th[b] - th[a]
        if len(X) < 3:
            prims.append(None); continue
        c = X.mean(0); sv = np.linalg.svd(X - c, full_matrices=False); u = sv[2][0]
        if k == "arc" and abs(turn) >= STRAIGHT_TURN:
            ctr, r = _circle(X)
            e_line = sv[1][1] ** 2 / len(X); e_circ = float(np.mean((np.hypot(*(X - ctr).T) - r) ** 2))
            if 0.5 <= r <= 2000 and e_circ < e_line:
                prims.append(("C", ctr, r, float(turn), a, b, None))
                continue
            if r < 0.5:
                return None, {"rms": 9, "why": 1}
            f = None  # a bend too gentle for a circle: a straight, not locked to a frontage
        if u @ (X[-1] - X[0]) < 0:
            u = -u
        if lock and f is not None:
            fu = np.array([np.cos(f), np.sin(f)]); fu = fu if fu @ u > 0 else -fu
            if abs(_turn(u, fu)) < np.radians(3):
                u = fu
        prims.append(("S", c, u, 0, a, b, f))
    # very short pieces (fewer than 3 points) are left to the join of their neighbours
    keep = [p for p in prims if p is not None]
    if not keep:
        return None, {"rms": 9, "why": 2}
    # merge straights that are one line
    m = [keep[0]]
    for p in keep[1:]:
        q = m[-1]
        if p[0] == "S" and q[0] == "S" and abs(_turn(q[2], p[2])) < np.radians(2) and \
                abs(q[2][0] * (p[1] - q[1])[1] - q[2][1] * (p[1] - q[1])[0]) < 0.3:
            X = Q[q[4]:p[5] + 1]; c = X.mean(0)
            m[-1] = ("S", c, q[2], 0, q[4], p[5], q[6] if q[6] is not None else p[6]); continue
        m.append(p)
    pts = [_onto(m[0], Q[m[0][4]] if m[0][4] > 0 else Q[0])]
    if m[0][4] > 0 and m[0][4] * STEP > 1.5:
        return None, {"rms": 9, "why": 3}
    draws = []  # (primitive, start point, end point)
    for A, B in zip(m[:-1], m[1:]):
        near = Q[(A[5] + B[4]) // 2]
        if A[0] == "S" and B[0] == "S":
            f = _fillet(A[1], A[2], B[1], B[2], Q[max(A[5] - 4, 0):B[4] + 5])
            if f is not None and np.hypot(*(f[0] - near)) < 3 * f[3] + 3 and (f[0] - pts[-1]) @ A[2] > -0.5 \
                    and (Q[B[5]] - f[1]) @ B[2] > -0.5:
                t1, t2, ctr, r, d = f
                draws.append((A, pts[-1], t1)); draws.append((("A", ctr, r, d), t1, t2)); pts.append(t2); continue
        q = _meet(A, B, near)
        if q is None:  # no crossing near the join: end A and start B at the join, a short straight between
            q1, q2 = _onto(A, near), _onto(B, near)
            draws.append((A, pts[-1], q1)); draws.append((("J",), q1, q2)); pts.append(q2); continue
        draws.append((A, pts[-1], q)); pts.append(q)
    last = m[-1]
    if (len(Q) - 1 - last[5]) * STEP > 1.5:
        return None, {"rms": 9, "why": 4}
    draws.append((last, pts[-1], _onto(last, Q[-1])))
    out = []
    for pr, p0, p1 in draws:
        if pr[0] in ("S", "J"):
            if pr[0] == "S" and (p1 - p0) @ pr[2] < -0.3:
                return None, {"rms": 9, "why": 5}  # a join behind the piece's start: the pieces overlap
            seg = [p0, p1]
        elif pr[0] == "A":
            seg = list(_arc_pts(p0, pr[1], pr[2], pr[3]))
        else:
            ctr, r, want = pr[1], pr[2], pr[3]
            a0 = np.arctan2(*(p0 - ctr)[::-1]); a1 = np.arctan2(*(p1 - ctr)[::-1])
            d = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
            d = min((d, d + 2 * np.pi, d - 2 * np.pi), key=lambda x: abs(x - want))  # sweep the way the trace turns
            if abs(d - want) > np.radians(45):
                return None, {"rms": 9, "why": 6}
            seg = list(_arc_pts(p0, ctr, r, d))
        out += seg if not out else seg[1:]
    out = np.array(out)
    if len(out) < 2:
        return None, {"rms": 9, "why": 7}
    keepm = np.r_[True, np.hypot(*np.diff(out, axis=0).T) > 0.05]
    out = out[keepm]
    if len(out) < 2:
        return None, {"rms": 9, "why": 8}
    lo_ = LineString(out)
    from shapely import points as _pts
    dev = np.array([lo_.distance(p) for p in _pts(Q)])
    rms = float(np.sqrt(np.mean(dev ** 2)))
    info = {"rms": rms, "p90": float(np.percentile(dev, 90)),
            "pieces": [("straight" if p[0] == "S" else "arc", p[6] if (lock and p[0] == "S") else None) for p in m],
            "s": s, "k": 1.0, "nodes": None, "len_ratio": lo_.length / max(LineString(Q).length, 1e-9)}
    if rms > 0.6 or info["p90"] > 0.9 or not 0.8 < info["len_ratio"] < 1.1:
        return None, info
    f0 = m[0][6] if m[0][0] == "S" else None; f1 = m[-1][6] if m[-1][0] == "S" else None
    info["ends"] = end_info_lf(out, f0, f1, faces)
    return out, info


def end_info_lf(out, f0, f1, faces):
    return end_info(out, ["straight"], [f0 if f0 is not None else None], None, None, faces)[:1] + \
        end_info(out, ["straight"], [f1 if f1 is not None else None], None, None, faces)[1:]


def fit_one(P, faces, lock, tol):
    Q, sg = segment(P, faces, tol)
    if sg is None:
        return Q[[0, -1]], {"pieces": [("straight", None)], "ends": None}
    th, s, br, kinds, face = sg
    nodes = np.array(br)
    # node groups: nodes at both ends of a straight share one heading
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, kd in enumerate(kinds):
        if kd == "straight":
            parent[find(i + 1)] = find(i)
    roots = sorted({find(i) for i in range(len(nodes))})
    gidx = {r: gi for gi, r in enumerate(roots)}
    groups = [[i for i in range(len(nodes)) if find(i) == r] for r in roots]
    fixed = [None] * len(groups)
    for i, kd in enumerate(kinds):
        if kd == "straight" and face[i] is not None:
            gi = gidx[find(i)]
            mean = th[br[i]:br[i + 1] + 1].mean()
            f = face[i] + np.round((mean - face[i]) / np.pi) * np.pi  # edge direction pointing the way the kerb runs
            fixed[gi] = f
    x0 = [Q[0, 0], Q[0, 1], 1.0]
    free = [gi for gi in range(len(groups)) if fixed[gi] is None]
    p0 = np.array(x0 + [float(np.mean(th[nodes[groups[gi]]])) for gi in range(len(groups))])

    # fit, then move each traced point's place along the curve to its nearest point on the fitted curve and fit again
    # (matching by distance along a wobbly trace would pull the fit sideways where the trace is longer than the kerb)
    t = s.copy()
    lo = np.full(len(p0), -np.inf); hi = np.full(len(p0), np.inf); lo[2], hi[2] = 0.9, 1.1
    from scipy.spatial import cKDTree
    for it in range(3):
        def res(p):
            C, _ = curve(p, nodes, kinds, groups, fixed, s)
            return (np.c_[np.interp(t, s, C[:, 0]), np.interp(t, s, C[:, 1])] - Q).ravel()
        r = least_squares(res, p0, bounds=(lo, hi), loss="soft_l1", f_scale=0.3, max_nfev=200)
        p0 = r.x
        C, thn = curve(r.x, nodes, kinds, groups, fixed, s)
        fine = np.linspace(0, s[-1], 4 * len(s))
        Cf = np.c_[np.interp(fine, s, C[:, 0]), np.interp(fine, s, C[:, 1])]
        t = fine[cKDTree(Cf).query(Q)[1]]
    Ct = np.c_[np.interp(t, s, C[:, 0]), np.interp(t, s, C[:, 1])]
    rms = float(np.sqrt(np.mean(np.sum((Ct - Q) ** 2, 1))))
    info = {"rms": rms, "pieces": list(zip(kinds, face)), "nodes": nodes, "th": thn, "s": s, "k": r.x[2]}
    if rms > MAX_RMS:
        return None, info
    # output: straights as two points, arcs every 1 m (densify the heading-integrated curve)
    keep = [0]
    for i, kd in enumerate(kinds):
        a, b = nodes[i], nodes[i + 1]
        if kd == "arc":
            n = max(2, int(np.ceil((s[b] - s[a]) / 1.0)))
            keep += list(np.linspace(a, b, n + 1).round().astype(int)[1:])
        else:
            keep.append(b)
    out = C[sorted(set(keep))]
    info["ends"] = end_info(out, kinds, face, thn, nodes, faces)
    return out, info


def end_info(out, kinds, face, thn, nodes, faces):
    """For gap joining: at each end, the heading and frontage offset if that end is a straight beside a frontage."""
    ends = []
    for which, ki in ((0, 0), (-1, len(kinds) - 1)):
        if kinds[ki] != "straight" or face[ki] is None or len(out) < 2:
            ends.append(None); continue
        p = out[which]; q = out[1] if which == 0 else out[-2]
        h = np.arctan2(*(p - q)[::-1])  # heading pointing out of the line
        e, o = faces.frontage(p - 1.0 * np.array([np.cos(h), np.sin(h)]), h)
        if e is None:
            ends.append(None); continue
        n = np.array([-np.sin(h), np.cos(h)])
        side = -np.sign((p - faces.a[e]) @ n)
        ends.append({"p": p, "h": h, "off": abs(o), "side": side})
    return ends


def chaikin(P, n=2):
    for _ in range(n):
        if len(P) < 3:
            return P
        Q = [P[0]]
        for a, b in zip(P[:-1], P[1:]):
            Q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        Q.append(P[-1]); P = np.array(Q)
    return P


# ---------------------------------------------------------------- gaps
def join_gaps(lines, ends, faces):
    """Join line ends that face each other along the same frontage at the same offset. Returns new lines + made-up lengths."""
    pts = [(li, w, e) for li, ee in enumerate(ends) if ee for w, e in enumerate(ee) if e]
    if not pts:
        return lines, {}
    from scipy.spatial import cKDTree
    P = np.array([e["p"] for _, _, e in pts]); tree = cKDTree(P)
    pairs = []
    for a, b in tree.query_pairs(GAP_MAX):
        (la, wa, ea), (lb, wb, eb) = pts[a], pts[b]
        if la == lb:
            continue
        d = eb["p"] - ea["p"]; g = np.hypot(*d)
        if g < 0.2:
            pairs.append((g, a, b)); continue
        # ends must point at each other along the gap, on the same frontage side and offset
        ua = np.array([np.cos(ea["h"]), np.sin(ea["h"])]); ub = np.array([np.cos(eb["h"]), np.sin(eb["h"])])
        if ua @ (d / g) < np.cos(GAP_ANG) or ub @ (-d / g) < np.cos(GAP_ANG):
            continue
        lat = abs(ua[0] * d[1] - ua[1] * d[0])
        if lat > GAP_LAT or abs(ea["off"] - eb["off"]) > GAP_LAT or ea["side"] != -eb["side"]:
            continue  # facing ends have opposite headings, so the same frontage side has opposite signs
        t = np.arange(0.5, g, 1.0)
        cov = np.mean([faces.covers(ea["p"] + ua * ti, ea["h"], ea["side"], ea["off"]) for ti in t]) if len(t) else 1.0
        if cov >= GAP_COVER:
            pairs.append((g, a, b))
    pairs.sort()
    used = set(); link = {}
    for g, a, b in pairs:
        if a in used or b in used:
            continue
        used |= {a, b}; link[(pts[a][0], pts[a][1])] = (pts[b][0], pts[b][1], g); link[(pts[b][0], pts[b][1])] = (pts[a][0], pts[a][1], g)
    # walk chains
    seen = set(); out = []; filled = {}
    for li in range(len(lines)):
        if li in seen:
            continue
        # find a chain start: an end without a link, else any (loop)
        cur, w = li, 0
        guard = 0
        while (cur, w) in link and guard < 1000:
            nl, nw, _ = link[(cur, w)]
            if nl == li:
                break
            cur, w = nl, 1 - nw; guard += 1
        # now (cur, w) is a free end (or loop); walk from it
        chain = []; gaps = 0.0; c, cw = cur, w
        while c not in seen:
            seen.add(c)
            seg = lines[c] if cw == 0 else lines[c][::-1]
            chain.append(seg)
            nxt = link.get((c, 1 - cw))
            if not nxt or nxt[0] in seen:
                break
            gaps += nxt[2]; c, cw = nxt[0], nxt[1]
        line = np.vstack(chain)
        out.append(line); filled[len(out) - 1] = gaps
    return out, filled


# ---------------------------------------------------------------- run
def run(a):
    from pyproj import Transformer
    inp, lots_dir, outp = a[0], a[1], a[2]
    epsg = int(a[a.index("--epsg") + 1]) if "--epsg" in a else 7856
    to = Transformer.from_crs(4326, epsg, always_xy=True).transform
    back = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    src = json.load(open(inp))
    faces = Faces(load_faces(lots_dir))
    print("frontage edges", len(faces.len), file=sys.stderr, flush=True)
    feats = src["features"]
    lines, ends, props, stats = [], [], [], {"lines": 0, "regular": 0, "kept": 0, "km_in": 0.0}
    for n, f in enumerate(feats):
        P = np.array([to(*c[:2]) for c in f["geometry"]["coordinates"]])
        stats["lines"] += 1; stats["km_in"] += LineString(P).length / 1000 if len(P) > 1 else 0
        out, info = regular_split(P, faces)
        if out is None:
            Q, _ = resample(P); out = chaikin(Q[::4] if len(Q) > 8 else Q, 3); stats["kept"] += 1; info["ends"] = None
        else:
            stats["regular"] += 1
            how = (info.get("try") or (None, None, "split"))[2]
            stats[how] = stats.get(how, 0) + 1
        lines.append(out); ends.append(info["ends"] or [None, None]); props.append(f["properties"])
        if n % 1000 == 0:
            print(n, file=sys.stderr, flush=True)
    joined, filled = join_gaps(lines, ends, faces)
    # each chain keeps the properties of the source line it starts with
    first = {tuple(np.round(l[0], 3)): i for i, l in enumerate(lines)}
    first.update({tuple(np.round(l[-1], 3)): i for i, l in enumerate(lines)})
    items = [{"p": l, "i": first.get(tuple(np.round(l[0], 3)), 0), "filled": filled.get(ci, 0.0)} for ci, l in enumerate(joined)]
    if "--roads" in a:
        import kerbdraft
        print("drafting", len(items), file=sys.stderr, flush=True)
        import kerbaudit
        roads_fh = kerbaudit.load_roads(a[a.index("--roads") + 1])
        # streets only: driveways, vehicle tracks and footpaths (functionhierarchy 8-11) do not break a kerb (Jacky 6 Nov 2026:
        # kerbs were cut 8 m at every driveway and footpath line as if it were a side street)
        world = kerbdraft.World(load_faces(lots_dir), [g for g, fh in roads_fh if fh not in kerbaudit.SKIP_FH])
        world.roads_fh = roads_fh
        dst = {}
        items = kerbdraft.draft(items, world, dst)
        stats["draft"] = dst
    out_feats = []; km_out = 0.0; km_fill = 0.0
    for it in items:
        l = it["p"]
        if len(l) < 2:
            continue
        p = dict(props[it["i"]]); g = LineString(l)
        p["length_m"] = round(g.length, 1); p["shape"] = "regular"
        if it["filled"] > 0:
            p["filled_m"] = round(it["filled"], 1)
            if it["filled"] > 0.9 * g.length:
                p["source"] = "street offset"  # drawn from the road layout, not seen in the photo
        km_out += g.length / 1000; km_fill += it["filled"] / 1000
        out_feats.append({"type": "Feature", "properties": p,
                          "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(x, y)] for x, y in l]}})
    json.dump({"type": "FeatureCollection", "features": out_feats}, open(outp, "w"))
    stats.update({"lines_out": len(out_feats), "km_out": round(km_out, 1), "km_filled": round(km_fill, 1),
                  "km_in": round(stats["km_in"], 1)})
    print("RESULT", json.dumps(stats))


def lots(a, url="https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query",
         fields="objectid"):
    import urllib.request, urllib.parse
    cells, out = json.load(open(a[0])), a[1]; os.makedirs(out, exist_ok=True)
    for x, y in cells:
        fn = f"{out}/{x}_{y}.json"
        if os.path.exists(fn):
            continue
        feats, off = [], 0
        while True:
            q = dict(geometry=f"{x - 60},{y - 60},{x + 1060},{y + 1060}", geometryType="esriGeometryEnvelope", inSR=7856, outSR=7856,
                     spatialRel="esriSpatialRelIntersects", outFields=fields, returnGeometry="true", f="geojson",
                     resultOffset=off, resultRecordCount=2000)
            r = json.load(urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(q),
                                                                          headers={"User-Agent": "openfetch-derive"}), timeout=120))
            fs = r.get("features", []); feats += fs; off += len(fs)
            if not fs:  # the server may page by fewer than asked (100 since Nov 2026): stop only on an empty page
                break
        json.dump({"type": "FeatureCollection", "features": feats}, open(fn, "w"))
        print(x, y, len(feats), file=sys.stderr, flush=True)


if __name__ == "__main__":
    roads = lambda a: lots(a, "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Transport_Theme_multiCRS/FeatureServer/5/query",
                           "OBJECTID,functionhierarchy")
    {"run": run, "lots": lots, "roads": roads}[sys.argv[1]](sys.argv[2:])
