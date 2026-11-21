#!/usr/bin/env python3
"""Cul-de-sac kerbs as their own line (kerb scenario 9, 21 Nov 2026). kerblot.py rings a whole block and keeps it only when every
side passes, so a dead-end street inside a block that fails on another side (bush, rail, a lane, no measure) stays blank: 42 km of
the top-10 street-side gap sits on 327 dead-end streets (measure nsw-2026-11-20-c). KN8 (derive c52cf1f) let such blocks through the
inlet gate and won 2 blocks, because the other gates still refused them. Here the cul-de-sac is drawn on its own, from the land:
  1. stem = the named street (fh 2-6, on the ground) from its dead end back to the first junction, at most STEM_MAX m.
  2. reserve = the land between lots (cadastre) within ZONE m of the stem, strips under LANE_W wide (walkways) taken off, the piece
     holding the stem's end. It must close round the end inside the zone (an open walkway or park beyond is refused).
  3. footpath width d = the LiDAR kerb step (kerbpcw.side_width) on the reserve's front, in runs of RUN samples; at least two runs
     must be measured and agree within AGREE m. No measure, no kerb (never guessed).
  4. kerb = the reserve's edge pushed in by d; only the part nearer the stem than any other centreline is kept, and each end then
     runs on round the corner return until it meets an existing kerb (JOIN m) or the corner straightens onto the through street.
  5. parts already kerbed (within JOIN m of an existing kerb) are cut out; pieces under MIN_LEN m are dropped; every piece keeps
     CL_CLEAR m from every centreline except the stem's last TIP m (a centreline drawn to the bulb's middle or edge).

    python3 kerbcds.py roads_dir lots_dir grids_dir kerbs.geojson[.gz][,more] out.geojson [--why why.json] [--cells cells.txt]
    python3 kerbcds.py --selftest
roads_dir / lots_dir: <x>_<y>.json in MGA56 (EPSG 7856) as fetchin2.py writes them; kerbs in lon/lat; out in lon/lat.
"""
import collections, glob, gzip, itertools, json, math, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box, shape
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree
import kerbpcw as kpw

STEM_MAX = 400.0     # m: a dead end further than this from its junction is a long street, not a cul-de-sac
ZONE = 30.0          # m either side of the stem searched for its reserve
LANE_W = 7.5         # m: reserve strips narrower than this are walkways or lanes (kerblot.LANE_W)
CLOSE = 0.4          # m: lot gaps under 0.8 m are drafting slivers (kerblot.CLOSE)
W_MIN, W_MAX = 8.0, 30.0     # m: believable cul-de-sac reserve widths along the stem
SAMPLE = 2.0         # m between samples round the reserve edge
D_MIN, D_MAX = 1.0, 7.0      # m, believable footpath widths (kerblot.D_MIN, D_MAX)
RUN = 15             # samples (30 m) per run measured on its own
AGREE = 1.0          # m: neighbouring runs agree within this (a run off both is a stray)
RUN_SHARE = 0.6      # share of runs that must be measured
STRAY = 6.0          # m of other front facing the stem allowed apart from the cul-de-sac's own run
MOUTH = 25.0         # m: each end of the cul-de-sac's front lies this near its junction
WIN = 6              # samples either side read together for one width (26 m)
TRIM = 0.6           # m: a profile's kerb further than this from the fitted line is a driveway, tree pit or car
FIT_MIN = 4          # readings that agree, at least, for a width
SEEN_MIN = float(os.environ.get('CDS_SEEN', 0.4))   # share of the cul-de-sac's samples with a width
GAP_MAX = int(os.environ.get('CDS_GAP', 10))       # samples (20 m) without a width bridged along the same kerb; a longer gap is not guessed
JUMP = 0.5           # m the width may change between two samples 2 m apart
CW_MIN = 2.5         # m: half a carriageway at least between the two kerbs (kerblot.CW_MIN)
JOIN = 1.5           # m: an end this near an existing kerb meets it; a kerb this near an existing one is already there
RETURN_MAX = 15.0    # m an end may run on round the corner return
STRAIGHT = 4.0       # degrees: the corner has straightened when the line turns less than this over 3 m
MIN_LEN = 20.0       # m: shorter pieces are not drawn
CL_CLEAR = 2.0       # m kept from every centreline
TIP = 8.0            # m: the stem's last metres may come nearer (drawn to the bulb's middle or its edge)
STREET_FH = range(2, 7)
ROAD_FH = range(1, 8)


