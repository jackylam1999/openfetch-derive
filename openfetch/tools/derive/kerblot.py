"""Lot-front kerbs (Jacky 18 Nov 2026, thread "Fill inner-city kerb gaps from lot fronts": "do we have ways to fix them? it is
critical ... make sure we don't make the same mistake"). The street-grid rings (kerbgrid.py) are offsets of road centrelines,
which are metres off in the inner city, so about 450 inner-Sydney rings ran over roofs or along rear lanes and were left blank.
Here the block is built from the land itself:
  1. block = union of cadastre lots (gaps under 0.8 m closed). Road reserve = everything between blocks.
  2. a reserve strip narrower than LANE_W (rear lane, walkway) with no street centreline along it is joined into the block, so
     no kerb runs along a lane and the street kerb runs straight across the lane mouth (as the layback does on the ground).
     Private estate roads sit inside lots (strata or community lots), so they are inside the block and get no kerb either.
  3. the kerb = the block outline pushed out into the street by the footpath width, measured per street side, in this order:
     LiDAR kerb trace on this side, on the other side, the kerb step in the LiDAR ground points (kerbpcw.py), the same named
     street's LiDAR widths, a drawn kerb across the street, the same street's drawn kerbs. A side with none is not guessed (block
     left blank). The 7 cm aerial was tried and is not used: on 195 LiDAR-measured sides it missed by over 1 m on most.
  4. whole or blank: a block is kept only if every gate passes (all sides face a street, no drawn kerb already there, the ring
     keeps clear of street centrelines, never runs over a roof (3 m inside a 120 m2+ footprint for over 3 m), never inside a lane,
     agrees with the LiDAR traces where they exist).

    python3 kerblot.py lots_dir roads_dir traced_raw.json drawn.geojson[.gz] buildings_dir cells.txt out.json [--why why.json]
        [--measure kerbs.geojson.gz (earlier kerbs used only to measure footpath widths; default the drawn file)] [--foot foot.json] [--ground grids_dir (kerbpcw.py ground grids)] [--nomeasure nm.json]
buildings_dir holds bldall.py files <x>_<y>.json (lon/lat). Writes closed rings (lon/lat) with id, cell, d (footpath widths).
"""
import glob, gzip, json, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
import kerbnet as kn
import kerbregular as kr
import kerbpcw as kpw
import kerbreview as kv

CLOSE = 0.4          # m: lot gaps under 0.8 m are drafting slivers, not reserves
LANE_W = 7.5         # m: a reserve strip narrower than this is a lane or walkway (rear lanes 3-6.1 m, streets 9 m and up)
LANE_FH = 7
NARROW_ST = 6        # functionhierarchy given to a lane-class centreline whose name is a street, road, avenue ...
LANE_TYPES = (None, "LANE")
STREET_LONG = 0.5    # share of a narrow strip's length a street centreline must run along for it to be a narrow street
STEP = 2.0           # m between front samples
RAY = 45.0           # m, how far across the street a front looks
D_MIN, D_MAX = 1.0, 7.0      # m, believable footpath widths (lot front to kerb)
C_MAX = 16.0         # m: a street's centreline lies within this of the lot front (a centreline seen past a rail line, creek
                     # or park strip is not this side's street; 18 Nov 2026 review: 9 rings ran along rail and bush edges)
CW_MIN = 2.5         # m, half a carriageway at least between the kerb and the centreline
MEASURED = 0.25      # share of a side's samples that must have a trace for its own median to be used
NO_STREET = 0.08     # share of front samples that may face no street (corner rays, splays)
COVER_RUN = 10.0     # m of front already kerbed (drawn or council kerb in front of it): not a blank block
CL_CLEAR = 0.5       # m the ring keeps from every street centreline outside the block (never crosses one)
BLD_IN, BLD_RUN, BLD_A = 3.0, 3.0, 120.0   # roof guard (the same numbers as the version gate)
AGREE_NEAR, AGREE_D, AGREE_MIN = 5.0, 1.5, 0.6
MIN_A, MAX_A = 300.0, 250000.0
FILL_E, FILL_W, ROUND_C, ROUND_R = 12.0, 3.0, 2.5, 3.0   # m: kerbs run straight past notches under 3 m wide in the lot fronts and
                                                        # turn on curves of 2.5-3 m or more (kerbaudit kinks, 18 Nov 2026)
PART = 0.85      # an earlier ring enclosing under 85 % of the block's land is a part-block ring (replaced when the whole block passes)
NOMEASURE = []
SAME_STREET_SPREAD = 0   # Vic 1.5 m: one block face along one street measured twice with widths this far apart is left blank
                         # (Vic review 19 Nov 2026: two rings wandered 4-8 m into the street between two pieces of one street)
