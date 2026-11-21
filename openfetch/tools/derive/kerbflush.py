"""Unmeasurable narrow streets become lanes (kerb scenario 16, flush CBD kerbs, 21 Nov 2026). A CBD laneway or shared zone (Angel
Place, York Lane, Market Row, Phillip Lane) is mapped as a street, so kerblot.py looked for a footpath on it, found none (flush paving,
no kerb step, no kerb inlet) and left every block beside it blank ("no footpath measure"): 55 of the 66 such blocks in the Sydney CBD.
A narrow reserve (under kerblot.LANE_W between lot fronts) with a street centreline along it is handled as a rear lane when nothing
kerblot measures footpaths with finds a kerb in it: no LiDAR kerb trace or earlier kerb inside it, no council kerb inlet inside it,
no measured width for its street name, and the LiDAR ground profiles (kerbpcw.py, where a grid exists) show no kerb on either side.
The blocks either side then join across it, and the ring is cut at its mouths with a kerb return into it (kerbmouth.py, --lane-cut).
So no kerb is ever drawn along it (blank beats a guess), and a street side beside it is no longer lost.
Tried and refused (21 Nov): calling a lane flush from "no kerb step in the LiDAR" alone: narrow terrace streets in Redfern and Surry
Hills read the same (parked cars hide their kerbs), and pits down a lane's middle are too sparse to tell.

    python3 kerbflush.py --selftest
    python3 kerbflush.py --merge plain.json flush.json out.json   (kerblot without and with --flush-lanes: the add-on pass)
"""
import sys
import numpy as np
from shapely.geometry import LineString

STEP = 2.0        # m between profiles along the lane
HALF = 6.0        # m each side of the centreline a profile reaches (narrow reserves are under 7.5 m)
RUN_M = 5.0       # m of kerb trace or earlier kerb inside the reserve: it has a kerb
INSIDE, INSIDE_M = 0.5, 20.0   # a centreline with half its length or 20 m in the reserve becomes a lane (the rest is its mouth)
LAST = {}


def axis(p, streets):
    """Street centreline parts inside the reserve (4 m or longer)."""
    parts = []
    for g in streets:
        if g.intersects(p):
            q = g.intersection(p)
            parts += [r for r in getattr(q, "geoms", [q]) if r.geom_type == "LineString" and r.length >= 4.0]
    return parts


def lidar_kerb(ground, lines, p, prof_step, prof_width, d_min=0.75, step_d=0.1):
    """True when the LiDAR ground shows a kerb lined up along either side at least d_min from the lot front (a footpath kerblot
    could measure, as kerbpcw: 1 m less its 0.25 m profile shift; a step at the lot front is a door sill or wall footing): kerbpcw's per-profile kerb and its
    densest-window rule, walked from the centreline out to each lot front."""
    t = np.arange(0.0, HALF, step_d)
    edge = p.exterior
    pos = {1: [], -1: []}
    for g in lines:
        s = np.arange(STEP / 2, g.length, STEP)
        if not len(s):
            continue
        C = np.asarray([g.interpolate(v).coords[0] for v in s])
        T = np.asarray([g.interpolate(min(v + 0.5, g.length)).coords[0] for v in s]) - np.asarray([g.interpolate(max(v - 0.5, 0)).coords[0] for v in s])
        T /= np.maximum(np.hypot(T[:, 0], T[:, 1]), 1e-9)[:, None]
        N = np.c_[T[:, 1], -T[:, 0]]
        for sg in (1, -1):
            H = ground.height(C[:, 0, None] + sg * N[:, 0, None] * t, C[:, 1, None] + sg * N[:, 1, None] * t)
            for c, n, h in zip(C, N, H):
                ray = LineString([tuple(c), tuple(c + sg * n * HALF)]).intersection(edge)
                f = min((LineString([tuple(c), q.coords[0]]).length for q in getattr(ray, "geoms", [ray]) if q.geom_type == "Point"), default=None)
                k = prof_step(h[::-1], t, 0.0, HALF) if f is not None and np.isfinite(h).sum() >= 1.0 / step_d else None
                d = None if k is None else HALF - k[1]          # kerb distance from the centreline
                pos[sg].append(np.nan if d is None or f - d < d_min or d > f else d)
    return any(prof_width(np.asarray(v)) is not None for v in pos.values() if len(v))