def key(c):
    return (round(c[0], 1), round(c[1], 1))


def load_roads(d):
    seen, out = set(), []
    for fn in sorted(glob.glob(os.path.join(d, "*.json"))):
        for f in json.load(open(fn))["features"]:
            p = f["properties"]; oid = p.get("objectid", p.get("OBJECTID"))
            if oid in seen or not f.get("geometry"):
                continue
            seen.add(oid)
            fh, st, on = p.get("functionhierarchy"), p.get("operationalstatus"), p.get("roadontype")
            if fh is None or int(fh) not in ROAD_FH or (st is not None and int(st) not in (1, 2)):
                continue
            g = shape(f["geometry"])
            for l in getattr(g, "geoms", [g]):
                out.append({"g": l, "fh": int(fh), "on": on, "name": p.get("roadnamebase"), "nid": p.get("roadnameoid")})
    return out


def stems(roads):
    """Dead-end streets: (tip point, stem line, junction point, road index list). The tip end has no other road; the walk back
    stops at the first node with three or more roads."""
    deg, adj = collections.Counter(), collections.defaultdict(list)
    for i, r in enumerate(roads):
        for c in (r["g"].coords[0], r["g"].coords[-1]):
            deg[key(c)] += 1; adj[key(c)].append(i)
    out = []
    for n, k in deg.items():
        r = roads[adj[n][0]]
        if k != 1 or r["fh"] not in STREET_FH or r["on"] not in (None, 1):
            continue
        cur, seg, parts, L = n, adj[n][0], [], 0.0
        while True:
            g = roads[seg]["g"]; parts.append(seg); L += g.length
            a, b = key(g.coords[0]), key(g.coords[-1]); nxt = b if a == cur else a
            if deg[nxt] != 2 or L > STEM_MAX:
                break
            seg = [j for j in adj[nxt] if j != seg][0]; cur = nxt
        if L <= STEM_MAX and deg[nxt] >= 3:
            u = unary_union([roads[j]["g"] for j in parts])
            line = u if u.geom_type == "LineString" else linemerge(u)
            if line.geom_type == "LineString":
                out.append({"tip": Point(n), "stem": line, "junction": Point(nxt), "parts": set(parts), "name": r["name"], "nid": r["nid"]})
    return out


def reserve(st, lots_t, lots):
    """The cul-de-sac's road reserve (polygon) or (None, why)."""
    zone = st["stem"].buffer(ZONE)
    near = [lots[int(k)] for k in lots_t.query(zone)]
    land = unary_union([g.buffer(CLOSE) for g in near]).buffer(-CLOSE) if near else Polygon()
    raw = zone.difference(land)
    res = raw.buffer(-LANE_W / 2, join_style="mitre").buffer(LANE_W / 2, join_style="mitre")
    res = res.union(raw.intersection(st["stem"].buffer(LANE_W / 2, cap_style="flat"))).intersection(zone)   # a narrow street keeps its own strip
    parts = [g for g in getattr(res, "geoms", [res]) if g.geom_type == "Polygon" and not g.is_empty]
    if not parts:
        return None, "no reserve round the street end"
    tip = st["tip"]
    p = min(parts, key=lambda g: g.distance(tip))
    if p.distance(tip) > 3.0:
        return None, "street end not in a reserve"
    if _open_past_end(p, st):
        return None, "reserve runs on past the street end"
    return p, None