CORNER_MIN = False   # corner_min(): tried for Vic 19 Nov 2026, made 17 of 48 rings step out past corners; kept off
STRAIGHT_WIN = 15    # samples (2 m apart) for straighten()
MITRE = False        # Vic True: mitre_parts()
SHORT_SIDE = 12.0   # m: an unmeasured side shorter than this is filled between its neighbours (Vic 30: block ends between two streets)
NOTCH = 5             # samples (10 m): a shorter stretch between two of one street's stretches is a notch
OSM_ALONE = True   # Vic aerial False: where the aerial finds no road the OSM line alone drew rings along the lot front past wide grass verges (review 7 V10, Bellfield)
GUTTER_WINS = bool(os.environ.get("KERB_GUTTER_WINS"))   # test only: the gutter is used even where the OSM path line lies past it
GUTTER = None   # Vic: an object with side_width(P, N, C) (kerbvic/mbdem.py), set by kerbvic/run_vic.py
NARROW_JOIN_FH = ()   # Vic (6,): a local street in a reserve under LANE_W ("Little" streets, 5-7 m, flush or one-sided) is joined like a lane
STREET_N, STREET_IQR = 8, 1.2   # a named street's own footpath width: 8 measures at least, middle half within 1.2 m


EPSG = int(os.environ.get("KERB_EPSG", "7856"))   # 7855 for Victoria (kerblot_vic.py)
SW_K, SW_FAR, SW_NEED, SW_LO = 2.17, 0.35, 0.4, 0.5
SW_ALONE_W = 24.0   # m: the OSM line alone measures only wide, fully paved streets (Carlton, East Melbourne 30 m: 66-74 % within
                    # 1 m); in 20 m streets with grass verges (Kensington, Brunswick) it falls metres short
PATH_HALF = 0.4   # m: half a footpath; the OSM path line must lie at least this far on the lot side of the gutter's kerb   # OSM footpath line: kerb at 2.17 x its distance from the lot front (Vic width study, 18 Nov 2026)


def tf():
    return Transformer.from_crs(4326, EPSG, always_xy=True).transform, Transformer.from_crs(EPSG, 4326, always_xy=True).transform


def sw_width(rays, m, C, W, ctx):
    """Footpath width from the OSM footpath line on this side (Vic, no LiDAR): 5 City of Melbourne boxes against the council's own
    kerbs put the kerb at 2.17 x the line's distance from the lot front, 61-74 % of samples within 1 m and 3 % over 3 m off. A line
    further out than SW_FAR of the reserve is the other side's footpath; fewer than SW_NEED of the side's samples is not measured."""
    if not ctx.get("sw"):
        return None
    hi = np.minimum(np.minimum(C, SW_FAR * W), 8.0)
    s = first_hit(rays[m], ctx["sw_t"], ctx["sw"], lo=SW_LO, hi=hi[m])
    if np.isfinite(s).sum() < max(5, SW_NEED * m.sum()):
        return None
    return float(SW_K * np.nanmedian(s))   # a line drawn on the lot boundary (under SW_LO out) says nothing about the width


def lines_ll(path, to):
    op = gzip.open if path.endswith(".gz") else open
    out = []
    for f in json.load(op(path, "rt"))["features"]:
        g = f["geometry"]
        for c in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []):
            if len(c) > 1:
                out.append(LineString([to(*p[:2]) for p in c]))
    return out


def buildings(d, cells, to):
    B = []
    for x, y in cells:
        fn = os.path.join(d, f"{x}_{y}.json")
        if not os.path.exists(fn):
            continue
        for f in json.load(open(fn))["features"]:
            p = Polygon([to(*c[:2]) for c in f["geometry"]["coordinates"][0]]).buffer(0)
            if p.area >= BLD_A:
                B.append(p)
    u = {}
    for p in B:
        u.setdefault(p.wkb, p)
    return list(u.values())


def first_hit(rays, T, G, lo=0.0, far=False, hi=None):
    """Distance along each ray (start at 0) to the nearest (or farthest) crossing with geometries G beyond lo; nan if none."""
    out = np.full(len(rays), np.nan)
    if not G:
        return out
    ri, gi = T.query(rays, predicate="intersects")
    for r, g in zip(ri, gi):
        x = rays[r].intersection(G[g])
        st = Point(rays[r].coords[0])
        pts = [Point(c) for q in getattr(x, "geoms", [x]) for c in getattr(q, "coords", [])] if not x.is_empty else []
        for p in pts:
            d = st.distance(p)
            if d > lo and (hi is None or d < hi[r]) and (np.isnan(out[r]) or (d > out[r] if far else d < out[r])):
                out[r] = d
    return out


