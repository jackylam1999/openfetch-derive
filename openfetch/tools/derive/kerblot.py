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
        [--cad cad_dir (kerbcad.py: a ring with a run outside the official road reserve is left blank)]
        [--calib calib.json (sides with a LiDAR kerb trace: trace width, ground step, every profile's kerb; tunes kerbpcw.py)]
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
import kerbcad as kc
import kerblane
import kerbside

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
CW_OWN, OWN = 1.75, ("lidar this side", "lidar step", "lidar profiles")   # a kerb the LiDAR saw on this very side: narrow terrace streets (6-7 m
                     # between lot fronts) keep 1-1.25 m footpaths and a 3.5 m carriageway; 45 such blocks were refused (19 Nov 2026)
WIDE = 0.75          # a centreline past C_MAX still faces this side when it lies before the land across, within 3/4 of the way
                     # (wide streets, 25-45 m between lot fronts: 117 blocks were refused as facing no street, 19 Nov 2026)
MEASURED = 0.25      # share of a side's samples that must have a trace for its own median to be used
NO_STREET = 0.08     # share of front samples that may face no street (corner rays, splays)
COVER_RUN = 10.0     # m of front already kerbed (drawn or council kerb in front of it): not a blank block
CL_CLEAR = 0.5       # m the ring keeps from every street centreline outside the block (never crosses one)
BLD_IN, BLD_RUN, BLD_A = 3.0, 3.0, 120.0   # roof guard (the same numbers as the version gate)
AGREE_NEAR, AGREE_D, AGREE_MIN = 5.0, 1.5, 0.6
MIN_A, MAX_A = 300.0, 250000.0
FRAME = 800.0   # m of land read round each 1 km square: big blocks (industrial, bushland) were never judged with 300 m (19 Nov 2026)
DETAIL = {}
ROADLOT_IN, ROADLOT_RUN = 3.0, 15.0   # m (drop_road_lots)
CL_BAND = '--cl-band' in sys.argv   # centrelines are tolerated inside the footpath band (19 Nov 2026)
FILL_E, FILL_W, ROUND_C, ROUND_R = 12.0, 3.0, 2.5, 3.0   # m: kerbs run straight past notches under 3 m wide in the lot fronts and
                                                        # turn on curves of 2.5-3 m or more (kerbaudit kinks, 18 Nov 2026)
PART = 0.85      # an earlier ring enclosing under 85 % of the block's land is a part-block ring (replaced when the whole block passes)
NOMEASURE = []
LANE_RUN = 12.0  # m: a longer run of the front facing only a lane centreline is a rear or service lane, never kerbed here (with
                 # --cad; 19 Nov 2026 close-up reviews: 7 of 30 refused rings ran a slot or spur down a lane wider than LANE_W)
STREET_N, STREET_IQR = 8, 1.2   # a named street's own footpath width: 8 measures at least, middle half within 1.2 m


def tf():
    return Transformer.from_crs(4326, 7856, always_xy=True).transform, Transformer.from_crs(7856, 4326, always_xy=True).transform


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


def drop_road_lots(lots, streets):
    """Cadastre lots that carry a street (road lots, closed roads kept as lots, stratum lots under a road) join the blocks on
    both sides into one block of 50-150 ha that is never judged (19 Nov 2026: 29 km of street sides in the top 10 suburbs).
    A lot with more than ROADLOT_RUN m of street centreline more than ROADLOT_IN m inside it is road, not land."""
    T = STRtree(streets)
    li, si = T.query(lots, predicate="intersects")
    run = {}
    for i, j in zip(li.tolist(), si.tolist()):
        inner = lots[i].buffer(-ROADLOT_IN)
        if not inner.is_empty:
            run[i] = run.get(i, 0.0) + streets[j].intersection(inner).length
    drop = {i for i, v in run.items() if v > ROADLOT_RUN}
    print("road lots", len(drop), "of", len(lots), flush=True)
    return [g for i, g in enumerate(lots) if i not in drop], [lots[i] for i in sorted(drop)]


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



def smooth(p):
    """A kerb line, not a copy of every jog in the lot fronts: fill thin notches (lane mouths, set-back lots), then round the
    corners. Without it 287 of 423 rings had kinks or wobbles (kerbaudit), seven times the rate of traced kerbs."""
    c = p.buffer(FILL_E, quad_segs=16).buffer(-FILL_E, quad_segs=16).difference(p)
    p = unary_union([p] + [g for g in getattr(c, "geoms", [c]) if g.area > 0 and g.buffer(-FILL_W / 2).is_empty])
    return p.buffer(ROUND_C, quad_segs=16).buffer(-ROUND_C - ROUND_R, quad_segs=16).buffer(ROUND_R, quad_segs=16)

def corridor_streets(P, N, W, rays, ri, gi, SG, ext_st, C, CID, cad):
    """A side faces a street when the official road corridor it opens onto holds a street centreline before the land across
    (or within RAY when there is none), however far: wide streets and centrelines drawn off-centre were "faces no street"
    (19 Nov 2026: 124 blocks had the centreline past 3/4 of the way across, 177 faced open ground). Fills C and CID in place."""
    cor = cad.corridor_at(P + N * 1.0)
    for r, g in zip(ri, gi):
        if not np.isnan(C[r]) or cor[r] < 0:
            continue
        x = rays[r].intersection(SG[g])
        for q in getattr(x, "geoms", [x]):
            if q.is_empty or q.geom_type != "Point" or not cad.in_corridor(q, cor[r]):
                continue
            d = Point(rays[r].coords[0]).distance(q)
            if d < W[r] and (np.isnan(C[r]) or d < C[r]):
                C[r], CID[r] = d, ext_st[g]


CALIB = [] if "--calib" in sys.argv else None


def calib(G, P, N, W, d_tr, nm):
    """--calib out.json: on sides with a LiDAR kerb trace (1-12 m out), the trace's width beside the median-profile step and every
    profile's own kerb (all on the traces' footing), for tuning kerbpcw offline."""
    reach = float(np.nanmedian(W)) / 2
    t = np.arange(0.0, min(reach, 13.5), kpw.STEP_D)
    H = kpw.profiles(G, P, N, t)
    with np.errstate(all="ignore"):
        pos = kpw.prof_positions(np.nanmedian(H, axis=0), t, 1.0 - kpw.P_SHIFT, 12.0 - kpw.P_SHIFT) + kpw.P_SHIFT
        h = np.nanmedian(H.reshape(-1, len(t)), axis=0)
    d = kpw.step_in(h, t, 1.0, 7.0) if np.isnan(h).mean() <= 0.3 else None
    a = None if d is None or not 1.0 <= d + kpw.SHIFT <= 7.0 else d + kpw.SHIFT
    CALIB.append([float(np.nanmedian(d_tr)), a, [None if np.isnan(v) else round(float(v), 2) for v in pos], round(reach * 2, 1), str(nm)])


SIDE = {}   # outline samples of the block last refused as facing no street, for kerbside.py (--sides)
SIDES = '--sides' in sys.argv   # --sides out.json: street-side lines (kerbside.py)


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
            if d < min(W[r], max(C_MAX, WIDE * W[r] if W[r] < RAY else 0)) and (np.isnan(C[r]) or d < C[r]):
                C[r], CID[r] = d, ext_st[g]
    if ctx["cad"] is not None:
        corridor_streets(P, N, W, rays, ri, gi, SG, ext_st, C, CID, ctx["cad"])
    street = ~np.isnan(C)
    if ctx["cad"] is not None:
        lane = street & np.isin(CID, [i for i, fh in enumerate(ctx["st_fh"]) if fh == LANE_FH])
        if kc.longest(lane) * STEP > LANE_RUN:
            DETAIL[comp.representative_point().wkt] = {"lane_m": round(float(kc.longest(lane) * STEP), 1)}
            return "side runs along a lane", None
    if (~street).mean() > NO_STREET:
        SIDE.update(P=P, N=N, W=W, C=C, CID=CID, street=street, rays=rays)
        far = np.full(len(rays), np.nan)
        for r, g in zip(ri, gi):
            x = rays[r].intersection(SG[g])
            for q in getattr(x, "geoms", [x]):
                if q.geom_type == "Point":
                    d = Point(rays[r].coords[0]).distance(q)
                    if d < W[r] and (np.isnan(far[r]) or d < far[r]):
                        far[r] = d
        ns = ~street
        DETAIL[comp.representative_point().wkt] = {"no_street_m": round(float(ns.sum() * STEP), 1), "share": round(float(ns.mean()), 3),
            "wide_street": int(np.sum(ns & ~np.isnan(far))), "land_across": int(np.sum(ns & np.isnan(far) & (W < RAY))),
            "open": int(np.sum(ns & np.isnan(far) & (W >= RAY))), "w_med": round(float(np.nanmedian(np.where(ns, W, np.nan))), 1)}
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
        if CALIB is not None and ctx["ground"] is not None:
            d_tr = np.where(street[m] & (near[m] < C[m]) & (near[m] >= D_MIN) & (near[m] <= 12.0), near[m], np.nan)
            if np.isfinite(d_tr).sum() >= need:
                calib(ctx["ground"], P[m], N[m], W[m], d_tr, nm)
        if np.isfinite(d_own[m]).sum() >= need:
            v, how = float(np.nanmedian(d_own[m])), "lidar this side"
        elif np.isfinite(d_opp[m]).sum() >= need:
            v, how = float(np.nanmedian(d_opp[m])), "lidar other side"
        elif ctx["ground"] is not None and (pv := kpw.side_width(ctx["ground"], P[m], N[m], float(np.nanmedian(W[m])) / 2)) is not None:
            v, how = pv, kpw.LAST
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
            DETAIL[comp.representative_point().wkt] = {"street": nm, "fh": int(ctx["st_fh"][cid]), "side_m": round(float(n * STEP), 1),
                "w_med": round(float(np.nanmedian(W[m])), 1), "at": [round(float(v), 1) for v in np.median(P[m], axis=0)]}
            return "no footpath measure", None
        v = min(v, float(np.nanmedian(W[m])) / 2 - (CW_OWN if how in OWN else CW_MIN))   # the reserve, not the centreline: centrelines are metres off here
        if v < D_MIN:
            DETAIL[comp.representative_point().wkt] = {"street": nm, "fh": int(ctx["st_fh"][cid]), "side_m": round(float(n * STEP), 1),
                "w_med": round(float(np.nanmedian(W[m])), 1), "measured": round(v + CW_MIN, 2) if how else None, "how": how}
            return "street too narrow for a footpath", None
        D[m] = v; used[str(nm) + ":" + str(int(cid))] = (round(v, 2), how)
    fill = np.isnan(D)
    if fill.all():
        return "no footpath measure", None
    D[fill] = np.interp(np.flatnonzero(fill), np.flatnonzero(~fill), D[~fill], period=len(D))
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
            if ctx["cad"] is not None and kc.tip_only(g, ring, [h for h, f2 in zip(SG, [ctx["st_fh"][i] for i in ext_st]) if f2 != LANE_FH]):
                continue   # a cul-de-sac's centreline runs a few metres past its kerb at the free end
            if CL_BAND and g.intersection(ring.buffer(CL_CLEAR)).within(comp.buffer(float(np.nanmax(D)) + CL_CLEAR)):
                continue   # an offset centreline inside the footpath band (inner city and older streets: metres off), not a street crossed
            DETAIL[comp.representative_point().wkt] = {"fh": int(fh), "in_m": round(g.intersection(ring.buffer(-0.5)).length, 1),
                "past_band_m": round(g.intersection(ring.buffer(CL_CLEAR)).difference(comp.buffer(float(np.nanmax(D)) + CL_CLEAR)).length, 1)}
            return "street centreline inside or too close", None
    for k in ctx["bld_t"].query(q):
        part = q.intersection(ctx["bld"][int(k)].buffer(-BLD_IN))
        if not part.is_empty and max(p.length for p in getattr(part, "geoms", [part])) > BLD_RUN:
            return "over a roof", None
    for L in ctx["lanes"]:
        if L.intersects(ring) and q.intersection(L.buffer(-0.3)).length > 3.0 and not L.within(comp.buffer(0.3)):
            return "along a lane", None
    if ctx["cad"] is not None:
        road = [g for g, fh in zip(ctx["st"], ctx["st_fh"]) if fh != LANE_FH and g.intersects(ring)]
        if kc.inlet(ring, road) > kc.INLET_D:
            DETAIL[comp.representative_point().wkt] = {"inlet_m": round(kc.inlet(ring, road), 1)}
            return "deep inlet (slot or notch, no street ends in it)", None
        if kc.doubles(q, others, STRtree(others)) > kc.DOUBLE_RUN:
            return "doubles a kerb already drawn", None
        w, m = kc.judge(ctx["cad"], q)
        if w:
            DETAIL[comp.representative_point().wkt] = {"run_m": m}
            return w, None
    if kerblane.bad(q, [g for g, fh in zip(ctx["st"], ctx["st_fh"]) if fh == LANE_FH and g.intersects(ring)]):
        return "ring across lane mouths", None
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
    lots_all, road_lots = drop_road_lots(lots_all, [g for g, fh, _ in ground if fh != LANE_FH])
    cad = kc.Cad(a[a.index("--cad") + 1], road_lots) if "--cad" in a else None
    LT = STRtree(lots_all)
    RW = [LineString(t) for t in ka.read_kerbs(a[2]) if len(t) > 1]
    DR = lines_ll(a[3], to)
    MS = lines_ll(a[a.index("--measure") + 1], to) if "--measure" in a else DR
    keep, why, cnt, done, sidel = [], [], {}, set(), []
    foot, prep = {}, []
    if "--foot-only" in a:
        pass
    for x, y in cells:
        cell = box(x * 1000, y * 1000, x * 1000 + 1000, y * 1000 + 1000)
        frame = cell.buffer(FRAME, join_style="mitre")
        lots = [lots_all[int(k)] for k in LT.query(frame)]
        land0, narrow = reserves(lots, frame)
        stg = [(g, fh, n) for g, fh, n in ground if g.intersects(frame)]
        lanes = []
        for p in narrow:
            inside = sum(g.intersection(p).length for g, fh, _ in stg if fh != LANE_FH and g.intersects(p))
            if not (long_side(p) > 15 and inside > STREET_LONG * long_side(p)) and not any(
                    fh == NARROW_ST and g.intersection(p).length > 10 for g, fh, _ in stg if g.intersects(p)):
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
        LB = [c.exterior for c in comps] + (cad.barriers(frame) if cad is not None else [])
        B = buildings(a[4], [(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1)], to)
        ctx = {"land_b": LB, "land_t": STRtree(LB), "st": [g for g, _, _ in stg], "st_name": [n for _, _, n in stg], "st_fh": [fh for _, fh, _ in stg], "foot": foot,
               "raw": raw, "raw_t": STRtree(raw), "drawn": dr, "drawn_t": STRtree(dr), "meas": ms, "meas_t": STRtree(ms), "bld": B, "bld_t": STRtree(B), "lanes": lanes, "cad": cad,
               "ground": kpw.Ground(a[a.index("--ground") + 1]) if "--ground" in a else None}
        for c in comps:
            rp = c.representative_point()
            if not cell.contains(rp) or not c.within(frame.buffer(-30)) or c.area < MIN_A:
                continue
            key = (round(rp.x, 1), round(rp.y, 1))
            if key in done:
                continue
            done.add(key)
            w, res = judge_block(c, ctx)
            if w == "side faces no street" and SIDES:
                for ln, info in kerbside.lines(c, SIDE, ctx, sys.modules[__name__]):
                    sidel.append((ln, info, f"{x}_{y}"))
            cnt[w or "kept"] = cnt.get(w or "kept", 0) + 1
            bid = f"L{x}{y}-{len(keep) + len(why)}"
            if w:
                why.append((w, Polygon(c.exterior), bid, f"{x}_{y}", DETAIL.pop(c.representative_point().wkt, None)))
            else:
                ring, used, seen, inside = res
                keep.append((ring, used, seen, bid, f"{x}_{y}", [[[round(v, 7) for v in back(*p)] for p in g.coords] for g in inside]))
        print(x, y, json.dumps(cnt), flush=True)
    ll = lambda g: [[round(v, 7) for v in back(*p)] for p in g.exterior.coords]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": b, "cell": n, "d": {str(k): v for k, v in u.items()},
               "lidar_seen": round(s, 2), "source": "lot front", "replaces": rp}, "geometry": {"type": "LineString", "coordinates": ll(r)}} for r, u, s, b, n, rp in keep]}, open(a[6], "w"))
    if SIDES:
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": f"S{i}", "cell": n, "side": True, "info": inf},
                   "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(*p)] for p in g.coords]}} for i, (g, inf, n) in enumerate(sidel)]},
                  open(a[a.index("--sides") + 1], "w"))
    if "--why" in a:
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"why": w, "id": b, "cell": n, "detail": dt},
                   "geometry": {"type": "LineString", "coordinates": ll(g)}} for w, g, b, n, dt in why]}, open(a[a.index("--why") + 1], "w"))
    if CALIB is not None:
        json.dump(CALIB, open(a[a.index("--calib") + 1], "w"))
    if "--nomeasure" in a:
        json.dump(NOMEASURE, open(a[a.index("--nomeasure") + 1], "w"))
    if SIDES:
        print("SIDES", dict(kerbside.STATS))
    print("RESULT", json.dumps({"count": cnt, "km": round(sum(k[0].exterior.length for k in keep) / 1000, 2)}))


if __name__ == "__main__":
    main(sys.argv[1:])
