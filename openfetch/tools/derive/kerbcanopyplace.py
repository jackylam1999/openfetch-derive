"""Kerbs under tree canopy, placement (scenario 10 round 8, 21 Nov 2026). Places kerb lines on local streets (functionhierarchy
6-7) where the LiDAR ground measures them, from canopy-aware grids (kerbcanopy.py) and the NSW road centrelines (multiCRS only).

Per street, every 2 m and on both sides, walk square to the centreline (the H5 walk): the kerb is the first rise of 6-35 cm
between 1 m medians (skipped as an island when it drops back within 2.5 m), else the first 1 m run whose intensity is not the
cell's own road intensity (median of the cell's centrelines, within 2.5 MAD; open-sky and under-canopy calibrated apart).
Kept only where both sides were found, the carriageway is 5-14 m and the centreline sits within 2.5 m of its middle (the width
pair: odd shapes 14 to 1 on the tune set), then smoothed (7-sample median, 0.75 m), broken at gaps over 2 samples or 1 m jumps,
and pieces under 20 m left blank. State roads, lanes over 14 m and anything unpaired stay blank: the source order puts council
and OSM kerbs there.

Corner zone: a point is left blank where it lies closer to a crossing street's centreline than half that street's width at the
mouth plus a 9 m kerb-return allowance. The width at the mouth is measured by the same walk on the crossing street 3-9 m either
side of its nearest point (median of paired sums, so a flared mouth counts); else official lanecount x 3.5 m; else 7 m. Inside
that zone the kerb curves away round the corner, so a walk square to the street cannot meet it (Woollahra, 21 Nov: a 16 m flared
mouth left a piece 7.5 m off). A segment within 30 deg of parallel at the nearest point is the same street continuing.

Scores (same-side council truth, read through each registry datum entry): 0 odd shapes on Parramatta, Woollahra and a fresh
Canterbury-Bankstown hold-out; under canopy 100 % within 3 m. Lab log: .notes/kerb-top10/canopy/LOG.md.

    python3 kerbcanopyplace.py place <grids_dir> <roads_dir> <cells: 322_6242,...> <out.json>
    python3 kerbcanopyplace.py --selftest
"""
import collections, glob, json, os, sys
import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree

DT, STEP, MAXE, END = 0.25, 2.0, 12.0, 10.0          # m: walk step, sample spacing along the street, longest walk, street ends skipped
SM, DEV, JUMP, MINLEN = 7, 0.75, 1.0, 20.0           # smoothing window (samples), m off the median, m jump that breaks a piece, m shortest piece
RISE = (0.06, 0.35)                                  # m: a kerb rise between 1 m medians
PAIR_W, PAIR_C = (5.0, 14.0), 2.5                    # m: carriageway width range, largest off-centre
LOCAL = (6, 7)                                       # NSW functionhierarchy: local road, access way
RET, LANE, PAR, REACH = 9.0, 3.5, 30.0, 30.0         # m kerb-return allowance, m per official lane, deg parallel, m search


class Roads:
    """NSW Transport Theme multiCRS road centrelines (GeoJSON features, EPSG 7856)."""

    def __init__(self, features):
        self.walk, self.lines, self.ids, self.lanes, cal = [], [], [], {}, []
        uniq = {}
        for f in features:
            p, g = f["properties"], f.get("geometry")
            if not g:
                continue
            oid = p.get("OBJECTID", p.get("objectid")); fh = p.get("functionhierarchy") or 9; on = p.get("roadontype", 1)
            parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
            for c in parts:
                if len(c) > 1:
                    self.lines.append(LineString([q[:2] for q in c])); self.ids.append(oid)
            self.lanes[oid] = p.get("lanecount")
            if g["type"] == "LineString" and on == 1:
                L = LineString([q[:2] for q in g["coordinates"]])
                uniq[(round(L.coords[0][0], 1), round(L.coords[0][1], 1), round(L.length, 1))] = (L, fh, oid)
                if fh <= 7:
                    cal.append(L)
        self.walk = list(uniq.values()); self.cal = cal
        self.tree, self.caltree = STRtree(self.lines), STRtree(cal)

    @classmethod
    def folder(cls, d):
        return cls([f for fn in sorted(glob.glob(os.path.join(d, "*.json"))) for f in json.load(open(fn))["features"]])


