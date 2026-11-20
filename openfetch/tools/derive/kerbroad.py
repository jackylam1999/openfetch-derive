"""Road surface from the LiDAR ground intensity (KN11, 20 Nov 2026, Jacky: "tackle each cause one by one ... root fix and learn
the lesson"). Asphalt returns much less light than concrete, grass or paving (NSW Spatial Services 2019-21 surveys: road centrelines
5-10, footpaths and verges 15-35), so the ground points show where the carriageway really ends. On KN10 every wrong side the close-up
review found sat 1.5-3 m inside this road surface (sides in the roadway) or 4-6 m behind it (back of a grass verge, also under
trees), while good sides sat 1-3 m from it; the kerb step (kerbpcw.py), the cadastre and borrowed widths could not tell them apart.
Used by kerblot.py --road: a footpath width measured to the road edge, and a gate every ring side must pass.

    python3 kerbroad.py grid <out_dir> file.laz [...]     intensity grids <x>_<y>.npz (uint8, 255 = no ground point)
    python3 kerbroad.py --selftest
"""
import os, sys
import numpy as np

RES = 0.5
OFFSET = 0.75     # m: asphalt starts this far past the kerb line (the gutter); 1,222 samples on LiDAR-traced kerbs, 90 % within 1 m
RUN = 2.0         # m of unbroken road surface that counts as the carriageway (a dark patch of shade or wet lawn is shorter)
SMOOTH = 5        # cells (2.5 m): the road mask is the majority of the seen cells round each cell
PAD, CAL_N, HI_DEF = 2.0, 300, 11.0   # road = intensity <= 75th percentile on the cell's own centrelines + 2 (calibrated per survey)
SEEN = 0.4        # share of a side's samples that must see the road edge, or the side is not drawn (canopy, KN10 Apsley St)
AGREE = 2.0       # m: a ring side's kerb line must lie within this of the road edge (a metre or two off is fine; Jacky 14 Nov)
INROAD = 0.5      # share of the 0.5-2.5 m band inside a ring side, over the whole side, that may be road surface
NOSIDE = 255