def _open_past_end(p, st):
    """True when the reserve still reaches the zone's edge beyond the street's end (a walkway, park or road carrying on)."""
    s = st["stem"]; tip = st["tip"]
    end = s.coords[0] if Point(s.coords[0]).distance(tip) < 0.5 else s.coords[-1]
    prev = s.interpolate(s.project(Point(end)) + (-3 if s.project(Point(end)) > 1 else 3))
    v = np.array(end) - np.array(prev.coords[0]); v /= max(np.linalg.norm(v), 1e-9)
    far = Point(np.array(end) + v * (ZONE - 1))
    cap = far.buffer(ZONE * 0.6).intersection(s.buffer(ZONE).exterior.buffer(1.0))
    return p.intersects(cap)


def widths(p, st):
    """Reserve width across the stem every 10 m (m), from rays both ways."""
    s, out = st["stem"], []
    for t in np.arange(10.0, s.length - 10.0, 10.0):
        a, b = s.interpolate(t - 1), s.interpolate(t + 1)
        v = np.array(b.coords[0]) - np.array(a.coords[0]); v /= max(np.linalg.norm(v), 1e-9); n = np.array([-v[1], v[0]])
        c = np.array(s.interpolate(t).coords[0])
        ray = LineString([c - n * ZONE, c + n * ZONE]).intersection(p)
        segs = [g for g in getattr(ray, "geoms", [ray]) if g.geom_type == "LineString" and g.distance(Point(c)) < 0.5]
        if segs:
            out.append(segs[0].length)
    return out


def front(p, st, cl_t, cls, zone):
    """Samples every SAMPLE m round the reserve edge (in ring order): points P, unit normals N square to the lot front and into
    the reserve (a profile aimed at the centreline's end crosses a bulb's kerb at a slant and smears its step), reach R (m to the
    nearest centreline), own (that centreline is the stem) and ok (a lot front, not the search zone's cut edge)."""
    ring = shapely.geometry.polygon.orient(p).exterior   # anticlockwise: the reserve lies to the left of the ring
    P, N, R, own, ok = [], [], [], [], []
    for t in np.arange(0.0, ring.length, SAMPLE):
        q = ring.interpolate(t)
        a, b = np.array(ring.interpolate((t - 2) % ring.length).coords[0]), np.array(ring.interpolate((t + 2) % ring.length).coords[0])
        v = b - a; nv = np.linalg.norm(v)
        k = int(cl_t.query_nearest(q)[0]); r = cls[k].distance(q)
        P.append(q.coords[0]); N.append(np.array([-v[1], v[0]]) / nv if nv > 1e-6 else np.array([0.0, 0.0])); R.append(r)
        own.append(k == 0); ok.append(nv > 1e-6 and zone.exterior.distance(q) > 1.0)   # a centreline drawn to the lot line still has its kerb
    return np.array(P), np.array(N), np.array(R), np.array(own), np.array(ok)


def positions(ground, P, N, R, ok):
    """Kerb distance from the lot front found in each LiDAR ground profile on its own (kerbpcw.prof_step), nan where none."""
    pos = np.full(len(P), np.nan)
    if not ok.any() or not ground.covers(P[ok]):
        return pos
    t = np.arange(0.0, D_MAX + 1.5, kpw.STEP_D)
    with np.errstate(all="ignore"):
        H = kpw.profiles(ground, P[ok], N[ok], t)
        pos[ok] = kpw.prof_positions(np.nanmedian(H, axis=0), t, D_MIN - kpw.P_SHIFT, D_MAX - kpw.P_SHIFT) + kpw.P_SHIFT
    pos[ok & (pos > R - CW_MIN)] = np.nan
    return pos