def reserves(lots, frame):
    """Blocks (lots closed over slivers) and the narrow reserve strips (lanes, walkways, narrow streets)."""
    land0 = unary_union([l.buffer(CLOSE) for l in lots]).buffer(-CLOSE)
    res = frame.difference(land0)
    wide = res.buffer(-LANE_W / 2).buffer(LANE_W / 2)
    narrow = res.difference(wide.buffer(0.05)).buffer(-0.1).buffer(0.1)
    return land0, [p for p in getattr(narrow, "geoms", [narrow]) if p.area > 5]


def long_side(p):
    r = p.minimum_rotated_rectangle
    c = np.asarray(r.exterior.coords)
    return max(np.hypot(*(c[1] - c[0])), np.hypot(*(c[2] - c[1])))


def front_samples(comp):
    ext = comp.exterior
    n = max(8, int(ext.length / STEP))
    t = np.linspace(0, ext.length, n, endpoint=False)
    P = np.asarray([ext.interpolate(v).coords[0] for v in t])
    A = np.asarray([ext.interpolate((v - 0.5) % ext.length).coords[0] for v in t])
    Bq = np.asarray([ext.interpolate((v + 0.5) % ext.length).coords[0] for v in t])
    tan = Bq - A; tan /= np.maximum(np.hypot(tan[:, 0], tan[:, 1]), 1e-9)[:, None]
    nrm = np.c_[tan[:, 1], -tan[:, 0]]
    test = shapely.points(P + nrm * 0.3)
    flip = shapely.contains(comp, test)
    nrm[flip] *= -1
    return P, nrm


def two_judge(rays, m, C, W, P, N, ctx):
    """Vic width without LiDAR points: the gutter in a coarse ground model (ctx["gutter"], kerbvic/mbdem.py) first, the OSM footpath
    line second. The OSM line marks the path, not the kerb: where a grass verge lies between them (Brunswick back streets, 20 m
    reserves, 7 m carriageways) 2.17 x its distance falls metres short (Brunswick, 325 sides measured both ways: the gutter was
    1.5-3.6 m wider on 10 %, all of them 15-20 m streets whose OSM width left a 13-16 m carriageway). So with a gutter, the OSM line
    only has to lie on the lot side of it; a side whose path line lies beyond the gutter is left blank."""
    g = ctx["gutter"].side_width(P[m], N[m], W[m] / 2) if ctx.get("gutter") is not None else None
    o = sw_width(rays, m, C, W, ctx)
    if g is not None:
        if o is not None and o / SW_K + PATH_HALF > g and not GUTTER_WINS:
            return None, ""
        return g, "ground gutter" + (" (osm path inside)" if o is not None else "")
    if o is not None and float(np.nanmedian(W[m])) >= SW_ALONE_W and OSM_ALONE:
        return o, "osm footpath this side"
    return None


def street_ok(vals):
    """Median footpath width of one named street, when there are enough measures and they agree (inner-city streets keep one
    footpath width along their length more often than not; a street whose measures spread is not used)."""
    if not vals or len(vals) < STREET_N:
        return None
    q1, q2, q3 = np.percentile(vals, [25, 50, 75])
    return float(q2) if q3 - q1 <= STREET_IQR else None


def street_feet(stl, names, land0, raw, raw_t, drawn, drawn_t, foot):
    """Footpath widths along every street: from points on the centreline, both ways across, the distance from the lot front
    back to the kerb nearest the property (LiDAR trace, or a drawn kerb), per street name."""
    lb = [land0.boundary] if not land0.is_empty else []
    if not lb:
        return
    for g, nm in zip(stl, names):
        if nm is None or g.length < 8:
            continue
        t = np.arange(2.0, g.length - 2.0, 4.0)
        if not len(t):
            continue
        P = np.asarray([g.interpolate(v).coords[0] for v in t])
        tan = np.asarray([g.interpolate(min(v + 0.5, g.length)).coords[0] for v in t]) - np.asarray([g.interpolate(max(v - 0.5, 0)).coords[0] for v in t])
        tan /= np.maximum(np.hypot(tan[:, 0], tan[:, 1]), 1e-9)[:, None]
        for sgn in (1, -1):
            N = np.c_[tan[:, 1], -tan[:, 0]] * sgn
            rays = shapely.linestrings(np.stack([P, P + N * 30.0], axis=1))
            F = first_hit(rays, STRtree(lb), lb, lo=0.5)
            for key, G, T in (("lidar", raw, raw_t), ("drawn", drawn, drawn_t)):
                K = first_hit(rays, T, G, lo=CW_MIN, far=True, hi=F)
                ok = np.isfinite(F) & np.isfinite(K) & (K < F)
                d = (F - K)[ok]
                foot.setdefault(nm, {}).setdefault(key, []).extend(d[(d >= D_MIN) & (d <= D_MAX)].round(2).tolist())