def grid(paths, out):
    import laspy
    S = {}
    for p in paths:
        with laspy.open(p) as f:
            for ch in f.chunk_iterator(3_000_000):
                k = np.asarray(ch.classification) == 2
                X, Y, I = np.asarray(ch.x)[k], np.asarray(ch.y)[k], np.asarray(ch.intensity)[k].astype(float)
                ci, cj = (X // 1000).astype(int), (Y // 1000).astype(int)
                for a, b in set(zip(ci.tolist(), cj.tolist())):
                    m = (ci == a) & (cj == b)
                    s, c = S.setdefault((a, b), (np.zeros((2000, 2000)), np.zeros((2000, 2000))))
                    i = ((X[m] - a * 1000) / RES).astype(int).clip(0, 1999); j = ((Y[m] - b * 1000) / RES).astype(int).clip(0, 1999)
                    np.add.at(s, (j, i), I[m]); np.add.at(c, (j, i), 1)
    for (a, b), (s, c) in S.items():
        g = np.where(c > 0, np.clip(np.round(s / np.maximum(c, 1)), 0, NOSIDE - 1), NOSIDE).astype(np.uint8)
        np.savez_compressed(os.path.join(out, f"{a}_{b}.npz"), i=g)


class Road:
    """Road-surface mask per 1 km cell; centrelines (shapely LineStrings in MGA56) calibrate each cell's asphalt brightness."""

    def __init__(self, d, centrelines):
        self.d, self.cl, self.mem = d, centrelines, {}

    def _cal(self, g, i, j):
        from shapely.geometry import box
        cell = box(i * 1000, j * 1000, i * 1000 + 1000, j * 1000 + 1000)
        v = []
        for L in self.cl:
            if not L.intersects(cell):
                continue
            for t in np.arange(0, L.length, 1.0):
                x, y = L.interpolate(t).coords[0]
                if i * 1000 <= x < i * 1000 + 1000 and j * 1000 <= y < j * 1000 + 1000:
                    q = g[int((y - j * 1000) / RES), int((x - i * 1000) / RES)]
                    if q != NOSIDE:
                        v.append(float(q))
        return float(np.percentile(v, 75)) + PAD if len(v) >= CAL_N else HI_DEF

    def get(self, i, j):
        if (i, j) not in self.mem:
            fn = os.path.join(self.d, f"{i}_{j}.npz")
            if not os.path.exists(fn):
                self.mem[(i, j)] = None
            else:
                from scipy.ndimage import uniform_filter
                g = np.load(fn)["i"]
                seen = g != NOSIDE
                a = (seen & (g <= self._cal(g, i, j))).astype(np.float32)
                # the road share among the cells that hold a ground point, 2.5 m round each cell: a cell with no ground point (a sparse
                # survey, a parked car) takes its neighbours' answer, so a hole is not a road edge
                ns = uniform_filter(seen.astype(np.float32), size=SMOOTH)
                with np.errstate(all="ignore"):
                    self.mem[(i, j)] = (uniform_filter(a, size=SMOOTH) / ns > 0.5, ns >= 0.2)
        return self.mem[(i, j)]

    def at(self, X, Y):
        """1 road, 0 not road, nan no ground point or no grid."""
        out = np.full(X.shape, np.nan)
        I, J = np.floor(X / 1000).astype(int), np.floor(Y / 1000).astype(int)
        for i, j in set(zip(I.ravel().tolist(), J.ravel().tolist())):
            m = self.get(i, j)
            if m is None:
                continue
            k = (I == i) & (J == j)
            c = ((X[k] - i * 1000) / RES).astype(int).clip(0, 1999); r = ((Y[k] - j * 1000) / RES).astype(int).clip(0, 1999)
            out[k] = np.where(m[1][r, c], m[0][r, c].astype(float), np.nan)
        return out

    def covers(self, P):
        return all(self.get(int(x // 1000), int(y // 1000)) is not None for x, y in P[:: max(1, len(P) // 5)])


def runs(row, t):
    """Distances where a run of RUN m of road surface starts along one profile."""
    road = row > 0.5
    n = int(round(RUN / (t[1] - t[0])))
    return [t[k] for k in range(len(t) - n) if road[k:k + n].all() and (k == 0 or not road[k - 1])]


def profiles(road, P, N, t):
    X = P[:, 0, None] + N[:, 0, None] * t[None]; Y = P[:, 1, None] + N[:, 1, None] * t[None]
    return road.at(X, Y)


def side_width(road, P, N, reach, dmin=1.0, dmax=7.0):
    """Footpath width of one street side from the lot front samples P (outward normals N): the first carriageway run out from the
    lot front, less the gutter. None when under SEEN of the samples see it or they spread over more than 1.2 m (middle half)."""
    if len(P) < 4 or not road.covers(P):
        return None
    t = np.arange(0.25, min(reach, dmax + OFFSET + RUN) + 0.01, 0.25)
    M = profiles(road, P, N, t)
    e = np.asarray([(r[0] if (r := runs(row, t)) else np.nan) for row in M])
    ok = e[np.isfinite(e)]
    if len(ok) < max(3, SEEN * len(P)):
        return None
    q1, q2, q3 = np.percentile(ok, [25, 50, 75])
    if q3 - q1 > 1.2:
        return None
    d = float(q2) - OFFSET
    return d if dmin <= d <= dmax else None


def judge_ring(road, ring_xy, minlen=15.0):
    """Reason a closed ring (MGA56 coords, counter- or clockwise) fails the road-surface gate, or None. Every side of 15 m or more
    must see the road edge on SEEN of its samples, lie within AGREE of it, and keep road surface out of the band just inside it."""
    P = np.asarray(ring_xy, float)
    A = 0.5 * np.sum(P[:-1, 0] * P[1:, 1] - P[1:, 0] * P[:-1, 1])
    t = np.arange(-6.0, 10.01, 0.25)
    for a, b in zip(P[:-1], P[1:]):
        L = float(np.hypot(*(b - a)))
        if L < minlen:
            continue
        dd = (b - a) / L
        n = np.array([dd[1], -dd[0]]) if A > 0 else np.array([-dd[1], dd[0]])
        S = np.arange(3, L - 3, 1.0)
        Q = a + dd * S[:, None]
        M = profiles(road, Q, np.repeat(n[None], len(Q), 0), t)
        if np.isnan(M).all():
            return "no road surface data"
        e = np.asarray([(min(r, key=abs) if (r := runs(row, t)) else np.nan) for row in M])
        if np.nan_to_num(M[:, (t >= -2.5) & (t <= -0.5)], nan=0.0).mean() > INROAD:   # over the whole side: asphalt footpaths and
            # driveways make single samples dark (a per-sample share refused 54 of 62 KN12 rings, 20 Nov 2026)
            return "side in the roadway"
        if np.isfinite(e).mean() < SEEN:
            return "road edge not seen"
        if abs(float(np.nanmedian(e)) - OFFSET) > AGREE:
            return "side in the roadway" if np.nanmedian(e) < OFFSET else "side behind the verge"
    return None


def side_report(road, ring_xy, minlen=15.0):
    """Per-side numbers behind judge_ring, for close-up crops: [{from, to, len_m, edge_m (median asphalt start from the kerb line, m),
    seen (share of samples that see the road edge), inroad (share of the 0.5-2.5 m inside band that is road)}]."""
    P = np.asarray(ring_xy, float)
    A = 0.5 * np.sum(P[:-1, 0] * P[1:, 1] - P[1:, 0] * P[:-1, 1])
    t = np.arange(-6.0, 10.01, 0.25)
    out = []
    for a, b in zip(P[:-1], P[1:]):
        L = float(np.hypot(*(b - a)))
        if L < minlen:
            continue
        dd = (b - a) / L
        n = np.array([dd[1], -dd[0]]) if A > 0 else np.array([-dd[1], dd[0]])
        S = np.arange(3, L - 3, 1.0)
        Q = a + dd * S[:, None]
        M = profiles(road, Q, np.repeat(n[None], len(Q), 0), t)
        r = {"from": [round(float(a[0]), 1), round(float(a[1]), 1)], "to": [round(float(b[0]), 1), round(float(b[1]), 1)], "len_m": round(L, 1)}
        if np.isnan(M).all():
            r.update(edge_m=None, seen=0.0, inroad=None)
        else:
            e = np.asarray([(min(q, key=abs) if (q := runs(row, t)) else np.nan) for row in M])
            band = np.nan_to_num(M[:, (t >= -2.5) & (t <= -0.5)], nan=0.0).mean()
            r.update(edge_m=None if np.isnan(e).all() else round(float(np.nanmedian(e)), 2), seen=round(float(np.isfinite(e).mean()), 2), inroad=round(float(band), 2))
        out.append(r)
    return out


WIN = 20.0        # m: an open line is judged in windows this long (a ring side is judged whole; a line passes many streets)
BAD_M = 40.0      # m of failed windows that refuse a line (KN13); shorter stretches are corners, driveways and gaps in the survey


def line_report(road, line_xy, centres, win=WIN, far=40.0):
    """Per-window numbers for an open line (MGA56 coords): the road side of every sample is the side the nearest street centreline
    lies on (centres: shapely LineStrings, lanes included, footpaths and tracks not). Window = {s0, len_m, edge_m, seen, inroad, why}
    with why one of None, 'side in the roadway', 'side behind the verge', 'road edge not seen'; windows with no street within `far`
    m are left out."""
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    L = LineString(np.asarray(line_xy, float))
    n = int(L.length)
    if n < 6:
        return []
    S = np.arange(0.5, L.length - 0.4, 1.0)
    Q = np.array([L.interpolate(s).coords[0] for s in S])
    A = np.array([L.interpolate(max(0.0, s - 2.5)).coords[0] for s in S]); B = np.array([L.interpolate(min(L.length, s + 2.5)).coords[0] for s in S])
    D = B - A; D /= np.maximum(np.hypot(D[:, 0], D[:, 1]), 1e-6)[:, None]
    N = np.c_[D[:, 1], -D[:, 0]]
    tree = STRtree(centres)
    side = np.zeros(len(S)); dist = np.full(len(S), np.inf)
    for k, q in enumerate(Q):
        j = tree.nearest(Point(q))
        if j is None:
            continue
        c = centres[int(j)]
        dist[k] = c.distance(Point(q))
        if dist[k] > far:
            continue
        cp = np.array(c.interpolate(c.project(Point(q))).coords[0])
        side[k] = 1.0 if np.dot(cp - q, N[k]) >= 0 else -1.0
    t = np.arange(-6.0, 10.01, 0.25)
    out = []
    for w0 in np.arange(0.0, L.length - win / 2, win):
        m = (S >= w0) & (S < w0 + win) & (side != 0)
        if m.sum() < 8:
            continue
        P, NN = Q[m], N[m] * side[m, None]
        M = profiles(road, P, NN, t)
        r = {"s0": round(float(w0), 1), "len_m": round(float(min(win, L.length - w0)), 1), "at": [round(float(P[len(P) // 2][0]), 1), round(float(P[len(P) // 2][1]), 1)]}
        if np.isnan(M).all():
            r.update(edge_m=None, seen=0.0, inroad=None, why="no road surface data")
            out.append(r); continue
        e = np.asarray([(min(q, key=abs) if (q := runs(row, t)) else np.nan) for row in M])
        band = float(np.nan_to_num(M[:, (t >= -2.5) & (t <= -0.5)], nan=0.0).mean())
        seen = float(np.isfinite(e).mean())
        med = None if np.isnan(e).all() else float(np.nanmedian(e))
        why = None
        if band > INROAD:
            why = "side in the roadway"
        elif seen < SEEN:
            why = "road edge not seen"
        elif abs(med - OFFSET) > AGREE:
            why = "side in the roadway" if med < OFFSET else "side behind the verge"
        r.update(edge_m=None if med is None else round(med, 2), seen=round(seen, 2), inroad=round(band, 2), why=why)
        out.append(r)
    return out


def judge_line(road, line_xy, centres, bad_m=BAD_M, **kw):
    """Reason an open line fails the road-surface gate, or None: windows that fail add up to bad_m m or more (the worst reason wins:
    roadway, then behind the verge, then not seen). A line with no road surface data at all is not judged (None)."""
    rep = line_report(road, line_xy, centres, **kw)
    if not rep or all(r["why"] == "no road surface data" for r in rep):
        return None
    tot = {}
    for r in rep:
        if r["why"] and r["why"] != "no road surface data":
            tot[r["why"]] = tot.get(r["why"], 0.0) + r["len_m"]
    if sum(tot.values()) < bad_m:
        return None
    for w in ("side in the roadway", "side behind the verge", "road edge not seen"):
        if tot.get(w):
            return w


class _Fake:
    """Test road: road surface everywhere outside a 100 x 60 m block of land (x 0-100, y 0-60), except under holes (x ranges)."""

    def __init__(self, holes=()):
        self.holes = holes

    def at(self, X, Y):
        r = (~((X > 0) & (X < 100) & (Y > 0) & (Y < 60))).astype(float)
        for x0, x1 in self.holes:
            r[(X >= x0) & (X < x1) & (Y > 55)] = np.nan
        return r

    def covers(self, P):
        return True


def selftest():
    ring = lambda d, top=None: [(-d, -d), (100 + d, -d), (100 + d, 60 + (d if top is None else top)), (-d, 60 + (d if top is None else top)), (-d, -d)]
    road = _Fake()
    assert judge_ring(road, ring(0.0)) is None                            # kerb 0.75 m inside the asphalt edge: on the kerb
    assert judge_ring(road, ring(-1.0)) is None                           # a little off is fine
    assert judge_ring(road, ring(0.0, top=-5.0)) == "side behind the verge"   # north side back of a 4 m grass verge
    assert judge_ring(road, ring(0.0, top=2.5)) == "side in the roadway"      # north side 2.5 m into the carriageway
    assert judge_ring(road, ring(0.0, top=3.5)) == "side in the roadway"
    assert judge_ring(_Fake([(-20, 120)]), ring(0.0)) == "road edge not seen"   # canopy over the whole north side
    P = np.c_[np.arange(10, 90, 2.0), np.full(40, 56.0)]; N = np.tile([0.0, 1.0], (40, 1))
    w = side_width(road, P, N, 12.0)
    assert w is not None and abs(w - (4.0 - OFFSET)) < 0.3, w             # lot front 4 m from the asphalt: 3.25 m footpath
    assert side_width(_Fake([(0, 80)]), P, N, 12.0) is None               # mostly unseen: no width
    from shapely.geometry import LineString
    cen = [LineString([(-60, -10), (160, -10)])]   # a street south of the land block; the road side of a line is the south
    ln = lambda y: [(10.0, y), (90.0, y)]
    assert judge_line(_Fake(), ln(0.0), cen) is None                       # kerb on the land edge, asphalt 0 m out
    assert judge_line(_Fake(), ln(1.0), cen) is None                       # a metre or two off is fine
    assert judge_line(_Fake(), ln(-2.5), cen) == "side in the roadway"      # 2.5 m into the carriageway
    assert judge_line(_Fake(), ln(3.5), cen) == "side behind the verge"     # 3.5 m back from the asphalt edge
    assert judge_line(_Fake(), [(10.0, -2.5), (40.0, -2.5)], cen) is None   # 30 m of odd is under bad_m (corners, gaps)
    assert judge_line(_Fake(), ln(-2.5), [LineString([(-60, 200), (160, 200)])]) is None   # no street within 40 m: nothing to judge
    rep = line_report(_Fake(), ln(-2.5), cen)
    assert len(rep) == 4 and all(w["why"] == "side in the roadway" for w in rep), rep
    print("kerbroad selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    if a and a[0] == "grid":
        os.makedirs(a[1], exist_ok=True)
        grid(a[2:], a[1])