def follow(pos, idx, n):
    """Footpath width at each cul-de-sac sample (nan where not seen): a straight line fitted to the profiles' kerbs within WIN
    samples either side, readings more than TRIM m off the line dropped and the line fitted again. A bulb's kerb is seldom
    concentric with its lot fronts, so the width changes smoothly round it; a driveway, tree pit or parked car is one stray
    reading and falls out. Needs FIT_MIN readings that agree, and half of the readings found in the window."""
    out = np.full(len(idx), np.nan)
    for k, i in enumerate(idx):
        j = np.arange(-WIN, WIN + 1); v = pos[[(i + x) % n for x in j]]; m = np.isfinite(v)
        if m.sum() < FIT_MIN:
            continue
        x, y = j[m].astype(float), v[m]
        keep = np.ones(len(x), bool)
        for _ in range(3):
            if keep.sum() < FIT_MIN:
                break
            c = np.polyfit(x[keep], y[keep], 1)
            keep = np.abs(y - np.polyval(c, x)) <= TRIM
        if keep.sum() >= FIT_MIN and keep.sum() >= 0.5 * len(x):
            c = np.polyfit(x[keep], y[keep], 1); out[k] = float(np.polyval(c, 0.0))
    return out


def _nearer_other(q, dq, others_t, others):
    return any(others[int(k)].distance(q) < dq - 0.5 for k in others_t.query(q.buffer(dq)))


def keep_runs(flags):
    """Index runs (start, end inclusive) of True in a cyclic list; a run through the start is joined."""
    n = len(flags); runs = []
    if all(flags):
        return [(0, n - 1)]
    s = next(k for k in range(n) if not flags[k]); k = 0
    while k < n:
        if flags[(s + k) % n]:
            b = k
            while b + 1 < n and flags[(s + b + 1) % n]:
                b += 1
            runs.append(((s + k) % n, (s + b) % n)); k = b + 1
        else:
            k += 1
    return runs


def turn(V, i, j, k):
    a, b = V[j] - V[i], V[k] - V[j]
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / (na * nb)))))


def extend(idx, n, K, seen, near_kerb):
    """The cul-de-sac's samples idx carried on round each corner return (ring order, n samples): until the kerb meets an existing
    one (join) or straightens onto the through street (return), at most RETURN_MAX m, never past an unseen sample."""
    ends = []
    for side in (0, 1):
        kind, cur = "return", idx[0] if side == 0 else idx[-1]
        for s in range(1, int(RETURN_MAX / SAMPLE) + 1):
            nxt = (cur - 1) % n if side == 0 else (cur + 1) % n
            if nxt in idx or not seen[nxt]:
                break
            cur = nxt
            idx.insert(0, cur) if side == 0 else idx.append(cur)
            if near_kerb(K[cur]):
                kind = "join"; break
            w = idx[:4] if side == 0 else idx[-4:]
            if s >= 2 and len(w) == 4 and turn(K, w[0], w[1], w[3]) < STRAIGHT:
                break
        ends.append(kind)
    return idx, ends


def clear_of(V, st, others_t, others):
    """First vertex index nearer than CL_CLEAR to a centreline (the stem's last TIP m excepted), or None."""
    s = st["stem"]; tip_t = s.project(st["tip"])
    body = shapely.ops.substring(s, TIP, s.length) if tip_t < 1 else shapely.ops.substring(s, 0, s.length - TIP)
    for i, v in enumerate(V):
        q = Point(v)
        if body.distance(q) < CL_CLEAR or any(others[int(k)].distance(q) < CL_CLEAR for k in others_t.query(q.buffer(CL_CLEAR))):
            return i
    return None


def kerb_pieces(K, near):
    """Split the kerb where it already lies on an existing kerb; keep pieces of MIN_LEN m or more."""
    out, cur = [], []
    for k, v in enumerate(K):
        if near(v) and 0 < k < len(K) - 1:
            if cur:
                cur.append(v); out.append(cur)
            cur = [v]
            continue
        cur.append(v)
    out.append(cur)
    return [q for q in out if len(q) > 1 and LineString(q).length >= MIN_LEN]