def straighten(off, win=STRAIGHT_WIN):
    """A kerb runs straight (or on the street's own curve) past lots set back from the street: the side's offset points are put
    on a running median of their distance from the side's best-fit line, over `win` samples (Vic review 5, 19 Nov 2026: 3 of 40
    rings stepped 2-4 m sideways where a few lots' fronts jog in or out)."""
    if len(off) < 5 or win < 3:
        return off
    c = off.mean(axis=0); u = np.linalg.svd(off - c)[2][0]; v = np.array([-u[1], u[0]])
    t = (off - c) @ u; r = (off - c) @ v
    h = win // 2
    rs = np.array([np.median(r[max(0, i - h): i + h + 1]) for i in range(len(r))])
    return c + np.outer(t, u) + np.outer(rs, v)


def fill_notches(CID, most=NOTCH):
    """A short stretch of front between two stretches facing the same street is a notch (a lane mouth, a set-back lot), not a
    street side of its own: it takes that street's id, so the kerb runs straight across it (Vic review 5, 19 Nov 2026: a lane
    mouth made its own side and the corner joins either side of it pushed a 2 m bump into Bell St)."""
    c = np.asarray(CID).copy(); n = len(c)
    for _ in range(4):
        start = next((i for i in range(n) if c[i] != c[i - 1]), None)
        if start is None:
            return c
        runs, cur = [], [start]
        for k in range(1, n):
            i = (start + k) % n
            if c[i] == c[cur[-1]]:
                cur.append(i)
            else:
                runs.append(cur); cur = [i]
        runs.append(cur)
        if len(runs) < 3:
            return c
        changed = False
        for j, r in enumerate(runs):
            a, b = runs[j - 1], runs[(j + 1) % len(runs)]
            if len(r) <= most and c[r[0]] != c[a[-1]] and c[a[-1]] == c[b[0]] and c[a[-1]] >= 0:
                c[r] = c[a[-1]]; changed = True
        if not changed:
            return c
    return c


def mitre_parts(P, N, D, CID, fan=25.0):
    """The kerb as each street side's own offset strip, joined at block corners where the two offset lines meet (then rounded by
    smooth()), the way a kerb return is set out. Round buffers per sample (the default) carry the wider side's width round the
    corner as an arc, which swings 2-4 m into the junction; carrying the narrower width instead stepped 2-4 m out 10 m past the
    corner (Vic reviews 19 Nov 2026: 6 of 40, then 17 of 48). Corner samples whose normal turns more than `fan` deg off their
    side's mean are left to the join."""
    n = len(P)
    if n < 4:
        return []
    CID = fill_notches(CID)
    start = next((i for i in range(n) if CID[i] != CID[i - 1]), None)
    order = list(range(n)) if start is None else [(start + k) % n for k in range(n)]
    runs, cur = [], [order[0]]
    for i in order[1:]:
        if CID[i] == CID[cur[-1]]:
            cur.append(i)
        else:
            runs.append(cur); cur = [i]
    runs.append(cur)
    keep = []
    for r in runs:
        mn = N[r].mean(axis=0); mn /= max(np.hypot(*mn), 1e-9)
        k = [i for i in r if float(np.dot(N[i], mn)) > np.cos(np.radians(fan))]
        if len(k) >= 2:
            keep.append(k)
    parts = []
    offs = {}
    for k in keep:
        off = straighten(P[k] + N[k] * D[k][:, None])
        offs[k[0]], offs[k[-1]] = off[0], off[-1]
        parts.append(Polygon(np.vstack([P[k], off[::-1]])).buffer(0))
    if start is None or len(keep) < 2:
        return parts
    for a_, b_ in zip(keep, keep[1:] + keep[:1]):
        a0, a1 = P[a_[-2]] + N[a_[-2]] * D[a_[-2]], offs[a_[-1]]
        b0, b1 = offs[b_[0]], P[b_[1]] + N[b_[1]] * D[b_[1]]
        a0 = a1 - (P[a_[-1]] - P[a_[-2]]); b1 = b0 + (P[b_[1]] - P[b_[0]])
        da, db = a1 - a0, b1 - b0
        den = da[0] * db[1] - da[1] * db[0]
        ring = [P[a_[-1]], a1]
        if abs(den) > 1e-6 * max(np.hypot(*da) * np.hypot(*db), 1e-9):
            t = ((b0[0] - a0[0]) * db[1] - (b0[1] - a0[1]) * db[0]) / den
            X = a0 + da * t
            if t > 0.5 and np.hypot(*(X - a1)) < 2 * max(D[a_[-1]], D[b_[0]]) + 4 and np.hypot(*(X - b0)) < 2 * max(D[a_[-1]], D[b_[0]]) + 4:
                ring.append(X)
        ring += [b0, P[b_[0]]]
        ring += [P[i] for i in order[order.index(a_[-1]):order.index(b_[0]) + 1][1:-1]] [::-1] if order.index(a_[-1]) < order.index(b_[0]) else []
        g = Polygon(ring).buffer(0)
        if g.area > 0:
            parts.append(g)
    return parts