def unmeasured(p, streets, names, pool, street_ok, raw=(), earlier=(), pits=None, ground=None, prof_step=None, prof_width=None):
    """True when nothing finds a kerb in the narrow reserve p (see module doc). streets: centrelines (not lanes); names: the street
    names along p; pool: kerblot's footpath widths per street name. LAST holds the reason."""
    LAST.clear()
    lines = axis(p, streets)
    if not lines:
        LAST["why"] = "no centreline"; return False
    for nm in names:
        tab = pool.get(nm, {})
        if street_ok(tab.get("lidar")) is not None or street_ok(tab.get("drawn")) is not None:
            LAST["why"] = "street measured elsewhere"; return False
    core = p.buffer(-0.3)
    for key, G in (("trace", raw), ("earlier kerb", earlier)):
        if sum(r.intersection(core).length for r in G if r.intersects(p)) >= RUN_M:
            LAST["why"] = key; return False
    if pits is not None:
        P, T = pits
        if any(p.contains(P[int(k)]) for k in T.query(p)):
            LAST["why"] = "kerb inlet"; return False
    if ground is not None and lidar_kerb(ground, lines, p, prof_step, prof_width):
        LAST["why"] = "lidar kerb"; return False
    LAST["why"] = "unmeasured"
    return True


def merge(base, flush):
    """--flush-lanes runs as an ADD-ON pass: every ring of the plain run stays, and a ring of the --flush-lanes run is added only where
    it overlaps none of them (joining blocks across a flush lane can make a plain ring vanish: 7 of 88 in 28 inner-Sydney squares)."""
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree
    poly = lambda f: Polygon(f["geometry"]["coordinates"]).buffer(0)
    B = [poly(f) for f in base]
    T = STRtree(B) if B else None
    ids = {f["properties"]["id"] for f in base}
    add = [f for f in flush if f["properties"]["id"] not in ids and not (T is not None and any(B[int(j)].intersection(poly(f)).area > 1e-10 for j in T.query(poly(f))))]
    return list(base) + add


def selftest():
    import kerbpcw as kpw
    from shapely.geometry import box, Point
    from shapely.strtree import STRtree

    class G:
        def __init__(self, fn): self.fn = fn
        def height(self, X, Y): return self.fn(X, Y)
    ok = lambda v: float(np.median(v)) if v and len(v) >= 3 else None
    lane = box(0, -2.5, 60, 2.5); cl = [LineString([(-5, 0), (65, 0)])]
    inside = lambda X, Y: (np.abs(Y) <= 2.5) & (X >= 0) & (X <= 60)
    flat = G(lambda X, Y: np.where(inside(X, Y), 10.0 - 0.02 * np.abs(Y), np.nan))
    kerbed = G(lambda X, Y: np.where(inside(X, Y), 10.0 + np.where(np.abs(Y) > 1.4, 0.13, 0.0), np.nan))
    args = dict(prof_step=kpw.prof_step, prof_width=kpw.prof_width)
    assert unmeasured(lane, cl, ["A"], {}, ok, ground=flat, **args) is True, LAST
    assert unmeasured(lane, cl, ["A"], {}, ok, ground=None, **args) is True                         # no grid: nothing found a kerb
    assert unmeasured(lane, cl, ["A"], {}, ok, ground=kerbed, **args) is False and LAST["why"] == "lidar kerb"
    assert unmeasured(lane, cl, ["A"], {"A": {"lidar": [1.2, 1.3, 1.25, 1.3]}}, ok, ground=flat, **args) is False   # measured on its street
    assert unmeasured(lane, cl, ["A"], {}, ok, raw=[LineString([(5, 1.5), (40, 1.5)])], ground=flat, **args) is False
    assert unmeasured(lane, cl, ["A"], {}, ok, earlier=[LineString([(5, -1.5), (40, -1.5)])], ground=flat, **args) is False
    pp = [Point(30, 1.6)]
    assert unmeasured(lane, cl, ["A"], {}, ok, pits=(pp, STRtree(pp)), ground=flat, **args) is False
    assert unmeasured(lane, [LineString([(0, 30), (60, 30)])], ["A"], {}, ok, ground=flat, **args) is False   # no centreline in it
    sq = lambda i, x0, y0, s=1e-4: {"type": "Feature", "properties": {"id": i}, "geometry": {"type": "LineString", "coordinates": [[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]}}
    m = merge([sq("a", 0, 0)], [sq("b", 0.00005, 0), sq("c", 0.001, 0), sq("a", 0, 0)])   # b overlaps a: plain ring wins; c is new
    assert [f["properties"]["id"] for f in m] == ["a", "c"], m
    print("kerbflush selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:2] == ["--merge"]:
        import json
        b_, f_, out = sys.argv[2:5]
        F = merge(json.load(open(b_))["features"], json.load(open(f_))["features"])
        json.dump({"type": "FeatureCollection", "features": F}, open(out, "w")); print(len(F)); sys.exit(0)
    print(__doc__)