def widths_along(ground, pos, P, N, R, idx, n):
    """Footpath width at each cul-de-sac sample: followed profile by profile (follow) where the kerb shows on most of it, else one
    width for the whole cul-de-sac where runs of RUN samples are each measured (kerbpcw.side_width) and agree within AGREE m.
    Returns (widths, how, detail) or (None, why, detail)."""
    dd = follow(pos, idx, n); seen_i = np.isfinite(dd); det = {"seen": round(float(seen_i.mean()), 2)}
    gap = max((len(list(g)) for v, g in itertools.groupby(seen_i) if not v), default=0)
    if seen_i.mean() >= SEEN_MIN and gap <= GAP_MAX:
        dd = np.interp(np.arange(len(idx)), np.flatnonzero(seen_i), dd[seen_i])
        if np.max(np.abs(np.diff(dd))) <= JUMP:
            return dd, "followed", det
    I = np.array(idx); cen, got = [], []
    for k in range(0, len(I), RUN):
        j = I[k:k + RUN]
        v = kpw.side_width(ground, P[j], N[j], float(np.median(R[j]))) if len(j) >= 4 else None
        cen.append(k + (len(j) - 1) / 2); got.append(v)
    det["runs"] = [None if v is None else round(v, 2) for v in got]
    return run_widths(cen, got, len(idx), det)


def run_widths(cen, got, m, det):
    """Widths at m samples from runs measured on their own (centres cen, widths got, None where not measured): a run that
    disagrees by more than AGREE m with both neighbours while they agree is a driveway or a parked car and takes their mean; one
    unmeasured run between two measured ones is bridged; widths change smoothly between run centres (the two sides of a
    cul-de-sac often keep different verges)."""
    v = [None if x is None else float(x) for x in got]
    if sum(x is not None for x in v) < max(2, RUN_SHARE * len(v)):
        return None, "kerb not seen in the LiDAR along most of the cul-de-sac", det
    if any(v[k] is None and (k == 0 or k == len(v) - 1 or v[k - 1] is None or v[k + 1] is None) for k in range(len(v))):
        return None, "kerb not seen along part of the cul-de-sac", det
    for k in range(1, len(v) - 1):
        a, b, c = v[k - 1], v[k], v[k + 1]
        if None not in (a, b, c) and abs(a - c) <= AGREE and min(abs(b - a), abs(b - c)) > AGREE:
            v[k] = (a + c) / 2
    ok = [k for k in range(len(v)) if v[k] is not None]
    dd = np.interp(np.arange(m), np.array(cen, float)[ok], np.array([v[k] for k in ok], float))
    if np.max(np.abs(np.diff(dd))) > JUMP:
        return None, "footpath width jumps between runs", det
    return dd, "run widths", det