def corner_min(D, CID, street, k=4):
    """Where the front turns from one street to the next, the narrower footpath runs round the corner (Vic review 19 Nov 2026: 6 of
    40 rings swung 3-4 m out into the junction where a wide side's width was carried round the corner to a narrow side)."""
    n = len(D); out = D.copy()
    cid = np.where(street, CID, -1)
    for i in range(n):
        j = (i + 1) % n
        if cid[i] >= 0 and cid[j] >= 0 and cid[i] != cid[j]:
            idx = [(i + o) % n for o in range(-k - 3, k + 4)]
            lo = min(D[(i + o) % n] for o in range(-k, k + 1))
            for q in idx:
                out[q] = min(out[q], lo)
    return out


def smooth(p):
    """A kerb line, not a copy of every jog in the lot fronts: fill thin notches (lane mouths, set-back lots), then round the
    corners. Without it 287 of 423 rings had kinks or wobbles (kerbaudit), seven times the rate of traced kerbs."""
    c = p.buffer(FILL_E, quad_segs=16).buffer(-FILL_E, quad_segs=16).difference(p)
    p = unary_union([p] + [g for g in getattr(c, "geoms", [c]) if g.area > 0 and g.buffer(-FILL_W / 2).is_empty])
    return p.buffer(ROUND_C, quad_segs=16).buffer(-ROUND_C - ROUND_R, quad_segs=16).buffer(ROUND_R, quad_segs=16)