class Placer:
    def __init__(self, grids, roads):
        self.G, self.R, self.CAL, self.MW = grids, roads, {}, {}

    def cal(self, i, j):
        """Road intensity of 1 km cell (i, j): median and spread of open-sky / under-canopy ground intensity on its centrelines."""
        if (i, j) not in self.CAL:
            out = {}
            idx = self.R.caltree.query(box(i * 1000, j * 1000, i * 1000 + 1000, j * 1000 + 1000))
            pts = [L.interpolate(s).coords[0] for L in (self.R.cal[k] for k in idx) for s in np.arange(0, L.length, 1.0)]
            pts = np.array([q for q in pts if i * 1000 <= q[0] < i * 1000 + 1000 and j * 1000 <= q[1] < j * 1000 + 1000]).reshape(-1, 2)
            for key in ("io", "iu"):
                v = self.G.sample(key, pts[:, 0], pts[:, 1]) if len(pts) else np.zeros(0)
                v = v[np.isfinite(v) & (v < 255)]
                out[key] = (np.median(v), max(2.0, 1.4826 * np.median(np.abs(v - np.median(v))))) if len(v) >= 100 else None
            self.CAL[(i, j)] = out
        return self.CAL[(i, j)]

    def roadclass(self, X, Y):
        """1 where the ground intensity is the cell's road intensity, 0 where not, nan with no ground point."""
        io, iu = self.G.sample("io", X, Y), self.G.sample("iu", X, Y); out = np.full(X.shape, np.nan)
        for i, j in set(zip((X // 1000).astype(int).ravel(), (Y // 1000).astype(int).ravel())):
            c = self.cal(i, j); k = ((X // 1000) == i) & ((Y // 1000) == j)
            for key, arr in (("iu", iu), ("io", io)):
                if c.get(key) is None:
                    continue
                m, s = c[key]; a = arr[k]; ok = (a < 255) & np.isfinite(a)
                sub = out[k]; sub[ok] = (np.abs(a[ok] - m) <= 2.5 * s).astype(float); out[k] = sub
        return out

    def edge(self, C, u, F):
        """Distance of the kerb from centreline point C along unit u, or None; F counts why."""
        tt = np.arange(0, MAXE + 2, DT); X = C[0] + u[0] * tt; Y = C[1] + u[1] * tt
        rc = self.roadclass(X, Y); H = self.G.sample("h", X, Y)
        if np.isfinite(H).mean() < 0.3:
            F["no ground"] += 1; return None
        n = int(1.0 / DT); e = None
        if np.isfinite(rc).mean() >= 0.3:
            sm = np.array([np.nanmean(rc[max(0, i - n // 2):i + n // 2 + 1]) if np.isfinite(rc[max(0, i - n // 2):i + n // 2 + 1]).any() else np.nan for i in range(len(rc))])
            for i in range(int(1.5 / DT), len(sm) - n):
                if np.all(np.nan_to_num(sm[i:i + n], nan=1.0) < 0.5):
                    e = tt[i]; break
        why = "non-road run"
        for i in range(int(2.0 / DT), len(H) - 6):
            if e is not None and tt[i] >= e:
                break
            b, a = H[i - 4:i], H[i + 2:i + 6]
            if np.isfinite(b).sum() >= 2 and np.isfinite(a).sum() >= 2:
                r = np.nanmedian(a) - np.nanmedian(b)
                if RISE[0] <= r <= RISE[1]:
                    back = H[i + 6:i + 10]
                    if np.isfinite(back).sum() >= 2 and np.nanmedian(back) - np.nanmedian(a) <= -0.06:
                        F["island skipped"] += 1; continue
                    e = tt[i] + 0.25; why = "rise"; break
        if e is None or e < 2.0 or e > MAXE:
            F["no edge found"] += 1; return None
        F["edge: " + why] += 1; return e

    def sides(self, L, S, F):
        out = {}
        for side in (1, -1):
            pts, E = [], []
            for s in S:
                C = np.array(L.interpolate(s).coords[0])
                T = np.array(L.interpolate(min(L.length, s + 1)).coords[0]) - np.array(L.interpolate(max(0, s - 1)).coords[0]); T /= np.hypot(*T)
                u = side * np.array([T[1], -T[0]]); F["samples"] += 1
                e = self.edge(C, u, F); pts.append((C, u)); E.append(np.nan if e is None else e)
            out[side] = (pts, np.array(E))
        return out

    @staticmethod
    def pair(a, b, F):
        """Both sides found, carriageway PAIR_W wide and centred within PAIR_C; the rest blank."""
        w = a + b; bad = ~(np.isfinite(w) & (w >= PAIR_W[0]) & (w <= PAIR_W[1]) & (np.abs(a - b) <= PAIR_C))
        F["side without a plausible partner (carriageway 5-14 m, centred)"] += int((np.isfinite(a) & bad).sum() + (np.isfinite(b) & bad).sum())
        return np.where(bad, np.nan, a), np.where(bad, np.nan, b)

    def pieces(self, oid, side, S, pts, E, F):
        med = np.array([np.nanmedian(E[max(0, i - SM // 2):i + SM // 2 + 1]) if np.isfinite(E[max(0, i - SM // 2):i + SM // 2 + 1]).sum() >= 3 else np.nan for i in range(len(E))])
        keep = np.isfinite(E) & np.isfinite(med) & (np.abs(E - med) <= DEV)
        F["dropped by smoothing (off its neighbours)"] += int((np.isfinite(E) & ~keep).sum())
        out, run = [], []

        def flush(run):
            if len(run) * STEP >= MINLEN:
                P = np.array([pts[i][0] + pts[i][1] * med[i] for i in run])
                can = float(np.mean(self.G.sample("v", P[:, 0], P[:, 1]) > 0.5))
                out.append(dict(street=oid, side=side, s0=float(S[run[0]]), s1=float(S[run[-1]]), canopy=can, pts=P.tolist()))
            elif run:
                F["pieces under 20 m (left blank)"] += 1
        for i in range(len(S)):
            if keep[i] and (not run or (i - run[-1] <= 2 and abs(med[i] - med[run[-1]]) <= JUMP)):
                run.append(i)
            else:
                flush(run); run = [i] if keep[i] else []
        flush(run)
        return out

    def place(self, cells, F):
        """Pieces on the local streets whose middle lies in cells ({(i, j)} km), corner zones taken out."""
        out = []
        for L, fh, oid in self.R.walk:
            x, y = L.interpolate(L.length / 2).coords[0]
            if (int(x // 1000), int(y // 1000)) not in cells:
                continue
            if fh not in LOCAL:
                F["street not local (left blank)"] += 1; continue
            S = np.arange(END, L.length - END + 0.01, STEP)
            if len(S) < int(MINLEN / STEP):
                F["street too short"] += 1; continue
            sd = self.sides(L, S, F)
            a, b = self.pair(sd[1][1], sd[-1][1], F)
            out += self.pieces(oid, 1, S, sd[1][0], a, F) + self.pieces(oid, -1, S, sd[-1][0], b, F)
        out = self.corner(out, F)
        F["pieces"] += len(out); F["km placed"] += round(sum(len(p["pts"]) * STEP for p in out) / 1000, 3)
        return out

    def mouthwidth(self, k, q):
        """Carriageway width of crossing street line k near the point q, measured by the walk 3-9 m either side; None if unmeasured."""
        L = self.R.lines[k]; s0 = L.project(Point(q)); key = (k, round(s0 / 5))
        if key not in self.MW:
            F = collections.Counter(); w = []
            for s in (s0 - 9, s0 - 6, s0 - 3, s0 + 3, s0 + 6, s0 + 9):
                if s < 1 or s > L.length - 1:
                    continue
                C = np.array(L.interpolate(s).coords[0])
                T = np.array(L.interpolate(min(s + 1, L.length)).coords[0]) - np.array(L.interpolate(max(s - 1, 0)).coords[0]); T /= np.hypot(*T)
                a, b = (self.edge(C, sd * np.array([T[1], -T[0]]), F) for sd in (1, -1))
                if a is not None and b is not None:
                    w.append(a + b)
            self.MW[key] = float(np.median(w)) if len(w) >= 2 else None
        return self.MW[key]

    def zone(self, oid, q, F=None):
        """True where q lies in a crossing street's corner zone."""
        R = self.R; P = Point(q)
        own = [R.lines[i] for i in R.tree.query(P.buffer(15)) if R.ids[i] == oid]
        Lo = min(own, key=lambda L: L.distance(P)) if own else None
        for k in R.tree.query(P.buffer(REACH)):
            if R.ids[k] == oid:
                continue
            d = R.lines[k].distance(P)
            if d >= REACH:
                continue
            if Lo is not None and abs(np.dot(hdg(Lo, q), hdg(R.lines[k], q))) > np.cos(np.radians(PAR)):
                continue
            w, src = self.mouthwidth(k, q), "measured at the mouth"
            if w is None:
                w, src = (R.lanes.get(R.ids[k]) or 0) * LANE, "official lanecount"
            if not w:
                w, src = 7.0, "default 7 m"
            if d < w / 2 + RET:
                if F is not None:
                    F["corner zone (width " + src + ")"] += 1
                return True
        return False

    def corner(self, pieces, F):
        out = []
        for p in pieces:
            run = []
            for q in p["pts"] + [None]:
                if q is not None and not self.zone(p["street"], q, F):
                    run.append(q); continue
                if len(run) * STEP >= MINLEN:
                    out.append({**p, "pts": run})
                elif run:
                    F["corner remnant under 20 m (left blank)"] += 1
                run = []
        return out


def hdg(L, q):
    s = L.project(Point(q)); a = np.array(L.interpolate(max(s - 1, 0)).coords[0]); b = np.array(L.interpolate(min(s + 1, L.length)).coords[0])
    d = b - a; return d / max(np.hypot(*d), 1e-9)


class CropGrids:
    """A small grid window (same sample() as kerbcanopy.Grids) for fixtures: arrays h, io, iu, v at RES from (x0, y0) south-west."""

    def __init__(self, x0, y0, res, arrays):
        self.x0, self.y0, self.res, self.a = x0, y0, res, arrays

    def sample(self, key, X, Y):
        X, Y = np.asarray(X, float), np.asarray(Y, float); A = self.a[key]
        c = np.floor((X - self.x0) / self.res).astype(int); r = np.floor((Y - self.y0) / self.res).astype(int)
        ok = (c >= 0) & (r >= 0) & (c < A.shape[1]) & (r < A.shape[0])
        out = np.full(X.shape, np.nan); out[ok] = A[r[ok], c[ok]]; return out


FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kerbcanopyplace-woollahra-mouth.npz")


def _synthetic_grid(width, lift=0.15):
    """A straight east-west street at y = 0: asphalt carriageway |y| < width/2 at 0 m, footpath lifted by a kerb, intensity 20 vs 60."""
    res = 0.5; xs = np.arange(-60, 60, res) + res / 2; ys = np.arange(-30, 30, res) + res / 2
    X, Y = np.meshgrid(xs, ys); road = np.abs(Y) < width / 2
    h = np.where(road, 0.0, lift).astype(np.float32); io = np.where(road, 20, 60).astype(np.float32)
    return CropGrids(-60, -30, res, dict(h=h, io=io, iu=np.full(h.shape, 255.0), v=np.zeros(h.shape)))


def selftest():
    F = collections.Counter()
    feat = lambda oid, c, fh=6, lanes=2: dict(properties=dict(OBJECTID=oid, functionhierarchy=fh, roadontype=1, lanecount=lanes),
                                             geometry=dict(type="LineString", coordinates=c))
    # an 8 m street: both kerbs found 4 m out, paired, placed as two straight pieces
    R = Roads([feat(1, [[-50, 0], [50, 0]])]); pl = Placer(_synthetic_grid(8.0), R)
    pl.cal = lambda i, j: {"io": (20.0, 2.0), "iu": None}
    P = pl.sides(R.walk[0][0], np.arange(END, 100 - END + 0.01, STEP), F)
    a, b = pl.pair(P[1][1], P[-1][1], F)
    assert all(3.0 <= np.nanmedian(x) <= 4.5 for x in (a, b)) and abs(np.nanmedian(a) - np.nanmedian(b)) <= 0.5, (np.nanmedian(a), np.nanmedian(b))
    # a 16 m carriageway is no local street: the width pair leaves it blank (Woollahra c07, a line on the camber of a wide road)
    R16 = Roads([feat(1, [[-50, 0], [50, 0]])]); pl16 = Placer(_synthetic_grid(16.0), R16); pl16.cal = pl.cal
    P16 = pl16.sides(R16.walk[0][0], np.arange(END, 100 - END + 0.01, STEP), F)
    a16, b16 = pl16.pair(P16[1][1], P16[-1][1], F)
    assert not np.isfinite(a16).any() and not np.isfinite(b16).any(), "16 m carriageway must stay blank"
    # the same street continuing past a node is not a crossing street; a street crossing at 90 deg is
    R2 = Roads([feat(1, [[-50, 0], [0, 0]]), feat(2, [[0, 0], [50, 0.5]]), feat(3, [[20, -50], [20, 50]])])
    pl2 = Placer(_synthetic_grid(8.0), R2); pl2.cal = pl.cal
    assert not pl2.zone(1, (-12, 4)), "continuing segment of the same street is no corner"
    assert pl2.zone(2, (12, 4)) and not pl2.zone(2, (45, 4)), "8 m crossing street: zone reaches 4 + 9 m from its centreline"
    # official data fixture: Woollahra flared mouth (NSW LiDAR ground crop, NSW multiCRS centrelines, Woollahra council kerb)
    if os.path.exists(FIXTURE):
        d = np.load(FIXTURE, allow_pickle=False); meta = json.loads(str(d["meta"]))
        G = CropGrids(float(d["x0"]), float(d["y0"]), float(d["res"]), dict(h=d["h"], io=d["io"].astype(float), iu=d["iu"].astype(float), v=d["v"].astype(float)))
        plw = Placer(G, Roads(meta["roads"])); plw.CAL = {tuple(map(int, k.split("_"))): {q: (tuple(v) if v else None) for q, v in c.items()} for k, c in meta["cal"].items()}
        piece = meta["piece"]; truth = [LineString(c) for c in meta["truth"]]
        Fw = collections.Counter(); kept = plw.corner([piece], Fw)
        off = [min(t.distance(Point(q)) for t in truth) for p in kept for q in p["pts"]]
        before = [min(t.distance(Point(q)) for t in truth) for q in piece["pts"]]
        assert max(before) > 5, "fixture: the uncut piece runs 7.5 m off the council kerb at the flared mouth"
        assert kept and max(off) <= 5.0 and np.mean(np.array(off) > 3) <= 0.2, ("corner zone must cut the flared mouth to no odd shape", off)
        lane = Placer(G, Roads(meta["roads"])); lane.CAL = plw.CAL; lane.mouthwidth = lambda k, q: None
        cut = lane.corner([piece], collections.Counter())
        lo = np.array([min(t.distance(Point(q)) for t in truth) for p in cut for q in p["pts"]])
        assert cut and (np.mean(lo > 3) > 0.2 or lo.max() > 5), ("lanecount width alone leaves the flare odd", lo.round(1).tolist())
    else:
        print("fixture missing:", FIXTURE)
    print("kerbcanopyplace selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        selftest()
    elif sys.argv[1:2] == ["place"]:
        import kerbcanopy as kc
        gd, rd, cells, dst = sys.argv[2:6]
        F = collections.Counter(); pl = Placer(kc.Grids(gd), Roads.folder(rd))
        P = pl.place({tuple(map(int, c.split("_"))) for c in cells.split(",")}, F)
        json.dump(dict(funnel=dict(F), pieces=P), open(dst, "w")); print(dict(F))
    else:
        print(__doc__)