def one(st, ctx):
    """Kerb pieces (lists of MGA points) for one cul-de-sac, or ([], why, detail)."""
    p, why = reserve(st, ctx["lots_t"], ctx["lots"])
    if p is None:
        return [], why, {}
    w = widths(p, st)
    if not w or not W_MIN <= float(np.median(w)) <= W_MAX:
        return [], "reserve width not a street", {"w": round(float(np.median(w)), 1) if w else None}
    others = [r["g"] for i, r in enumerate(ctx["roads"]) if i not in st["parts"] and r["g"].distance(st["stem"]) < ZONE * 2]
    cls = [st["stem"]] + others
    ot = STRtree(others or [Point(1e9, 1e9)]); others = others or [Point(1e9, 1e9)]
    P, N, R, own, ok = front(p, st, STRtree(cls), cls, st["stem"].buffer(ZONE))
    runs = keep_runs(list(own & ok))
    if not runs:
        return [], "no front facing the street end", {}
    n = len(P); a, b = max(runs, key=lambda r: (r[1] - r[0]) % n)
    if sum(((r[1] - r[0]) % n + 1) * SAMPLE for r in runs if r != (a, b)) > STRAY:
        return [], "cul-de-sac front broken by another street", {}
    idx = [(a + k) % n for k in range(((b - a) % n) + 1)]
    if len(idx) * SAMPLE < MIN_LEN:
        return [], "no front facing the street end", {}
    J = st["junction"]
    if max(J.distance(Point(P[idx[0]])), J.distance(Point(P[idx[-1]]))) > MOUTH:
        return [], "cul-de-sac front does not reach back to the mouth on both sides", {}
    pos = positions(ctx["ground"], P, N, R, ok)
    dd, how, det = widths_along(ctx["ground"], pos, P, N, R, idx, n)
    det["w"] = round(float(np.median(w)), 1)
    if dd is None:
        return [], how, det
    det["how"] = how
    d = np.full(n, np.nan); d[idx] = dd
    for i in set(range(n)) - set(idx):   # round the corner returns: the width at the nearer end of the cul-de-sac
        d[i] = dd[0] if (idx[0] - i) % n <= (i - idx[-1]) % n else dd[-1]
    seen = ok.copy()
    K = P + N * np.nan_to_num(d)[:, None]
    det["d"] = round(float(np.median(dd)), 2)
    near = lambda v: ctx["kerb_t"] is not None and len(ctx["kerb_t"].query(Point(v), predicate="dwithin", distance=JOIN)) > 0
    idx, ends = extend(idx, n, K, seen, near)
    V = K[idx]
    if not LineString(V).is_simple:
        return [], "kerb crosses itself", det
    bad = clear_of(V, st, ot, others)
    if bad is not None:
        return [], "kerb runs within 2 m of a centreline", {**det, "at": [round(x, 1) for x in V[bad]]}
    pieces = kerb_pieces(V, near)
    if not pieces:
        return [], "kerb already there", det
    det["ends"] = ends
    return pieces, None, det


def lines_mga(paths):
    from pyproj import Transformer
    T = Transformer.from_crs(4326, 7856, always_xy=True); out = []
    for pth in paths:
        fc = json.load(gzip.open(pth) if pth.endswith(".gz") else open(pth))
        for f in fc["features"]:
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            g = shapely.transform(g, lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))
            for l in getattr(g, "geoms", [g]):
                out.append(l.exterior if l.geom_type == "Polygon" else l)
    return out


def load_lots(d):
    out = []
    for fn in sorted(glob.glob(os.path.join(d, "*.json"))):
        for f in json.load(open(fn))["features"]:
            if f.get("geometry"):
                g = shape(f["geometry"])
                out += [x for x in getattr(g, "geoms", [g]) if x.geom_type == "Polygon" and x.is_valid]
    return out