def judge_block(comp, ctx):
    """Kerb ring for one block or (reason, None)."""
    P, N = front_samples(comp)
    st = shapely.points(P + N * 0.05)
    rays = shapely.linestrings(np.stack([P + N * 0.05, P + N * RAY], axis=1))
    W = first_hit(rays, ctx["land_t"], ctx["land_b"], lo=0.3)
    W[np.isnan(W)] = RAY
    ext_st = [i for i, g in enumerate(ctx["st"]) if not (g.intersection(comp.buffer(0.5)).length > 0.8 * g.length)]
    SG = [ctx["st"][i] for i in ext_st]
    if not SG:
        return "no street", None
    ST = STRtree(SG)
    C = np.full(len(rays), np.nan); CID = np.full(len(rays), -1)
    ri, gi = ST.query(rays, predicate="intersects")
    for r, g in zip(ri, gi):
        x = rays[r].intersection(SG[g])
        for q in getattr(x, "geoms", [x]):
            if q.is_empty or q.geom_type != "Point":
                continue
            d = Point(rays[r].coords[0]).distance(q)
            if d < min(W[r], C_MAX) and (np.isnan(C[r]) or d < C[r]):
                C[r], CID[r] = d, ext_st[g]
    street = ~np.isnan(C)
    if (~street).mean() > NO_STREET:
        return "side faces no street", None
    reach = comp.buffer(D_MAX + 1.0)
    def part(g):   # an earlier closed ring round only a part of this block (a half block cut off by its rear lane)
        return g.within(reach) and g.is_ring and Polygon(g).area < PART * comp.area
    inside = [g for g in ctx["drawn"] if part(g)]      # replaced by this whole-block ring, not coverage
    others = [g for g in ctx["drawn"] if not part(g)]
    cov = first_hit(rays, STRtree(others), others)
    cov_m = np.sum((~np.isnan(cov)) & street & (cov < np.where(street, C, 0) + 0.5)) * STEP
    if cov_m >= COVER_RUN:
        return "kerb already there", None
    near = first_hit(rays, ctx["raw_t"], ctx["raw"], lo=0.5)
    farr = first_hit(rays, ctx["raw_t"], ctx["raw"], lo=0.5, far=True, hi=W)
    d_own = np.where(street & (near < C) & (near >= D_MIN) & (near <= D_MAX), near, np.nan)
    opp = W - farr
    d_opp = np.where(street & (farr > C) & (farr < W) & (opp >= D_MIN) & (opp <= D_MAX) & (W < RAY), opp, np.nan)
    dfar = first_hit(rays, ctx["meas_t"], ctx["meas"], lo=0.5, far=True, hi=W)
    dnear = first_hit(rays, ctx["meas_t"], ctx["meas"], lo=0.5)
    d_ownd = np.where(street & (dnear < C) & (dnear >= D_MIN) & (dnear <= D_MAX), dnear, np.nan)
    oppd = W - dfar
    d_oppd = np.where(street & (dfar > C) & (dfar < W) & (oppd >= D_MIN) & (oppd <= D_MAX) & (W < RAY), oppd, np.nan)
    D = np.full(len(rays), np.nan); used = {}
    for cid in set(CID[street].tolist()):
        m = CID == cid
        n = m.sum()
        need = max(3, MEASURED * n)
        nm = ctx["st_name"][cid]
        tab = ctx["foot"].get(nm, {})
        if np.isfinite(d_own[m]).sum() >= need:
            v, how = float(np.nanmedian(d_own[m])), "lidar this side"
        elif np.isfinite(d_opp[m]).sum() >= need:
            v, how = float(np.nanmedian(d_opp[m])), "lidar other side"
        elif ctx["ground"] is not None and (pv := kpw.side_width(ctx["ground"], P[m], N[m], float(np.nanmedian(W[m])) / 2)) is not None:
            v, how = pv, "lidar step"
        elif (vv := two_judge(rays, m, C, W, P, N, ctx)) is not None:
            if vv[0] is None:
                return "footpath measures disagree", None
            v, how = vv
        elif not ctx.get("borrow", True):
            if n * STEP < SHORT_SIDE:
                continue   # a short block end takes the width tapered between its measured neighbours
            NOMEASURE.append((nm, int(n), {}, 0, 0, 0))
            return "no footpath measure", None
        elif np.isfinite(d_ownd[m]).sum() >= need:
            v, how = float(np.nanmedian(d_ownd[m])), "earlier kerb this side"
        elif street_ok(tab.get("lidar")):
            v, how = street_ok(tab["lidar"]), "lidar same street"
        elif np.isfinite(d_oppd[m]).sum() >= need:
            v, how = float(np.nanmedian(d_oppd[m])), "kerb other side"
        elif street_ok(tab.get("drawn")):
            v, how = street_ok(tab["drawn"]), "kerbs same street"
        elif n * STEP < 12:
            continue
        else:
            NOMEASURE.append((nm, int(n), {k: len(v) for k, v in tab.items()}, int(np.isfinite(d_own[m]).sum()), int(np.isfinite(d_opp[m]).sum()), int(np.isfinite(d_oppd[m]).sum())))
            return "no footpath measure", None
        v = min(v, float(np.nanmedian(W[m])) / 2 - CW_MIN)   # the reserve, not the centreline: centrelines are metres off here
        if v < D_MIN:
            return "street too narrow for a footpath", None
        D[m] = v; used[str(nm) + ":" + str(int(cid))] = (round(v, 2), how)
    if SAME_STREET_SPREAD:
        per = {}
        for key, (val, _) in used.items():
            per.setdefault(key.rsplit(":", 1)[0], []).append(val)
        if any(max(v) - min(v) > SAME_STREET_SPREAD for v in per.values()):
            return "widths differ along one street", None
    fill = np.isnan(D)
    if fill.all():
        return "no footpath measure", None
    D[fill] = np.interp(np.flatnonzero(fill), np.flatnonzero(~fill), D[~fill], period=len(D))
    if CORNER_MIN:
        D = corner_min(D, CID, street)
    if MITRE:
        segs = mitre_parts(P, N, D, np.where(street, CID, -2))
    else:
        segs = [shapely.convex_hull(Point(P[i]).buffer(D[i], quad_segs=8).union(Point(P[(i + 1) % len(P)]).buffer(D[(i + 1) % len(P)], quad_segs=8)))
                for i in range(len(P))]   # tapered, not the larger width: a corner where two widths meet steps out and back (a wobble)
    poly = smooth(unary_union(segs + [comp]))
    if poly.geom_type != "Polygon" and sorted(g.area for g in poly.geoms)[-2] > 1.0:
        return "ring splits when smoothed", None
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    ring = Polygon(poly.exterior).simplify(0.15)
    q = ring.exterior
    if not q.is_simple:
        return "ring touches itself", None
    if comp.difference(ring.buffer(0.3)).area > 1.0:
        return "ring cuts into the lots", None
    if not (MIN_A <= ring.area <= MAX_A):
        return "size", None
    fold = []
    kv.folds(LineString(q.coords), fold)
    if fold:
        return "ring folds back on itself", None   # the version review (kerbreview fold) refuses these: never make one
    for g, fh in zip(SG, [ctx["st_fh"][i] for i in ext_st]):
        if fh == LANE_FH:
            continue   # a lane joined into this block or the next: the kerb crosses its mouth on purpose
        if g.distance(q) < CL_CLEAR or g.intersection(ring.buffer(-0.5)).length > 1.0 or g.intersects(q):
            return "street centreline inside or too close", None
    for k in ctx["bld_t"].query(q):
        part = q.intersection(ctx["bld"][int(k)].buffer(-BLD_IN))
        if not part.is_empty and max(p.length for p in getattr(part, "geoms", [part])) > BLD_RUN:
            return "over a roof", None
    for L in ctx["lanes"]:
        if L.intersects(ring) and q.intersection(L.buffer(-0.3)).length > 3.0 and not L.within(comp.buffer(0.3)):
            return "along a lane", None
    pts = shapely.points(np.asarray([q.interpolate(t).coords[0] for t in np.arange(0, q.length, 1.0)]))
    near_raw = np.asarray([min([ctx["raw"][int(k)].distance(p) for k in ctx["raw_t"].query(p.buffer(AGREE_NEAR))] or [99]) for p in pts])
    seen = near_raw < AGREE_NEAR
    if seen.sum() > 20 and (near_raw[seen] < AGREE_D).mean() < AGREE_MIN:
        return "does not agree with LiDAR", None
    return None, (ring, used, float(seen.mean()), inside)