def main(a):
    roads_d, lots_d, grids_d, kerbs, out = a[:5]
    roads = load_roads(roads_d); lots = load_lots(lots_d); K = lines_mga([k for k in kerbs.split(",") if k])
    cells = None
    if "--cells" in a:
        cells = {tuple(map(int, l.split())) for l in open(a[a.index("--cells") + 1]) if l.strip()}
    ctx = {"roads": roads, "lots": lots, "lots_t": STRtree(lots), "ground": kpw.Ground(grids_d), "kerb_t": STRtree(K) if K else None}
    from pyproj import Transformer
    B = Transformer.from_crs(7856, 4326, always_xy=True)
    feats, why = [], collections.Counter(); whys = []
    for st in stems(roads):
        x, y = st["tip"].coords[0]
        if cells is not None and (int(x // 1000), int(y // 1000)) not in cells:
            continue
        pieces, w, det = one(st, ctx)
        why[w or "drawn"] += 1
        whys.append({"tip": [round(x, 1), round(y, 1)], "name": st["name"], "why": w or "drawn", **det})
        for k, q in enumerate(pieces):
            ll = [list(map(lambda v: round(v, 7), B.transform(*v))) for v in q]
            feats.append({"type": "Feature", "properties": {"id": f"C{int(x)}_{int(y)}-{k}", "street": st["name"], **det},
                          "geometry": {"type": "LineString", "coordinates": ll}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    if "--why" in a:
        json.dump(whys, open(a[a.index("--why") + 1], "w"))
    km = sum(LineString(f["geometry"]["coordinates"]).length for f in feats)
    print(json.dumps({"cul_de_sacs": sum(why.values()), "pieces": len(feats), "why": why.most_common()}))
    return 0


class _Fake:
    """Ground with a kerb step d metres in from the lot line of a synthetic cul-de-sac (selftest)."""
    def __init__(self, res, d):
        self.res, self.d = res, d

    def height(self, X, Y):
        inside = shapely.contains_xy(self.res.buffer(-self.d), X, Y)
        return np.where(inside, -0.15, 0.0) - 0.0 * X

    def covers(self, P):
        return True


def selftest():
    lots = [box(-100, 10, -6, 60), box(6, 10, 100, 60), box(-100, -60, 100, -10)]   # a through street along y=0, 20 m reserve
    bulb = Point(0, 70).buffer(12)
    lots[0] = lots[0].difference(bulb); lots[1] = lots[1].difference(bulb)
    lots.append(box(-100, 60, 100, 120).difference(bulb))
    roads = [{"g": LineString([(-100, 0), (0, 0)]), "fh": 5, "on": 1, "name": "MAIN", "nid": 1},
             {"g": LineString([(0, 0), (100, 0)]), "fh": 5, "on": 1, "name": "MAIN", "nid": 1},
             {"g": LineString([(0, 0), (0, 70)]), "fh": 6, "on": 1, "name": "CLOSE", "nid": 2}]
    S = [s for s in stems(roads) if s["name"] == "CLOSE"]
    assert len(S) == 1 and S[0]["stem"].length == 70, S
    land = unary_union(lots)
    res = box(-100, -100, 100, 130).difference(land)
    ctx = {"roads": roads, "lots": lots, "lots_t": STRtree(lots), "ground": _Fake(res, 3.0), "kerb_t": None}
    pieces, why, det = one(S[0], ctx)
    assert why is None and len(pieces) == 1, (why, det)
    L = LineString(pieces[0])
    assert abs(det["d"] - 3.0) < 0.6, det
    assert L.distance(Point(0, 70)) > 7.0 and L.distance(Point(0, 70)) < 10.0     # round the bulb, about 12 - 3 m from its middle
    assert all(e == "return" for e in det["ends"]), det
    assert all(abs(c[1]) > 6.0 for c in L.coords)                                  # never onto the through street's carriageway
    kerb = [LineString([(-100, 7), (-9, 7)]), LineString([(9, 7), (100, 7)])]        # existing kerbs along the through street
    ctx["kerb_t"] = STRtree(kerb)
    pieces, why, det = one(S[0], ctx)
    assert why is None and det["ends"] == ["join", "join"], det
    ctx["ground"] = _Fake(res, 0.0)                                                # no step: not measured, nothing drawn
    assert one(S[0], ctx)[1].startswith("kerb not seen")
    walk = lots[3].difference(box(-2, 60, 2, 120))                                 # a 4 m walkway past the bulb: still closed
    ctx2 = {**ctx, "lots": lots[:3] + [walk], "lots_t": STRtree(lots[:3] + [walk]), "ground": _Fake(res, 3.0), "kerb_t": None}
    assert one(S[0], ctx2)[1] is None, one(S[0], ctx2)[1]
    park = lots[3].difference(box(-30, 60, 30, 120))                               # a 60 m open reserve past the end: refused
    ctx3 = {**ctx2, "lots": lots[:3] + [park], "lots_t": STRtree(lots[:3] + [park])}
    assert one(S[0], ctx3)[1] == "reserve runs on past the street end", one(S[0], ctx3)[1]
    print("kerbcds selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(selftest() if a == ["--selftest"] else main(a))