def main(a):
    to, back = tf()
    cells = [tuple(map(int, l.split())) for l in open(a[5]) if l.strip()]
    lots_all = [g for g in kr.load_faces(a[0]) if g.geom_type == "Polygon"]
    LT = STRtree(lots_all)
    roads, rname = [], []
    seen = set()
    for fn in sorted(glob.glob(os.path.join(a[1], "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            if not f.get("geometry") or pr.get("OBJECTID", pr.get("objectid")) in seen:
                continue
            seen.add(pr.get("OBJECTID", pr.get("objectid")))
            g = shape(f["geometry"])
            for q in (g.geoms if g.geom_type.startswith("Multi") else [g]):
                if q.geom_type == "LineString" and q.length > 0:
                    fh = pr.get("functionhierarchy")
                    if fh == LANE_FH and pr.get("roadnametype") not in LANE_TYPES:
                        fh = NARROW_ST   # mapped as a lane but named a street (Kepos St): a narrow street, never joined into a block
                    roads.append((q, fh)); rname.append(pr.get("roadnameoid"))
    over = []
    for fn in sorted(glob.glob(os.path.join(a[1], "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            if pr.get("roadontype") in (2, 3) and f.get("geometry"):
                over += [q for q in getattr(shape(f["geometry"]), "geoms", [shape(f["geometry"])]) if q.geom_type == "LineString"]
    nm_of = {id(g): n for (g, _), n in zip(roads, rname)}
    ground = [(g, fh, nm_of.get(id(g))) for g, fh in kn.on_ground(roads, over) if fh not in ka.SKIP_FH]
    RW = [LineString(t) for t in ka.read_kerbs(a[2], EPSG) if len(t) > 1]
    SW = lines_ll(a[a.index("--sidewalks") + 1], to) if "--sidewalks" in a else []
    DR = lines_ll(a[3], to)
    MS = lines_ll(a[a.index("--measure") + 1], to) if "--measure" in a else DR
    keep, why, cnt, done = [], [], {}, set()
    foot, prep = {}, []
    if "--foot-only" in a:
        pass
    for x, y in cells:
        cell = box(x * 1000, y * 1000, x * 1000 + 1000, y * 1000 + 1000)
        frame = cell.buffer(300, join_style="mitre")
        lots = [lots_all[int(k)] for k in LT.query(frame)]
        land0, narrow = reserves(lots, frame)
        stg = [(g, fh, n) for g, fh, n in ground if g.intersects(frame)]
        lanes = []
        for p in narrow:
            inside = sum(g.intersection(p).length for g, fh, _ in stg if fh != LANE_FH and fh not in NARROW_JOIN_FH and g.intersects(p))
            if not (long_side(p) > 15 and inside > STREET_LONG * long_side(p)) and not any(
                    fh == NARROW_ST and fh not in NARROW_JOIN_FH and g.intersection(p).length > 10 for g, fh, _ in stg if g.intersects(p)):
                lanes.append(p)
        raw = [g for g in RW if g.intersects(frame)]; dr = [g for g in DR if g.intersects(frame)]; ms = [g for g in MS if g.intersects(frame)]
        inner = [(g.intersection(cell), n) for g, fh, n in stg if fh != LANE_FH and g.intersects(cell)]
        inner = [(q, n) for g, n in inner for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
        if "--foot-in" not in a:
            street_feet([q for q, _ in inner], [n for _, n in inner], land0, raw, STRtree(raw), ms, STRtree(ms), foot)
        prep.append((x, y, cell, frame, land0, lanes, stg, raw, dr, ms))
        print("feet", x, y, len(foot), flush=True)
    if "--foot-raw" in a:
        json.dump({str(k): v for k, v in foot.items()}, open(a[a.index("--foot-raw") + 1], "w"))
        if "--foot-only" in a:
            return
    if "--foot-in" in a:
        foot = {}
        for fn in a[a.index("--foot-in") + 1].split(","):
            for k, v in json.load(open(fn)).items():
                for kk, vv in v.items():
                    foot.setdefault(int(k) if k.isdigit() else k, {}).setdefault(kk, []).extend(vv)
    if "--foot" in a:
        json.dump({str(k): {kk: [len(vv), street_ok(vv)] for kk, vv in v.items()} for k, v in foot.items()}, open(a[a.index("--foot") + 1], "w"))
    for x, y, cell, frame, land0, lanes, stg, raw, dr, ms in prep:
        land = unary_union([land0] + lanes)
        comps = [Polygon(g.exterior) for g in getattr(land, "geoms", [land]) if g.geom_type == "Polygon"]
        LB = [c.exterior for c in comps]
        B = buildings(a[4], [(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1)], to)
        ctx = {"land_b": LB, "land_t": STRtree(LB), "st": [g for g, _, _ in stg], "st_name": [n for _, _, n in stg], "st_fh": [fh for _, fh, _ in stg], "foot": foot,
               "raw": raw, "raw_t": STRtree(raw), "drawn": dr, "drawn_t": STRtree(dr), "meas": ms, "meas_t": STRtree(ms), "bld": B, "bld_t": STRtree(B), "lanes": lanes,
               "ground": kpw.Ground(a[a.index("--ground") + 1]) if "--ground" in a else None,
               "sw": [g for g in SW if g.intersects(frame)], "borrow": "--no-borrow" not in a, "gutter": GUTTER}
        ctx["sw_t"] = STRtree(ctx["sw"])
        for c in comps:
            rp = c.representative_point()
            if not cell.contains(rp) or not c.within(frame.buffer(-30)) or c.area < MIN_A:
                continue
            key = (round(rp.x, 1), round(rp.y, 1))
            if key in done:
                continue
            done.add(key)
            w, res = judge_block(c, ctx)
            cnt[w or "kept"] = cnt.get(w or "kept", 0) + 1
            bid = f"L{x}{y}-{len(keep) + len(why)}"
            if w:
                why.append((w, Polygon(c.exterior), bid, f"{x}_{y}"))
            else:
                ring, used, seen, inside = res
                keep.append((ring, used, seen, bid, f"{x}_{y}", [[[round(v, 7) for v in back(*p)] for p in g.coords] for g in inside]))
        print(x, y, json.dumps(cnt), flush=True)
    ll = lambda g: [[round(v, 7) for v in back(*p)] for p in g.exterior.coords]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": b, "cell": n, "d": {str(k): v for k, v in u.items()},
               "lidar_seen": round(s, 2), "source": "lot front", "replaces": rp}, "geometry": {"type": "LineString", "coordinates": ll(r)}} for r, u, s, b, n, rp in keep]}, open(a[6], "w"))
    if "--why" in a:
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"why": w, "id": b, "cell": n},
                   "geometry": {"type": "LineString", "coordinates": ll(g)}} for w, g, b, n in why]}, open(a[a.index("--why") + 1], "w"))
    if "--nomeasure" in a:
        json.dump(NOMEASURE, open(a[a.index("--nomeasure") + 1], "w"))
    print("RESULT", json.dumps({"count": cnt, "km": round(sum(k[0].exterior.length for k in keep) / 1000, 2)}))


if __name__ == "__main__":
    main(sys.argv[1:])
