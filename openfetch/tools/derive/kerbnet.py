"""Kerbs built top-down from the street layout, so every block is one closed kerb loop by construction (Jacky 7 Nov 2026: "figure
out the root cause, and a solution that can completely fill the missing gaps").

Root cause of open ends: kerbs were built bottom-up from photo-traced fragments and stitched together by rules (join, bridge,
corner, extend, turn, close); a fragment that fails every rule's limits stays open, so there is always a tail of gaps.

Here the street layout decides where kerbs ARE and the photo decides where exactly they sit:
  1. street centrelines (functionhierarchy 1-7; lanes in a reserve under 7 m left out; fh <= 5 never a lane) are noded and
     polygonised into faces; a face with property lots in it is a street block, and each block becomes one closed kerb loop:
     the face minus every edge's offset band (offset = nearest traced kerb along that edge on the block's side, else the other
     side, else frontage minus 3.5 m, else a default by road type), corners rounded, then moved onto the traced kerb (fuse);
  2. the output keeps every traced kerb exactly as seen, adds the loop parts where nothing was traced (fill), and carries every
     kerb end left open on to the next kerb: straight on when the same kerb carries on ahead, else along its block's loop
     (guide). Nothing added crosses or touches a street centreline, runs along a bridge or tunnel (roadontype 2, 3: barriers,
     not kerbs; Jacky 7 Nov 2026), doubles a traced kerb, or turns sharper than SMOOTH_TURN per SMOOTH_STEP (no spikes, Vs).

    python3 kerbnet.py traced.json(lon/lat) lots_dir roads_dir out.json [--box x0 y0 x1 y1] [--traced-only-area] [--loops]
        [--keep-motorway] [--lot-guide]   (motorway stretches are taken out unless --keep-motorway; --lot-guide is a tested-off option)

Default output: traced kerbs + loop parts that fill their gaps (fill()); --loops writes the fused block loops instead.
"""
import json
import sys

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, box
from shapely.ops import polygonize, unary_union, substring
from shapely.prepared import prep
from shapely.strtree import STRtree

import kerbaudit as ka
import kerbregular as kr

R_BY_RANK = {1: 9.0, 2: 6.0, 3: 4.0}   # m, corner radius by the busiest road at the block
W_DEFAULT = {1: 9.0, 2: 6.5, 3: 4.5}   # m, centreline to kerb when nothing was measured
BAND = 25.0        # m, traced kerb this close to an edge (inside the block) measures that edge
PAR = np.cos(np.radians(20))
ROAD_GAP = 20.0    # m, a street end this near another street (ahead) is a gap in the road data
GUIDE_REACH, GUIDE_START, GUIDE_MAX = 10.0, 3.0, 60.0  # m: an open end this near a block loop is walked along it
GUIDE_TAPER = 10.0  # m, the end (and the kerb it reaches) blend onto the loop over this length
SMOOTH_TURN, SMOOTH_STEP = 50.0, 2.0  # deg per m: a join turning faster than this is a spike, not a kerb
CORE_MIN_W = 5.0   # m, mean width (2 x area / perimeter) under which a block core is a sliver
GUIDE_CUTS = (0.0, 4.0, 8.0)  # m, a join that spikes is tried again from this far back along the traced end
LINE_MAX, LINE_LAT, LINE_ANG = 80.0, 1.5, 10.0  # m, m, deg: the same kerb carrying on straight ahead is joined
FOLLOW, MERGE_ANG = 10.0, 25.0  # m, deg: a join may end mid-kerb only on a kerb the loop follows on, entering within 25 deg
INSIDE, BESIDE = 2.7, 3.7   # m, kerbreview.py's inside / beside distances plus a margin
JOIN_RUN = 12.0    # m, the end of a join running into a kerb may lie close beside it
SOFT_SIGMA = 1.5   # m, final smoothing of every line (soften)
CROSSOVER = 15.0   # m, a fill shorter than this from the middle of one kerb to the middle of another is a crossover
DEAD_CLEAR = 30.0  # m, a dangling centreline end this near another road is a data gap, not a dead end
DUP = 2.5          # m, a traced piece this close to a block kerb is that kerb
TWIN = 6.0         # m, a fill this close beside a parallel traced kerb would double it
T_END = 3.0        # m, this near a kerb's end counts as meeting it end-on
FILL_MIN = 4.0     # m, shorter gaps between traced kerb and the block loop are left to the weld
KEEP_MIN = 8.0     # m, shorter leftovers of traced kerb are noise


def tangent(g, t):
    a = np.asarray(g.interpolate(max(t - 1.5, 0)).coords[0]); b = np.asarray(g.interpolate(min(t + 1.5, g.length)).coords[0])
    d = b - a; n = np.hypot(*d)
    return d / n if n > 1e-9 else np.array([1.0, 0.0])


FUSE = 3.0         # m, a traced kerb this close across the loop (and parallel) is where the kerb really is


def fuse(loop, T, tt, stats):
    """The block's kerb loop moved onto the traced kerb wherever the photo saw it (within FUSE m, parallel); between seen parts
    the shift is interpolated along the loop, so the drawn parts meet the seen ones without a step. Stays one closed loop."""
    g = LineString(loop)
    if tt is None or g.length < 10:
        return loop
    n_s = max(int(g.length // 1.0), 8)
    s = np.linspace(0, g.length, n_s, endpoint=False)
    P = np.array([g.interpolate(x).coords[0] for x in s])
    tg = np.array([tangent(g, x) for x in s]); N = np.c_[-tg[:, 1], tg[:, 0]]
    c = np.full(len(s), np.nan)
    for i in range(len(s)):
        ray = LineString([P[i] - N[i] * FUSE, P[i] + N[i] * FUSE])
        best = None
        for k in tt.query(ray, predicate="intersects"):
            x = ray.intersection(T[int(k)])
            for q in getattr(x, "geoms", [x]):
                if q.geom_type != "Point":
                    continue
                gk = T[int(k)]
                if abs(tangent(gk, gk.project(q)) @ tg[i]) < PAR:
                    continue
                d = float((np.asarray(q.coords[0]) - P[i]) @ N[i])
                if best is None or abs(d) < abs(best):
                    best = d
        if best is not None:
            c[i] = best
    seen = ~np.isnan(c)
    stats["fuse_seen_m"] = stats.get("fuse_seen_m", 0) + int(seen.sum()); stats["fuse_all_m"] = stats.get("fuse_all_m", 0) + len(s)
    if not seen.any():
        return loop
    # a lone seen point or two is noise; then interpolate round the loop and smooth
    idx = np.where(seen)[0]
    x = np.r_[idx - len(s), idx, idx + len(s)]; y = np.r_[c[idx], c[idx], c[idx]]
    cc = np.interp(np.arange(len(s)), x, y)
    k = 7
    pad = np.r_[cc[-k:], cc, cc[:k]]
    cc = np.array([np.median(pad[i:i + 2 * k + 1]) for i in range(len(s))])
    pad = np.r_[cc[-k:], cc, cc[:k]]
    cc = np.convolve(pad, np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    Q = P + N * cc[:, None]
    return np.vstack([Q, Q[:1]])


NET = []   # the street centrelines a joining kerb may not cross: the block network plus streets left out only for lying in lots
BARRIER = []


def close_gaps(streets, stats):
    """A street that stops short of another (a gap in the road data, not a dead end) is carried on to it, so the blocks either
    side become separate faces: an end with no other street at it but one within ROAD_GAP m ahead (within 45 deg of its heading)."""
    G = [g for g, _ in streets]; st = STRtree(G); out = []
    for i, (g, fh) in enumerate(streets):
        c = np.asarray(g.coords)
        for j in (0, -1):
            e = Point(c[j]); k = [int(x) for x in st.query(e.buffer(ROAD_GAP)) if int(x) != i]
            if any(G[x].distance(e) < 0.5 for x in k) or not k:
                continue
            d = c[j] - c[1 if j == 0 else -2]; d = d / (np.hypot(*d) or 1)
            best = None
            for x in k:
                q = np.asarray(G[x].interpolate(G[x].project(e)).coords[0]); v = q - c[j]; n = np.hypot(*v)
                if n <= ROAD_GAP and (n < 1e-6 or v @ d / n > np.cos(np.radians(45))) and (best is None or n < best[0]):
                    best = (n, q)
            if best is not None:
                c = np.vstack([best[1], c]) if j == 0 else np.vstack([c, best[1]])
                stats["road_gap_closed"] = stats.get("road_gap_closed", 0) + 1
        out.append((LineString(c), fh))
    return out


LOT_GUIDE = False   # --lot-guide: block loops follow the lot fronts (road reserve edge) moved out by the street's verge.
# Tested 7 Nov 2026 (thread "Guide kerbs with property boundaries"), OFF by default: Parramatta box found 69.7 -> 68.1, precise
# 82.8 -> 82.1, open ends 137 -> 201; lot-front loops alone precise 75.8 vs centreline loops 79.3. The cadastre sits up to ~5 m
# off the aerial in places (333028 6244986: south lot fronts lie in the carriageway), and the traced kerbs already hug the lots
# (0.4 % of traced points fall inside a house lot), so drift there comes FROM following the lots; lots cannot correct it.
VERGE_DEFAULT = {1: 4.5, 2: 4.0, 3: 3.8}   # m, lot front to kerb when no traced kerb measured it (Parramatta council median 4.1)
VERGE_RANGE = (1.5, 7.5)   # m, a measured verge outside this is not a footpath strip (a median, a car park, a path)
RESERVE_MAX = {1: 30.0, 2: 18.0, 3: 13.0}   # m, centreline to lot front beyond which the lots do not show where the kerb is
CL_CLEAR = 2.8     # m, a lot-guided kerb stays at least this far from its street's centreline (half a lane)


def lot_bands(f, edge_ids, pieces, rank, house, ht, T, tt, stats):
    """Jacky 7 Nov 2026: "property boundary is going to be very helpful ... especially for resi suburbs". For each street edge of a
    block whose lot fronts sit a normal distance from the centreline, the kerb is the lot front moved out into the road reserve by
    that street side's verge (measured from the traced kerb against the lot front, else a default by road type). Returns bands
    (the region between the centreline and that kerb, per edge) and the edges done; other edges keep the centreline offset."""
    if ht is None:
        return [], set()
    hs = [house[int(k)] for k in ht.query(f, predicate="intersects")]
    hs = [h.intersection(f) for h in hs if h.intersection(f).area > 0.5 * h.area]
    if not hs:
        return [], set()
    L = unary_union([h.buffer(0.2, join_style="mitre") for h in hs]).buffer(-0.2, join_style="mitre")
    if L.is_empty:
        return [], set()
    Lb = L.boundary
    bands, done = [], set()
    for k in edge_ids:
        pc = pieces[k]
        if pc.length < 4:
            continue
        # centreline to lot front along the edge, on the block's side
        fr = []
        inside = f.buffer(-0.5)
        for s_ in np.arange(1.0, pc.length - 1.0, 3.0) if pc.length > 3 else [pc.length / 2]:
            c = np.asarray(pc.interpolate(s_).coords[0]); tg = tangent(pc, s_); n = np.array([-tg[1], tg[0]])
            for sg in (1, -1):
                if not inside.contains(Point(c + n * sg * 1.0)):
                    continue
                ray = LineString([c, c + n * sg * 40])
                x = ray.intersection(L)
                if not x.is_empty:
                    fr.append(Point(c).distance(x))
        rk = rank[k]
        if len(fr) < max(2, 0.6 * pc.length / 3.0) or np.median(fr) > RESERVE_MAX[rk] or np.median(fr) < CL_CLEAR + VERGE_RANGE[0]:
            stats["lot_edge_skip"] = stats.get("lot_edge_skip", 0) + 1
            continue
        D = float(np.percentile(fr, 90))
        zone = pc.buffer(D + 1.0).intersection(f)
        # verge: traced kerb (parallel to the edge, between centreline and lot front) to the lot front
        vs = []
        if tt is not None:
            for q in tt.query(zone):
                g = T[int(q)]
                part = g.intersection(zone)
                for seg in getattr(part, "geoms", [part]):
                    if seg.geom_type != "LineString" or seg.length < 3:
                        continue
                    for t_ in np.arange(0.5, seg.length, 2.0):
                        p = seg.interpolate(t_)
                        if abs(tangent(seg, t_) @ tangent(pc, pc.project(p))) < PAR:
                            continue
                        dl = L.distance(p)
                        if L.contains(p) or not (VERGE_RANGE[0] <= dl <= VERGE_RANGE[1]):
                            continue
                        if pc.distance(p) < CL_CLEAR:
                            continue
                        vs.append(dl)
        if len(vs) >= 4:
            v = float(np.median(vs)); src = "lot traced"
        else:
            v = VERGE_DEFAULT[rk]; src = "lot default"
        v = min(v, max(VERGE_RANGE[0], float(np.median(fr)) - CL_CLEAR))
        stats["edge_" + src] = stats.get("edge_" + src, 0) + 1
        kerb_side = L.buffer(v, join_style="round", quad_segs=8)
        band = zone.difference(kerb_side).union(pc.buffer(CL_CLEAR, cap_style="flat"))
        bands.append(band); done.add(k)
    return bands, done


DRIFT_DEV, DRIFT_RUN = 1.5, 8.0   # m: a traced kerb this far off its street side's usual verge for this long has drifted
DRIFT_MIN_VERGE, DRIFT_MIN_CL = 1.2, 2.3   # m: a local street kerb is never this close to the lot front / its centreline
DRIFT_NODE = 15.0                 # m, near a street junction the verge changes (corner splays, blisters): not judged there
DRIFT_FH = (4, 5, 6, 7)           # streets judged; main roads have medians, bus bays and service lanes the lots do not show


def lot_drift(traced, lots, roads, stats, area=None):
    """Traced kerb that has drifted (Jacky 7 Nov 2026 via the reviewer: lines 3 m onto the footpath or into the road): on a street
    with house lots along it, the kerb sits the same distance in front of the lot fronts all along one side (Parramatta council
    kerbs: 80 % within 1 m of their street side's median, mid-block). A traced stretch of DRIFT_RUN m or more that is more than
    DRIFT_DEV m off that side's median verge is cut out; the lot-guided block loop then fills it."""
    streets = [(g, fh) for g, fh in roads if fh not in ka.SKIP_FH]
    if area is not None:
        a3 = prep(area.buffer(300)); streets = [(g, fh) for g, fh in streets if a3.intersects(g)]
        lots = [l for l in lots if a3.intersects(l)]
    G = [g for g, _ in streets]; st = STRtree(G)
    house = [l for l in lots if not any(G[int(k)].intersects(l.buffer(-0.5)) for k in st.query(l))]
    if not house:
        return traced
    ht = STRtree(house)
    ends = [Point(c) for g in G for c in (g.coords[0], g.coords[-1])]; et = STRtree(ends)
    samples = []   # (line index, station, group key, verge)
    T = [LineString(t) for t in traced]
    for i, g in enumerate(T):
        if g.length < DRIFT_RUN:
            continue
        for t in np.arange(0.5, g.length, 1.0):
            p = g.interpolate(t)
            j = st.nearest(p); cl, fh = streets[int(j)]
            if fh not in DRIFT_FH:
                continue
            tp = cl.project(p)
            if any(ends[int(q)].distance(p) < DRIFT_NODE for q in et.query(p.buffer(DRIFT_NODE))):
                continue
            q = np.asarray(cl.interpolate(tp).coords[0]); tg = tangent(cl, tp); n = np.array([-tg[1], tg[0]])
            v = np.asarray(p.coords[0]) - q; side = 1 if v @ n > 0 else -1
            if abs(tangent(g, t) @ tg) < PAR:
                continue
            # the lot front straight out from the centreline through this point, on this side
            ray = LineString([q, q + n * side * 40])
            hit = None
            for k in ht.query(ray, predicate="intersects"):
                x = ray.intersection(house[int(k)])
                if not x.is_empty:
                    d = Point(q).distance(x)
                    hit = d if hit is None else min(hit, d)
            if hit is None:
                continue
            dc = float(abs(v @ n))
            if dc > hit + 1.0:
                continue   # beyond the lot front: not this street's kerb
            samples.append((i, t, (int(j), side, int(tp // 60)), hit - dc, dc))
    groups = {}
    for i, t, k, v, dc in samples:
        if VERGE_RANGE[0] <= v <= VERGE_RANGE[1]:
            groups.setdefault(k, []).append(v)
    med = {k: float(np.median(v)) for k, v in groups.items() if len(v) >= 12}
    bad = {}
    for i, t, k, v, dc in samples:
        # on the lot front or a fence line (no footpath strip), within half a lane of the centreline, or off the side's usual verge
        if v < DRIFT_MIN_VERGE or dc < DRIFT_MIN_CL or (k in med and abs(v - med[k]) > DRIFT_DEV):
            bad.setdefault(i, []).append(t)
    out = []
    cut = 0
    for i, g in enumerate(T):
        ts = sorted(bad.get(i, []))
        runs, a0, prev = [], None, None
        for t in ts:
            if a0 is None:
                a0 = prev = t
            elif t - prev <= 2.5:
                prev = t
            else:
                runs.append((a0, prev)); a0 = prev = t
        if a0 is not None:
            runs.append((a0, prev))
        runs = [(a, b) for a, b in runs if b - a >= DRIFT_RUN]
        if not runs:
            out.append(traced[i]); continue
        pos = 0.0
        for a, b in runs:
            if a - 1.0 - pos > KEEP_MIN:
                out.append(np.asarray(substring(g, pos, a - 1.0).coords))
            pos = b + 1.0; cut += b - a + 2.0
        if g.length - pos > KEEP_MIN:
            out.append(np.asarray(substring(g, pos, g.length).coords))
    stats["drift_cut_m"] = int(cut); stats["drift_groups"] = len(med)
    return out


def no_motorway(out, roads, stats):
    """Motorways and their ramps (functionhierarchy 1) have barriers and edge lines, not kerbs (Jacky 7 Nov 2026: "some are highway
    not kerb"; reviewer d tiles 12, 13, 15: lines on a freeway bridge deck, a ramp nose, a freeway median). Any stretch of a line
    whose nearest street is a motorway is taken out; leftovers shorter than KEEP_MIN go."""
    streets = [(g, fh) for g, fh in roads if fh not in ka.SKIP_FH]
    if not any(fh == 1 for _, fh in streets):
        return out
    st = STRtree([g for g, _ in streets]); res = []; cut = 0.0
    for o in out:
        g = LineString(o)
        if not any(streets[int(k)][1] == 1 for k in st.query(g.buffer(40))):
            res.append(o); continue
        n = max(2, int(g.length // 1.0) + 1); ts = np.linspace(0, g.length, n)
        mw = np.array([streets[int(st.nearest(g.interpolate(t)))][1] == 1 for t in ts])
        if not mw.any():
            res.append(o); continue
        i = 0
        while i < n:
            j = i
            while j + 1 < n and mw[j + 1] == mw[i]:
                j += 1
            a, b = ts[i], ts[j]
            if mw[i]:
                cut += b - a
            elif b - a >= KEEP_MIN:
                res.append(np.asarray(substring(g, a, b).coords) if (a > 0 or b < g.length) else o)
            i = j + 1
    stats["motorway_cut_m"] = int(cut)
    return res


def build(traced, lots, roads, area=None, stats=None):
    """traced: list of Nx2 arrays (7856); lots: polygons; roads: [(LineString, fh)]. Returns list of Nx2 kerb lines."""
    stats = stats if stats is not None else {}
    streets = [(g, fh) for g, fh in roads if fh not in ka.SKIP_FH]
    if area is not None:
        a300 = prep(area.buffer(300)); a50 = prep(area.buffer(50)); ap = prep(area)
        streets = [(g, fh) for g, fh in streets if a300.intersects(g)]
    # lanes and walkways between houses are not kerbed streets: a centreline mostly inside lots, or in a reserve under 7 m
    lt0 = STRtree(lots); BARRIER.clear()
    keep = []
    for g, fh in streets:
        if fh <= 5:
            keep.append((g, fh)); continue   # arterial to distributor roads are never lanes (some cross plaza or rail lots)
        inlot = sum(lots[int(k)].intersection(g).length for k in lt0.query(g, predicate="intersects"))
        if inlot > 0.3 * g.length:
            stats["net_lane_inlot"] = stats.get("net_lane_inlot", 0) + 1; BARRIER.append(g); continue
        wid = []
        for t in np.arange(2.0, g.length, 8.0):
            c = np.asarray(g.interpolate(t).coords[0]); tg = tangent(g, t); n = np.array([-tg[1], tg[0]]); d = []
            for sg in (1, -1):
                ray = LineString([c, c + n * sg * 20])
                hs = [lots[int(k)].distance(Point(c)) for k in lt0.query(ray, predicate="intersects")]
                d.append(min(hs) if hs else 20.0)
            wid.append(sum(d))
        if wid and np.median(wid) < 7.0:
            stats["net_lane_narrow"] = stats.get("net_lane_narrow", 0) + 1; continue
        keep.append((g, fh))
    streets = close_gaps(keep, stats)
    NET[:] = [g for g, _ in streets] + BARRIER
    # node the network; remember each noded piece's road rank
    noded = unary_union([g for g, _ in streets])
    pieces = list(getattr(noded, "geoms", [noded]))
    st = STRtree([g for g, _ in streets])
    rank = []
    for p in pieces:
        m = p.interpolate(0.5, normalized=True)
        k = min(st.query(m.buffer(0.5)), key=lambda k: streets[int(k)][0].distance(m), default=None)
        rank.append(ka.road_rank(streets[int(k)][1]) if k is not None else 3)
    pt = STRtree(pieces)
    deg = {}
    for p in pieces:
        for e in (p.coords[0], p.coords[-1]):
            key = (round(e[0], 2), round(e[1], 2)); deg[key] = deg.get(key, 0) + 1
    faces = [f for f in polygonize(pieces) if f.area > 150]
    lt = STRtree(lots)
    # house lots (no street centreline runs through them): their street fronts are where the road reserve ends
    house = [l for l in lots if not any(g.intersects(l.buffer(-0.5)) for g in (pieces[int(k)] for k in pt.query(l)))]
    ht = STRtree(house) if house else None
    T = [LineString(t) for t in traced if len(t) > 1]
    tt = STRtree(T) if T else None

    def offset_on(piece, inside, side_pt_ok):
        """Median offset of traced kerb points along `piece`, on the side where `inside` contains them."""
        if tt is None:
            return None
        offs = []
        L = piece.length
        for s in np.arange(1.0, L - 1.0, 2.0) if L > 3 else [L / 2]:
            c = np.asarray(piece.interpolate(s).coords[0]); tg = tangent(piece, s); n = np.array([-tg[1], tg[0]])
            for sg in (1, -1):
                ray = LineString([c + n * sg * 1.5, c + n * sg * BAND])
                if not side_pt_ok(Point(c + n * sg * 3)):
                    continue
                best = None
                for k in tt.query(ray, predicate="intersects"):
                    x = ray.intersection(T[int(k)])
                    for q in getattr(x, "geoms", [x]):
                        if q.geom_type != "Point":
                            continue
                        gk = T[int(k)]; tk = gk.project(q)
                        dk = tangent(gk, tk)
                        if abs(dk @ tg) < PAR:
                            continue
                        d = Point(c).distance(q)
                        # the nearest kerb on the block's side wins (a divided road's median lies in its own face, not here;
                        # farther lines are paths and garden edges)
                        if best is None or d < best:
                            best = d
                if best is not None:
                    offs.append(best)
        return float(np.median(offs)) if len(offs) >= 3 else None

    # offsets per (piece, side): measured from traced kerbs inside each face
    out, blocks = [], 0
    meas = {}
    for f in faces:
        if area is not None and not ap.intersects(f):
            continue
        lot_hits = [lots[int(k)] for k in lt.query(f, predicate="intersects")]
        lot_area = sum(l.intersection(f).area for l in lot_hits)
        if lot_area < 0.25 * f.area:
            continue  # no properties: a median, a park strip or a rail corridor, not a street block
        blocks += 1
        inside = f.buffer(-0.5)
        edge_ids = [int(k) for k in pt.query(f.buffer(0.3)) if pieces[int(k)].within(f.buffer(0.3))]
        bands = []
        lot_done = set()
        if LOT_GUIDE:
            bands, lot_done = lot_bands(f, edge_ids, pieces, rank, house, ht, T, tt, stats)
        for k in edge_ids:
            if k in lot_done:
                meas[("other", k)] = meas.get(("other", k), 4.5)
                continue
            pc = pieces[k]
            w = offset_on(pc, inside, inside.contains)
            src = "traced"
            if w is None:
                w = meas.get(("other", k))
                src = "other side"
            if w is None:
                # frontage: lots of this block along the edge, minus the block's verge (kerb to lot) measured elsewhere
                fr = []
                for s in np.arange(2.0, pc.length - 2.0, 4.0):
                    c = np.asarray(pc.interpolate(s).coords[0]); tg = tangent(pc, s); n = np.array([-tg[1], tg[0]])
                    for sg in (1, -1):
                        if not inside.contains(Point(c + n * sg * 2)):
                            continue
                        ray = LineString([c, c + n * sg * 30])
                        hs = [lots[int(q)].distance(Point(c)) for q in lt.query(ray, predicate="intersects")]
                        if hs:
                            fr.append(min(hs))
                if len(fr) >= 3:
                    w = max(2.5, float(np.median(fr)) - 3.5); src = "frontage"
            if w is None:
                w = W_DEFAULT[rank[k]]; src = "default"
            stats["edge_" + src] = stats.get("edge_" + src, 0) + 1
            meas[("other", k)] = meas.get(("other", k), w)
            bands.append(pc.buffer(w, cap_style="flat", join_style="mitre"))
            for e in (Point(pc.coords[0]), Point(pc.coords[-1])):
                # a disc at every node; at a dangling end only when it is a real dead end, not a centreline that stops short of
                # another road (a gap in the road data: the disc would cut a round hole across that road)
                if deg[(round(e.x, 2), round(e.y, 2))] == 1 and any(
                        pieces[int(j)].distance(e) < DEAD_CLEAR for j in pt.query(e.buffer(DEAD_CLEAR)) if int(j) != k):
                    stats["dangling_no_disc"] = stats.get("dangling_no_disc", 0) + 1; continue
                bands.append(e.buffer(w, quad_segs=8))
        if not bands:
            continue
        core = f.difference(unary_union(bands))
        r = R_BY_RANK[min(rank[k] for k in edge_ids)] if edge_ids else 6.0
        for poly in getattr(core, "geoms", [core]):
            if poly.geom_type != "Polygon" or poly.area < 30:
                continue
            if 2 * poly.area / poly.length < CORE_MIN_W:
                stats["core_thin"] = stats.get("core_thin", 0) + 1; continue  # a strip between carriageways, not a block
            if sum(l.intersection(poly).area for l in lot_hits) < 0.25 * poly.area:
                stats["core_no_lots"] = stats.get("core_no_lots", 0) + 1; continue  # a sliver of the face with no property in it
            rr = r
            sm = poly.buffer(-rr, join_style="round").buffer(rr, join_style="round")
            while (sm.is_empty or sm.area < 0.7 * poly.area) and rr > 1.5:
                rr /= 2; sm = poly.buffer(-rr, join_style="round").buffer(rr, join_style="round")
            if sm.is_empty:
                sm = poly
            for pp in getattr(sm, "geoms", [sm]):
                if pp.geom_type == "Polygon":
                    out.append(fuse(np.asarray(pp.exterior.coords), T, tt, stats))
    stats["blocks"] = blocks
    # traced kerb that is not part of any block kerb (lane kerbs, median islands, build-outs) is kept, part by part: the stretch
    # of a traced line more than DUP m from every block loop, at least KEEP_MIN m long, its ends snapped onto the loop it meets
    if out and T:
        BK = [LineString(o) for o in out]; bt = STRtree(BK)
        kept = 0
        for g in T:
            if area is not None and not a50.intersects(g):
                continue
            near = [BK[int(k)] for k in bt.query(g.buffer(DUP))]
            rest = g.difference(unary_union([b.buffer(DUP, quad_segs=4) for b in near])) if near else g
            for q in getattr(rest, "geoms", [rest]):
                if q.geom_type != "LineString" or q.length < KEEP_MIN:
                    continue
                c = np.asarray(q.coords)
                for j in (0, -1):
                    e = Point(c[j]); bs = [b for b in near if b.distance(e) <= DUP + 0.6]
                    if bs:
                        b = min(bs, key=lambda b: b.distance(e)); s0 = np.asarray(b.interpolate(b.project(e)).coords[0])
                        c = np.vstack([s0, c]) if j == 0 else np.vstack([c, s0])
                out.append(c); kept += 1
        stats["traced_kept"] = kept
    return out


def tangent_smooth(c, h0=None, h1=None, it=3):
    """Chaikin-smoothed line through c with its ends kept: it leaves c[0] along h0 and enters c[-1] along h1 (unit vectors),
    so a join flows out of one kerb and into the next without a corner (Jacky 7 Nov 2026: "smooth that out")."""
    c = np.asarray(c, dtype=float)
    L = LineString(c).length
    if L < 1.0 or len(c) < 2:
        return c
    k = min(3.0, L / 3)
    pts = [c[0]] + ([c[0] + h0 * k] if h0 is not None else []) + list(c[1:-1]) + ([c[-1] - h1 * k] if h1 is not None else []) + [c[-1]]
    P = np.asarray(pts)
    for _ in range(it):
        Q = [P[0]]
        for a, b in zip(P[:-1], P[1:]):
            Q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        Q.append(P[-1]); P = np.asarray(Q)
    return P


def smooth(c, head=None, lim=SMOOTH_TURN):
    """True when line c never turns more than lim degrees within SMOOTH_STEP m (resampled), counting the heading it leaves
    the kerb it starts from (head, a unit vector), so a join is a curve and not a spike, V or wedge."""
    g = LineString(c)
    if g.length < 1.0:
        return True
    n = max(int(g.length // SMOOTH_STEP), 1)
    P = np.array([g.interpolate(x).coords[0] for x in np.linspace(0, g.length, n + 1)])
    D = np.diff(P, axis=0); D = D / np.maximum(np.hypot(D[:, 0], D[:, 1]), 1e-9)[:, None]
    if head is not None:
        D = np.vstack([head, D])
    return bool(len(D) < 2 or (np.sum(D[1:] * D[:-1], axis=1) >= np.cos(np.radians(lim))).all())


BRIDGES = []   # street centrelines on a bridge or in a tunnel (roadontype 2, 3): their edges are barriers, not kerbs


def along_bridge(c, streets_tree, streets):
    """Share of line c whose nearest street (within 25 m) is a bridge or tunnel."""
    if not BRIDGES:
        return 0.0
    g = LineString(c); bt = STRtree(BRIDGES) if not hasattr(along_bridge, "t") or along_bridge.n != len(BRIDGES) else along_bridge.t
    along_bridge.t, along_bridge.n = bt, len(BRIDGES)
    hit = tot = 0
    for x in np.arange(0.5, max(g.length, 1.0), 2.0):
        p = g.interpolate(x); tot += 1
        db = BRIDGES[int(bt.nearest(p))].distance(p)
        if db < 25 and (streets_tree is None or db <= streets[int(streets_tree.nearest(p))].distance(p) + 0.01):
            hit += 1
    return hit / max(tot, 1)


def twin_share(q, near, reach=TWIN):
    """Share of line q with a parallel traced kerb within reach m beside it (perpendicular rays, so a kerb carrying on ahead
    along the same line does not count)."""
    if not near or q.length < 1:
        return 0.0
    hit = tot = 0
    for t in np.arange(0.5, q.length, 1.0):
        c = np.asarray(q.interpolate(t).coords[0]); tg = tangent(q, t); n = np.array([-tg[1], tg[0]]); tot += 1
        ray = LineString([c - n * reach, c + n * reach])
        for g in near:
            x = ray.intersection(g)
            if any(abs(tangent(g, g.project(p)) @ tg) >= PAR for p in getattr(x, "geoms", [x]) if p.geom_type == "Point"):
                hit += 1; break
    return hit / max(tot, 1)



def crosses_mid(t, w, tol=1.0):
    """True when kerb t crosses the added line w away from w's two ends: a join that grazes the kerb it ends on (or the end it
    starts from) while curving in is fine; one that cuts through a kerb on the way (the V at tile 2) is not."""
    if not t.crosses(w):
        return False
    x = t.intersection(w); a, b = Point(w.coords[0]), Point(w.coords[-1])
    pts = [x] if x.geom_type == "Point" else [g for g in getattr(x, "geoms", [x])]
    return any(min(g.distance(a), g.distance(b)) > tol for g in pts)


def untangle(T, stats=None, self_near=2.5, other_near=1.2, gap=8.0, tail=12.0):
    """Traced kerbs as a person would draw them (Jacky 7 Nov 2026: "some have parallel line, some have intersection, some have kerb
    within a kerb"): stitching photo pieces left lines that fold back alongside themselves, cross themselves at corners, run a
    second strand inside another kerb, or poke a short tail through the kerb they meet. A kerb never does any of that, so:
    - a stretch of a line within self_near m of an earlier stretch of the same line (more than gap m back along it) is a fold-back
      and goes; a stretch within other_near m of a longer kerb, heading the same way, is a strand inside that kerb and goes
      (medians and islands, 1 m apart or more, stay);
    - where two kerbs cross, the side of either one that ends within tail m of the crossing is cut at the crossing;
    leftovers shorter than KEEP_MIN m go."""
    stats = stats if stats is not None else {}
    G = [LineString(c) for c in T if len(c) > 1]
    G = [g for g in G if g.length > 0]
    order = sorted(range(len(G)), key=lambda i: -G[i].length)
    tree = STRtree(G); keep = []; kept = set(); cuts = []; CUT = {}
    for i in order:
        g = G[i]; L = g.length; closed = g.coords[0] == g.coords[-1] or Point(g.coords[0]).distance(Point(g.coords[-1])) < 0.5
        ts = np.arange(0.5, L, 1.0)
        if len(ts) < 2:
            continue
        P = np.array([g.interpolate(t).coords[0] for t in ts])
        bad = np.zeros(len(ts), bool)
        # fold-backs: near an earlier part of itself
        from scipy.spatial import cKDTree
        for a_, b_ in cKDTree(P).query_pairs(self_near):
            d_ = abs(ts[a_] - ts[b_]); d_ = min(d_, L - d_) if closed else d_
            if d_ > gap:
                bad[max(a_, b_)] = True
        # strands inside a longer kerb already kept
        for k in [int(x) for x in tree.query(g.buffer(other_near))]:
            if k == i or k not in kept:
                continue
            h = G[k]
            # a join that runs into this kerb at its end is meant to merge with it: its last JOIN_RUN m are not a strand
            t_s = h.distance(Point(g.coords[0])) <= 1.0; t_e = h.distance(Point(g.coords[-1])) <= 1.0
            for n, (t, q) in enumerate(zip(ts, P)):
                if bad[n] or h.distance(Point(q)) >= other_near:
                    continue
                if (t_s and t < JOIN_RUN) or (t_e and L - t < JOIN_RUN):
                    continue
                if abs(tangent(g, t) @ tangent(h, h.project(Point(q)))) >= PAR:
                    bad[n] = True
        if bad.any():
            stats["untangle_m"] = stats.get("untangle_m", 0) + int(bad.sum())
            runs = []; st = None
            for n in range(len(ts)):
                if not bad[n] and st is None:
                    st = n
                if (bad[n] or n == len(ts) - 1) and st is not None:
                    e = n if not bad[n] else n - 1
                    a0 = 0.0 if st == 0 else ts[st] - 0.5; a1 = L if e == len(ts) - 1 else ts[e] + 0.5
                    if a1 - a0 >= KEEP_MIN:
                        runs.append(substring(g, a0, a1)); cuts.append((a0 > 0, a1 < L))
                    st = None
            for r, cu in zip(runs, cuts[-len(runs):] if runs else []):
                G.append(r); keep.append(len(G) - 1); CUT[len(G) - 1] = cu
        else:
            keep.append(i)
        kept.add(i)
    out = [G[i] for i in keep]
    # a cut end lies on the strand that was taken out, beside the kerb (or the part of itself) it doubled: it carries on into
    # that kerb, so the cut leaves a merge, not a new open end
    ct = STRtree(out)
    for n, i in enumerate(keep):
        if i not in CUT:
            continue
        c = np.asarray(out[n].coords)
        for j, was_cut in ((0, CUT[i][0]), (-1, CUT[i][1])):
            if not was_cut:
                continue
            e = Point(c[j])
            cand = [int(x) for x in ct.query(e.buffer(self_near + 0.5))]
            cand = [k for k in cand if (k != n and out[k].distance(e) <= max(self_near, other_near) + 0.5)]
            if not cand:
                continue
            k = min(cand, key=lambda k: out[k].distance(e)); q = np.asarray(out[k].interpolate(out[k].project(e)).coords[0])
            if np.hypot(*(q - c[j])) > 0.05:
                c = np.vstack([q, c]) if j == 0 else np.vstack([c, q])
                stats["untangle_rejoined"] = stats.get("untangle_rejoined", 0) + 1
        out[n] = LineString(c)
    # tails poking through a kerb they meet
    tr = STRtree(out); changed = True; rounds = 0
    while changed and rounds < 3:
        changed = False; rounds += 1
        for i in range(len(out)):
            g = out[i]
            for k in [int(x) for x in tr.query(g)]:
                if k == i or not out[k].crosses(g):
                    continue
                x = out[k].intersection(g)
                for q in [x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]:
                    t = g.project(q)
                    if 0.3 < t < tail and g.length - t > KEEP_MIN:
                        g = substring(g, t, g.length); changed = True; stats["untangle_tail"] = stats.get("untangle_tail", 0) + 1
                    elif 0.3 < g.length - t < tail and t > KEEP_MIN:
                        g = substring(g, 0, t); changed = True; stats["untangle_tail"] = stats.get("untangle_tail", 0) + 1
            out[i] = g
        tr = STRtree(out)
    return [np.asarray(g.coords) for g in out if g.length >= KEEP_MIN]


def fill(traced, loops, streets=(), area=None, stats=None):
    """The traced kerbs kept exactly as seen, plus the parts of each block loop where nothing was traced (more than DUP m from
    every traced kerb), each at least FILL_MIN m long and with its ends snapped onto the traced kerb it meets: the photo stays
    the kerb wherever it saw one, and the street layout fills every gap, so each block closes."""
    stats = stats if stats is not None else {}
    T = [LineString(t) for t in traced if len(t) > 1]
    if area is not None:
        a50 = prep(area.buffer(50)); T = [g for g in T if a50.intersects(g)]
    tt = STRtree(T) if T else None
    out = [np.asarray(g.coords) for g in T]
    sl = list(streets); stt = STRtree(sl) if sl else None
    n = m = 0
    for lp in loops:
        g = LineString(lp)
        near = [T[int(k)] for k in tt.query(g.buffer(DUP))] if tt is not None else []
        rest = g.difference(unary_union([t.buffer(DUP, quad_segs=4) for t in near])) if near else g
        from shapely.ops import linemerge
        if rest.geom_type == "MultiLineString":
            rest = linemerge(rest)
        for q in getattr(rest, "geoms", [rest]):
            if q.geom_type != "LineString" or q.length < FILL_MIN:
                continue
            if twin_share(q, near) > 0.4:
                stats["fill_twin"] = stats.get("fill_twin", 0) + 1; continue  # runs beside a traced kerb: a second copy of it
            if stt is not None and any(sl[int(k)].intersects(q) for k in stt.query(q)):
                stats["fill_cross"] = stats.get("fill_cross", 0) + 1; continue  # a kerb never crosses a street
            c = np.asarray(q.coords); ok = True; mids = []
            for j in (0, -1):
                e = Point(c[j]); bs = [t for t in near if t.distance(e) <= DUP + 0.6]
                if bs:
                    b = min(bs, key=lambda b: b.distance(e)); tb = b.project(e); s0 = np.asarray(b.interpolate(tb).coords[0])
                    # meets that kerb end-on, or runs on along it; a fill hitting the middle of a kerb side-on is a T, not a kerb
                    d_in = tangent(q, 0.0 if j == 0 else q.length)
                    if min(tb, b.length - tb) > T_END:
                        mids.append(id(b))
                        if abs(tangent(b, tb) @ d_in) < np.cos(np.radians(MERGE_ANG)):
                            ok = False; break
                    c = np.vstack([s0, c]) if j == 0 else np.vstack([c, s0])
            if not ok:
                stats["fill_tee"] = stats.get("fill_tee", 0) + 1; continue
            cg = LineString(c)
            if any(crosses_mid(t, cg) for t in near):
                stats["fill_crosses_kerb"] = stats.get("fill_crosses_kerb", 0) + 1; continue  # kerbs never cross each other
            if len(mids) == 2 and mids[0] != mids[1] and q.length < CROSSOVER:
                # both ends land mid-way on two different kerbs a few metres apart: a crossover between two parallel kerbs
                # (the V at tile 2, Jacky 7 Nov 2026), not a missing piece of either
                stats["fill_crossover"] = stats.get("fill_crossover", 0) + 1; continue
            c = tangent_smooth(c)
            if not smooth(c):
                stats["fill_spike"] = stats.get("fill_spike", 0) + 1; continue
            if along_bridge(c, stt, sl) > 0.3:
                stats["fill_bridge"] = stats.get("fill_bridge", 0) + 1; continue  # Jacky 7 Nov: a highway bridge has no kerb
            out.append(c); n += 1; m += q.length
    stats["fill_pieces"] = n; stats["fill_m"] = int(m)
    return out


def guide(lines, loops, streets=(), stats=None):
    """Every kerb end left open is carried along its block's loop to the next kerb: from the end, onto the nearest loop (within
    GUIDE_REACH m), along it in the end's own heading until a kerb lies within DUP m of the loop, and onto that kerb. The loop
    is the street layout's closed kerb, so a path along it always exists; the end is closed unless the way crosses a street."""
    stats = stats if stats is not None else {}
    L = [LineString(o) for o in loops if len(o) > 3]
    if not L:
        return lines
    lt = STRtree(L); sl = list(streets); stt = STRtree(sl) if sl else None
    out = [np.asarray(c) for c in lines]
    G = [LineString(c) for c in out]; tree = STRtree(G); ADD = []
    near_ids = lambda geom: [int(x) for x in tree.query(geom)] + [x for x in ADD if G[x].intersects(geom)]
    done = 0

    def walk(i, j, e, hd, lp, te, skip=-1):
        """The join from end e (heading hd) of kerb i along loop lp: (path, line), or why it is not drawn. It may end only where
        it meets another kerb's end, or where it runs into a kerb the loop then FOLLOWS (the same kerb line): a kerb the loop only
        passes (the kerb across a narrow carriageway, a median) is not this kerb, and joining it would make a V or a second
        parallel line poking out (Jacky 7 Nov 2026). The path is then smoothed so it leaves the end and enters the kerb tangentially."""
        t0 = lp.project(Point(e)); sg = 1.0 if tangent(lp, t0) @ hd >= 0 else -1.0
        at = lambda x: lp.interpolate((t0 + sg * x) % lp.length)
        path = [e]; hit = None
        for step in np.arange(GUIDE_START, GUIDE_MAX, 1.0):
            if skip >= 0 and not 0.0 <= t0 + sg * step <= lp.length:
                break   # the line it runs beside has ended
            q = at(step); path.append(np.asarray(q.coords[0]))
            # its own kerb counts only far along it from the end (closing its own loop), never the stretch it came from
            near = [m for m in near_ids(q.buffer(DUP)) if G[m].distance(q) <= DUP and m != skip
                    and not (m == i and abs(G[i].project(q) - te) < 30.0)]
            if near:
                m = min(near, key=lambda m: G[m].distance(q)); hit = np.asarray(G[m].interpolate(G[m].project(q)).coords[0])
                break
        if hit is None:
            return "no_kerb"
        hk = G[m]; th_t = hk.project(Point(hit))
        at_end = min(th_t, hk.length - th_t) <= T_END
        if m != i:
            # two kerbs side by side (a kerb and the bus-lane line beside it, both sides of a median): the kerb it starts from runs
            # within TWIN m of the one it would join for the last 15 m before its end, so the join only links two parallel lines
            # (the V at tile 2, Jacky 7 Nov 2026: "there should not be two parallel line")
            back = [np.asarray(G[i].interpolate(te + x if j == 0 else te - x).coords[0]) for x in (5.0, 10.0, 15.0)]
            if G[i].length > 20.0 and all(hk.distance(Point(b)) <= TWIN for b in back):
                if skip >= 0 or not hk.geom_type == "LineString":
                    return "parallel"
                # carry the kerb on beside that one at its own distance (Jacky 7 Nov: "you should just continue tracing it")
                # until it meets the next kerb; never join the line beside it
                off = e - np.asarray(hk.interpolate(hk.project(Point(e))).coords[0]); dd = np.hypot(*off)
                if dd < 0.5:
                    return "parallel"
                side = "left" if (tangent(hk, hk.project(Point(e))) @ np.array([off[1], -off[0]])) < 0 else "right"
                try:
                    pl = hk.parallel_offset(dd, side, join_style=2)
                except Exception:
                    return "parallel"
                if pl.geom_type != "LineString" or pl.length < 5:
                    return "parallel"
                r2 = walk(i, j, e, hd, pl, te, skip=m)
                return r2 if isinstance(r2, tuple) else "parallel"
        if not at_end:
            # the same kerb: the loop keeps running along it for FOLLOW m after the meeting point
            fol = [hk.distance(at(step + x)) <= DUP + 0.5 for x in np.arange(1.0, FOLLOW + 1.0, 1.0)]
            if np.mean(fol) < 0.7:
                return "not_same_kerb"
        # taper: the end's offset from the loop fades out over the first GUIDE_TAPER m, the hit's fades in over the last
        P = np.asarray(path[1:]); n = len(P)
        if n >= 2:
            o0 = e - np.asarray(lp.interpolate(t0).coords[0]); o1 = hit - P[-1]
            d = np.arange(n, dtype=float) + GUIDE_START
            a0 = np.clip(1 - (d - GUIDE_START) / GUIDE_TAPER, 0, 1); a1 = np.clip(1 - (d[-1] - d) / GUIDE_TAPER, 0, 1)
            path = [e] + list(P + a0[:, None] * o0 + a1[:, None] * o1)
        path.append(hit)
        th = tangent(hk, th_t); dn = np.asarray(path[-1]) - np.asarray(path[-2]); dn = dn / (np.hypot(*dn) or 1)
        if th @ dn < 0:
            th = -th
        if not at_end and th @ dn < np.cos(np.radians(MERGE_ANG)):
            return "spike_hit"
        path = tangent_smooth(np.asarray(path), hd, th if not at_end else None)
        w = LineString(path)
        if not smooth(path[:6], hd):
            return "spike_head"
        if not smooth(path):
            return "spike_body"
        if stt is not None and any(sl[int(x)].intersects(w) for x in stt.query(w)):
            return "cross"
        if any(crosses_mid(G[x], w) for x in near_ids(w)):
            return "crosses_kerb"   # kerbs never cross each other
        if along_bridge(path, stt, sl) > 0.3:
            return "bridge"
        return path, w

    def straight(i, e, hd):
        """The same kerb carrying on ahead (Jacky 7 Nov: a kerb along a bus lane just continues): another kerb's end straight
        ahead within LINE_MAX m, at most LINE_LAT m off the line and heading the same way within LINE_ANG deg."""
        ray = LineString([e, e + hd * LINE_MAX]); best = None
        for m in near_ids(ray.buffer(LINE_LAT)):
            if m == i or len(G[m].coords) < 2:
                continue
            for k in (0, -1):
                q = np.asarray(G[m].coords[k]); v = q - e; along = v @ hd; lat = abs(v @ np.array([-hd[1], hd[0]]))
                if along < 1.0 or along > LINE_MAX or lat > LINE_LAT:
                    continue
                nb = np.asarray(G[m].interpolate(3.0 if k == 0 else G[m].length - 3.0).coords[0]); dm = nb - q
                dm = dm / (np.hypot(*dm) or 1)
                if dm @ hd < np.cos(np.radians(LINE_ANG)):
                    continue   # that kerb must carry on in the same direction from its end
                if best is None or along < best[0]:
                    best = (along, q, m, k)
        if best is None:
            return None
        q = best[1]; nb = np.asarray(G[best[2]].interpolate(3.0 if best[3] == 0 else G[best[2]].length - 3.0).coords[0])
        h1 = nb - q; h1 = h1 / (np.hypot(*h1) or 1)
        pts = tangent_smooth(np.array([e, q]), hd, h1)
        w = LineString(pts)
        if stt is not None and any(sl[int(x)].intersects(w) for x in stt.query(w)):
            return None
        if along_bridge(pts, stt, sl) > 0.3:
            return None
        return pts, w

    for i, c in enumerate(list(out)):
        if len(c) < 2 or np.hypot(*(c[0] - c[-1])) < 1.0:
            continue
        for j in (0, -1):
            e = c[j]; pe = Point(e)
            if any(k != i and G[k].distance(pe) <= ka.END_NEAR for k in near_ids(pe.buffer(ka.END_NEAR))):
                continue
            g = G[i]; bk = np.asarray(g.interpolate(3.0 if j == 0 else g.length - 3.0).coords[0]); hd0 = e - bk
            if np.hypot(*hd0) > 1e-6:
                st_ = straight(i, e, hd0 / np.hypot(*hd0))
                if st_:
                    out.append(np.asarray(st_[0])); G.append(st_[1]); ADD.append(len(G) - 1); done += 1
                    stats["guide_straight"] = stats.get("guide_straight", 0) + 1; continue
            k = int(lt.nearest(pe)); lp = L[k]
            if lp.distance(pe) > GUIDE_REACH:
                stats["guide_no_loop"] = stats.get("guide_no_loop", 0) + 1; continue
            res = None
            for cut in GUIDE_CUTS:
                # a traced end that curls or overshoots into the junction is cut back a little before the join starts
                g = G[i]
                if g.length < cut + 6.0:
                    break
                tc = cut if j == 0 else g.length - cut
                ec = np.asarray(g.interpolate(tc).coords[0])
                bk = np.asarray(g.interpolate(tc + 3.0 if j == 0 else tc - 3.0).coords[0])
                hd = ec - bk; hn = np.hypot(*hd)
                if hn < 1e-6:
                    break
                res = walk(i, j, ec, hd / hn, lp, tc)
                if isinstance(res, tuple):
                    if cut > 0:
                        sub = substring(g, cut, g.length) if j == 0 else substring(g, 0, g.length - cut)
                        out[i] = np.asarray(sub.coords); G[i] = sub; c = out[i]
                    break
            if not isinstance(res, tuple):
                if res:
                    stats["guide_" + res] = stats.get("guide_" + res, 0) + 1
                continue
            path, w = res
            out.append(np.asarray(path)); done += 1
            G.append(w); ADD.append(len(G) - 1)
    stats["guide_closed"] = done
    return out


def soften(c, sigma=SOFT_SIGMA, step=0.5):
    """The line resampled every step m and Gaussian-smoothed (sigma m): sideways steps and jogs where traced pieces were welded at
    slightly different offsets become gentle S-bends over ~4 sigma, wobbles go, corners keep their place (a 6 m round corner moves
    under 0.3 m). Ends stay put; a closed line stays closed (Jacky 7 Nov 2026: "smooth that out, it still looks fussy")."""
    from scipy.ndimage import gaussian_filter1d
    c = np.asarray(c, dtype=float); g = LineString(c)
    if g.length < 4 * sigma:
        return c
    closed = np.hypot(*(c[0] - c[-1])) < 0.5
    n = max(int(g.length / step), 4)
    P = np.array([g.interpolate(x).coords[0] for x in np.linspace(0, g.length, n + 1)])
    if closed:
        Q = np.c_[gaussian_filter1d(P[:-1, 0], sigma / step, mode="wrap"), gaussian_filter1d(P[:-1, 1], sigma / step, mode="wrap")]
        Q = np.vstack([Q, Q[:1]])
    else:
        Q = np.c_[gaussian_filter1d(P[:, 0], sigma / step, mode="nearest"), gaussian_filter1d(P[:, 1], sigma / step, mode="nearest")]
        # pin the ends: blend back to the original over the first and last 2 sigma so joins to other kerbs stay exact
        w = np.clip(np.minimum(np.arange(len(P)), np.arange(len(P))[::-1]) * step / (2 * sigma), 0, 1)[:, None]
        Q = w * Q + (1 - w) * P
    return np.asarray(LineString(Q).simplify(0.05).coords)


def final_clean(out, stats):
    """The finished lines checked once more for what a kerb never does (the same shapes openfetch-derive kerbreview.py fails):
    fold-backs and strands (untangle, a little wider than the reviewer's 2.5 / 2.0 m so a cut edge does not trip it), a line
    lying mostly within INSIDE m of longer kerbs (a kerb within a kerb), and a free end stopping beside a parallel kerb (cut back
    until it is clear of it)."""
    st = {}
    out = untangle(out, st, self_near=3.0, other_near=2.3, tail=0.0)   # tails: only on traced input (here they cut joins at corners)
    stats.update({"final_" + k: v for k, v in st.items()})
    G = sorted([LineString(c) for c in out], key=lambda g: -g.length); tree = STRtree(G); keep = []; kept = set()
    for i, g in enumerate(G):
        others = [G[k] for k in (int(x) for x in tree.query(g.buffer(INSIDE))) if k in kept]
        if others:
            ts = np.arange(0.5, g.length, 1.0)
            near = sum(1 for t in ts if any(o.distance(g.interpolate(t)) < INSIDE for o in others))
            if near >= 0.7 * len(ts):
                stats["final_inside"] = stats.get("final_inside", 0) + 1; continue
        keep.append(g); kept.add(i)
    G = keep; tree = STRtree(G); n_cut = 0
    for i in range(len(G)):
        g = G[i]
        for j in (0, -1):
            for _ in range(40):
                L = g.length
                if L < KEEP_MIN:
                    break
                e = Point(g.coords[j]); t = 0.0 if j == 0 else L
                near = [G[k] for k in (int(x) for x in tree.query(e.buffer(BESIDE))) if k != i]
                if not near or any(o.distance(e) < 1.0 for o in near):
                    break
                tg = tangent(g, min(max(t, 1.0), L - 1.0))
                if not any(o.distance(e) < BESIDE and abs(tangent(o, o.project(e)) @ tg) >= PAR for o in near):
                    break
                g = substring(g, 1.0, L) if j == 0 else substring(g, 0, L - 1.0); n_cut += 1
        G[i] = g
    stats["final_beside_m"] = n_cut
    return [np.asarray(g.coords) for g in G if g.length >= KEEP_MIN]


CORNER_R = 6.0     # m, radius of the corner made where two kerbs crossed (a side-street kerb meeting the main kerb)
CORNER_SEE = 20.0  # m, a street centreline this near a crossing, between two of its arms, makes that side road, not block
ARM_DROP = 30.0    # m, a road-side arm shorter than this goes; a longer one is cut back ARM_CUT m from the crossing
ARM_CUT = 3.0
X_END = 0.8        # m, a crossing this close to a kerb end is a join, not a crossing (the reviewer counts 1.0)
T_TOUCH, T_ANG = 2.5, 35.0  # m, deg: a kerb end this near another kerb's middle, coming in steeper than this, is a T
LOOP_DROP = 40.0   # m, a kerb that crosses itself round a loop shorter than this has a knot: the loop goes


def _bez(a, c, b, n=10):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * c + t ** 2 * b


def _xings(G):
    """Every place two kerbs (or one kerb with itself) cross away from their ends: (i, j, ti, tj, point); i == j for a self-crossing
    (ti < tj along the line)."""
    tree = STRtree(G); out = []
    for i, a in enumerate(G):
        if not a.is_simple:
            c = np.asarray(a.coords); seg = [LineString(c[k:k + 2]) for k in range(len(c) - 1)]
            cum = np.r_[0, np.cumsum([s.length for s in seg])]; st = STRtree(seg); done = False
            for k, s in enumerate(seg):
                for m in st.query(s, predicate="intersects"):
                    m = int(m)
                    if m <= k + 1 or done:
                        continue
                    p = s.intersection(seg[m])
                    if p.geom_type != "Point":
                        continue
                    t1 = cum[k] + Point(c[k]).distance(p); t2 = cum[m] + Point(c[m]).distance(p)
                    if t2 - t1 < 0.05:
                        continue
                    if a.coords[0] == a.coords[-1] and t1 < X_END and a.length - t2 < X_END:
                        continue
                    if t1 < X_END and a.length - t2 < X_END and Point(a.coords[0]).distance(Point(a.coords[-1])) < 1.0:
                        continue
                    out.append((i, i, t1, t2, p)); done = True
        for j in tree.query(a, predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            b = G[j]; x = a.intersection(b)
            for p in [x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]:
                ta, tb = a.project(p), b.project(p)
                if min(ta, a.length - ta) < X_END or min(tb, b.length - tb) < X_END:
                    continue
                out.append((i, j, ta, tb, p))
    return out


CORNER_LOG = []   # (what, x, y) of every corner made, for the review sheet


def _tees(G, done=()):
    """Every kerb end resting on the middle of another kerb (within T_TOUCH m, more than T_END m from its ends), coming in at more
    than T_ANG deg (a shallow approach is a merge, kept): (line hit, line ending, t on the hit line, which end, foot point)."""
    tree = STRtree(G); out = []
    for i, g in enumerate(G):
        if i in done or g.length < 2.0:
            continue
        for end in ("s", "e"):
            e = Point(g.coords[0] if end == "s" else g.coords[-1])
            for k in (int(x) for x in tree.query(e.buffer(T_TOUCH))):
                if k == i:
                    continue
                o = G[k]
                if o.distance(e) >= T_TOUCH:
                    continue
                t = o.project(e)
                if min(t, o.length - t) < T_END:
                    continue
                h = _hdg(g, 0.0 if end == "s" else g.length, 4.0)
                if _par(h, _hdg(o, t, 3.0), T_ANG):
                    continue
                out.append((k, i, t, end, o.interpolate(t)))
                break
    return out


def _sectors(P, arms_dir, st_tree, streets, p):
    """For each gap between neighbouring arms (counter-clockwise): True when no street centreline passes through it near P."""
    pts = []
    for s in (streets[int(x)] for x in st_tree.query(p.buffer(CORNER_SEE))) if st_tree is not None else ():
        g = s.intersection(p.buffer(CORNER_SEE))
        for gg in getattr(g, "geoms", [g]):
            if gg.geom_type == "LineString" and gg.length > 0:
                pts += [gg.interpolate(t).coords[0] for t in np.arange(0, gg.length + 0.5, 1.0)]
    ang = [np.arctan2(y - P[1], x - P[0]) for x, y in pts if np.hypot(x - P[0], y - P[1]) > 0.5]
    order = sorted(range(len(arms_dir)), key=lambda k: arms_dir[k]); n = len(order); block = []
    for m in range(n):
        lo, hi = arms_dir[order[m]], arms_dir[order[(m + 1) % n]]
        span = (hi - lo) % (2 * np.pi)
        block.append(not any((t - lo) % (2 * np.pi) < span for t in ang))
    return order, block


def _ring_prep(c):
    """A loop left a hair open (end within RING_GAP m of its start) is closed, and a ring starts half-way round, so a knot at its
    seam is seen as a crossing."""
    c = np.asarray(c, dtype=float); gap = np.hypot(*(c[0] - c[-1]))
    if 0.05 <= gap < RING_GAP and LineString(c).length > 4 * RING_GAP:
        c = np.vstack([c, c[:1]])
    if len(c) > 4 and np.hypot(*(c[0] - c[-1])) < 0.05:
        k = len(c) // 2; c = np.vstack([c[k:-1], c[:k + 1]]); c[-1] = c[0]
    return LineString(c)


def corners(out, streets, stats):
    """Kerbs that cross or butt into each other (Jacky 7 Nov 2026, version c review: "side-street kerbs cross the main kerb in an
    X instead of one rounded corner"; also a plus across a road, a square corner with a hook, a knot where a line crosses itself).
    A kerb never crosses a kerb, and the main kerb does not run on across a side street's mouth: at every crossing (four arms)
    and every place a kerb end rests on the middle of another kerb (a T, three arms) the arms are sorted round the point and each
    gap between two neighbouring arms is road when a street centreline passes through it within CORNER_SEE m, else block.
    One block gap = a street corner: its two arms are kept and joined by a round corner (CORNER_R m); the road-side arms go
    (cut back ARM_CUT m when longer than ARM_DROP m, so the piece across a side street's mouth goes when both its corners are
    done). Two block gaps side by side = a stub poking into the block: the through kerb stays, the stub goes. Anything else at a
    crossing: the longer kerb carries straight on and the other is cut; at a T it is left as it is. A self-crossing round a loop
    under LOOP_DROP m is a knot: the loop goes."""
    G = [_ring_prep(c) for c in out]
    st_tree = STRtree(streets) if streets else None
    n = {"round": 0, "stub": 0, "knot": 0, "other": 0, "tee_round": 0, "tee_stub": 0, "tee_left": 0}
    skip_t = set()
    for _round in range(12):
        G = [g if g.is_simple else _ring_prep(g.coords) for g in G]
        X = [("x",) + x for x in _xings(G)] + [("t",) + t for t in _tees(G)]
        X = [x for x in X if not (x[0] == "t" and (round(x[5].x, 1), round(x[5].y, 1)) in skip_t)]
        if not X:
            break
        touched = set(); new = {}
        for item in X:
            kind, i, j = item[0], item[1], item[2]
            if i in touched or j in touched:
                continue
            p = item[5]; P = np.asarray(p.coords[0])
            if kind == "t":
                a, b = G[i], G[j]; t, end = item[3], item[4]
                edges = [substring(a, 0, t), substring(a, t, a.length), b]
                arms = [(0, "e"), (1, "s"), (2, end)]
                if min(edges[0].length, edges[1].length) < 0.2:
                    continue
            elif i == j:
                a = G[i]; L = a.length; ti, tj = item[3], item[4]
                c = np.asarray(a.coords)
                if (ti < X_END or L - tj < X_END) and np.hypot(*(c[0] - c[-1])) < 0.05 and len(c) > 4:
                    k = len(c) // 2; c = np.vstack([c[k:-1], c[:k + 1]]); c[-1] = c[0]   # a knot at a ring's seam: seen next round
                    new[i] = [c]; touched.add(i)
                    continue
                if ti < X_END or L - tj < X_END:          # an end resting on its own line further on (a 6 shape): pulled back off it
                    new[i] = [np.asarray((substring(a, 1.5, L) if ti < X_END else substring(a, 0, L - 1.5)).coords)]
                    n["knot"] += 1; touched.add(i)
                    continue
                edges = [substring(a, 0, ti), substring(a, ti, tj), substring(a, tj, L)]
                arms = [(0, "e"), (1, "s"), (1, "e"), (2, "s")]
                if edges[1].length < LOOP_DROP:
                    edges[1] = None; n["knot"] += 1; touched.add(i)
                    new[i] = _assemble(edges, arms, {(0, 3)}, set(), P)
                    continue
            else:
                a, b = G[i], G[j]; ti, tj = item[3], item[4]
                edges = [substring(a, 0, ti), substring(a, ti, a.length), substring(b, 0, tj), substring(b, tj, b.length)]
                arms = [(0, "e"), (1, "s"), (2, "e"), (3, "s")]
            if any(e is not None and e.length < 0.2 for e in edges[:2] if kind == "x") :
                continue
            dirs = []
            for (k, e_) in arms:
                e = edges[k]; arm = e if e_ == "s" else LineString(np.asarray(e.coords)[::-1])
                q = np.asarray(arm.interpolate(min(4.0, arm.length)).coords[0]); dirs.append(np.arctan2(q[1] - P[1], q[0] - P[0]))
            order, block = _sectors(P, dirs, st_tree, streets, p)
            na = len(arms); nb = sum(block)
            adj = [m for m in range(na) if block[m] and block[(m + 1) % na]]
            pre = "tee_" if kind == "t" else ""
            if nb == 1:
                m = block.index(True); pairs = {(order[m], order[(m + 1) % na])}; n[pre + "round"] += 1
            elif nb == 2 and adj:
                m = adj[0]; pairs = {(order[m], order[(m + 2) % na])}; n[pre + "stub"] += 1
                if kind == "t" and set(next(iter(pairs))) != {0, 1}:   # the T's stem is not the stub: leave it
                    skip_t.add((round(p.x, 1), round(p.y, 1))); n["tee_left"] += 1; continue
            elif kind == "t":
                skip_t.add((round(p.x, 1), round(p.y, 1))); n["tee_left"] += 1; continue
            else:
                pairs = {(0, 3)} if i == j else ({(0, 1)} if a.length >= b.length else {(2, 3)}); n["other"] += 1
            touched.update((i, j)); CORNER_LOG.append((pre + ("round" if nb == 1 else "other"), float(P[0]), float(P[1])))
            new[i] = _assemble(edges, arms, pairs, {1, 2} if (kind == "x" and i == j) else set(), P)
            if j != i:
                new[j] = []
        G2 = []
        for k, g in enumerate(G):
            if k in new:
                G2 += [LineString(c) for c in new[k] if len(c) > 1 and LineString(c).length >= KEEP_MIN]
            else:
                G2.append(g)
        G = G2
    stats.update({"corner_" + k: v for k, v in n.items()})
    stats["corner_x_left"] = len(_xings(G))
    return [np.asarray(g.coords) for g in G]


def _assemble(edges, arms, pairs, keep_arms, P):
    """Lines rebuilt round one crossing point P: paired arms joined by a round corner, other arms cut back or dropped."""
    trim = {k: [0.0, 0.0] for k in range(len(edges))}
    link = {}
    for x, y in pairs:
        ex, ey = edges[arms[x][0]], edges[arms[y][0]]
        ax = ex if arms[x][1] == "s" else LineString(np.asarray(ex.coords)[::-1])
        ay = ey if arms[y][1] == "s" else LineString(np.asarray(ey.coords)[::-1])
        u = np.asarray(ax.interpolate(min(4.0, ax.length)).coords[0]) - P
        v = np.asarray(ay.interpolate(min(4.0, ay.length)).coords[0]) - P
        th = np.arccos(np.clip(u @ v / max(np.hypot(*u) * np.hypot(*v), 1e-9), -1, 1))
        d = 0.0 if th > np.radians(150) else min(CORNER_R / np.tan(th / 2), 0.45 * ax.length, 0.45 * ay.length, 15.0)
        if arms[x][0] == arms[y][0]:
            d = min(d, 0.3 * ax.length)
        for z, a_ in ((x, ax), (y, ay)):
            trim[arms[z][0]][0 if arms[z][1] == "s" else 1] = d
        A = np.asarray(ax.interpolate(d).coords[0]); B = np.asarray(ay.interpolate(d).coords[0])
        link[x] = (y, _bez(A, P, B) if d > 0 else np.array([P]))
        link[y] = (x, None)
    dead = set()
    for z, (k, end) in enumerate(arms):
        if z in link or edges[k] is None:
            continue
        other_free = (end == "s" and not any(arms[w] == (k, "e") for w in range(len(arms)))) or \
                     (end == "e" and not any(arms[w] == (k, "s") for w in range(len(arms))))
        if other_free and z not in keep_arms and edges[k].length < ARM_DROP:
            dead.add(k)
        else:
            trim[k][0 if end == "s" else 1] = ARM_CUT
    def piece(k, fwd):
        e = edges[k]; s_, e_ = trim[k]
        g = substring(e, s_, max(s_, e.length - e_)); c = np.asarray(g.coords)
        return c if fwd else c[::-1]
    arm_at = {(k, end): z for z, (k, end) in enumerate(arms)}
    used = set(); res = []
    starts = [k for k in range(len(edges)) if edges[k] is not None and k not in dead]
    for k0 in starts + starts:
        if k0 in used:
            continue
        # walk backwards first to a free end so a chain is emitted once, from one end
        k, fwd = k0, True; seen = set()
        while True:
            z = arm_at.get((k, "s" if fwd else "e"))
            if z is None or z not in link or (k, fwd) in seen:
                break
            seen.add((k, fwd)); y = link[z][0]; k2, end2 = arms[y]
            if k2 in dead or k2 in used:
                break
            k, fwd = k2, end2 == "e"
            if k == k0:
                break
        chain = []; cur, f = k, fwd
        while cur not in used:
            used.add(cur); chain.append(piece(cur, f))
            z = arm_at.get((cur, "e" if f else "s"))
            if z is None or z not in link:
                break
            y, arc = link[z]; k2, end2 = arms[y]
            if k2 in dead:
                break
            arc = arc if arc is not None else link[y][1][::-1]
            chain.append(arc)
            if k2 in used:
                break
            cur, f = k2, end2 == "s"
        res.append(np.vstack(chain))
    return res


HOOK_NEAR, HOOK_ALONG, HOOK_MAX, RING_GAP = 2.6, 7.5, 30.0, 3.0   # m: a line back within HOOK_NEAR of itself more than HOOK_ALONG further on folds back


def unhook(out, stats):
    """Lines that fold back on themselves (the reviewer's "fold": within 2.5 m of itself more than 8 m further along). Seen in the
    version c review as short hooks and J-tails at line ends where a join or a rejoin turned back, and spikes out and back mid-line.
    A kerb never does that: a hook at an end (up to HOOK_MAX m) is cut off at its tip; an out-and-back spike in the middle is cut
    out and the two sides joined. A line that is folded along most of its length (a narrow island) is left alone."""
    from scipy.spatial import cKDTree
    res = []; n_end = n_mid = 0
    n_ring = 0
    for c in out:
        g = LineString(c); L = g.length
        gap = np.hypot(*(np.asarray(g.coords[0]) - g.coords[-1]))
        if 0 < gap < RING_GAP and L > 4 * RING_GAP:      # a loop left a hair open (its end beside its own start): close it
            g = LineString(list(g.coords) + [g.coords[0]]); L = g.length; n_ring += 1
        for _ in range(4):
            if L < HOOK_ALONG + 2:
                break
            nn = max(1, int(np.ceil(L))); ts = np.linspace(0, L, nn + 1)
            seg = [LineString([g.interpolate(ts[k]), g.interpolate(ts[k + 1])]) for k in range(nn)]
            ts = (ts[:-1] + ts[1:]) / 2; tr = STRtree(seg)
            closed = np.hypot(*(np.asarray(g.coords[0]) - g.coords[-1])) < 1.0
            pr = [(ts[a], ts[int(b)]) for a in range(nn) for b in tr.query(seg[a], predicate="dwithin", distance=HOOK_NEAR)
                  if int(b) > a and ts[int(b)] - ts[a] > HOOK_ALONG and not (closed and L - (ts[int(b)] - ts[a]) <= HOOK_ALONG)]
            if not pr or closed:
                break
            pr = [(min(a, b), max(a, b)) for a, b in pr]
            lo = min(a for a, _ in pr); hi = max(b for _, b in pr)
            tip = float(np.median([(a + b) / 2 for a, b in pr]))
            s_far = [b for a, b in pr if a < 3.0 and (a + b) / 2 > HOOK_MAX]
            e_far = [a for a, b in pr if b > L - 3.0 and L - (a + b) / 2 > HOOK_MAX]
            if s_far or e_far:
                # an end lying beside its own line far along (a near-6): the end is pulled back until it is clear
                at_start = bool(s_far)
                cut = 0.0; h = g
                for _k in range(int(HOOK_MAX)):
                    cut += 1.0; h = substring(g, cut, L) if at_start else substring(g, 0, L - cut)
                    e = Point(h.coords[0] if at_start else h.coords[-1])
                    far = substring(h, HOOK_ALONG, h.length) if at_start else substring(h, 0, h.length - HOOK_ALONG)
                    if far.distance(e) >= HOOK_NEAR + 0.6:
                        break
                g = h; n_end += 1
            elif hi - lo > 0.6 * L:
                break
            elif L - hi < 3.0 and L - tip <= HOOK_MAX:
                g = substring(g, 0, tip); n_end += 1
            elif lo < 3.0 and tip <= HOOK_MAX:
                g = substring(g, tip, L); n_end += 1
            elif hi - lo <= 2 * HOOK_MAX:
                a_, b_ = substring(g, 0, lo), substring(g, hi, L)
                g = LineString(np.vstack([np.asarray(a_.coords), np.asarray(b_.coords)])); n_mid += 1
            else:
                break
            L = g.length
        res.append(np.asarray(g.coords))
    stats.update({"unhook_end": n_end, "unhook_mid": n_mid, "unhook_ring": n_ring})
    return [c for c in res if LineString(c).length >= KEEP_MIN]


TWO_D, TWO_ANG, TWO_RUN = 2.3, 22.0, 6.0   # m, deg, m: a stretch this close beside another kerb, this parallel, this long, is a double


def _hdg(g, t, step):
    a = np.asarray(g.interpolate(max(0.0, t - step)).coords[0]); b = np.asarray(g.interpolate(min(g.length, t + step)).coords[0])
    return np.arctan2(b[1] - a[1], b[0] - a[0])


def _par(h1, h2, lim):
    d = abs(h1 - h2) % np.pi
    return np.degrees(min(d, np.pi - d)) <= lim


def tidy(out, stats):
    """Last pass (version c review, "two lines merge and run on top of each other", "short loose strand ends just beside the curved
    kerb"): a stretch of a kerb running within TWO_D m of a longer kerb, parallel, for TWO_RUN m or more is a second copy of that
    kerb and is taken out of the shorter one; then every free end that stops beside a parallel kerb (BESIDE m, the reviewer's
    "beside") is cut back until it is clear, or joins that kerb when it points into it."""
    G = sorted([LineString(c) for c in out], key=lambda g: -g.length)
    tree = STRtree(G); n_two = 0; res = []
    for i, g in enumerate(G):
        near = [k for k in (int(x) for x in tree.query(g.buffer(TWO_D))) if k < i]
        if not near:
            res.append(g); continue
        ts = np.arange(1.0, g.length, 2.0); bad = np.zeros(len(ts), bool)
        for n, t in enumerate(ts):
            q = g.interpolate(t); h = _hdg(g, t, 1.0)
            for k in near:
                o = G[k]
                if o.distance(q) < TWO_D and _par(h, _hdg(o, o.project(q), 1.0), TWO_ANG):
                    bad[n] = True; break
        runs = []; st = None
        for n in range(len(ts) + 1):
            if n < len(ts) and bad[n]:
                st = n if st is None else st
            elif st is not None:
                if (n - st) * 2.0 >= TWO_RUN:
                    runs.append((max(0.0, ts[st] - 1.0), min(g.length, ts[n - 1] + 1.0)))
                st = None
        if not runs:
            res.append(g); continue
        n_two += len(runs); a0 = 0.0
        for r0, r1 in runs:
            if r0 - a0 >= KEEP_MIN:
                res.append(substring(g, a0, r0))
            a0 = r1
        if g.length - a0 >= KEEP_MIN:
            res.append(substring(g, a0, g.length))
    G = res; tree = STRtree(G); n_cut = n_drop = 0
    for i in range(len(G)):
        g = G[i]
        for j in (0, -1):
            for _ in range(60):
                L = g.length
                if L < KEEP_MIN:
                    break
                e = Point(g.coords[j]); t = 0.0 if j == 0 else L
                near = [k for k in (int(x) for x in tree.query(e.buffer(BESIDE))) if k != i]
                if not near or any(G[k].distance(e) < 1.0 for k in near):
                    break
                h = _hdg(g, t, 2.0); hit = False
                for k in near:
                    o = G[k]; od = o.project(e)
                    if o.distance(e) >= BESIDE or min(o.length, od + 5.0) - max(0.0, od - 5.0) < 8.5:
                        continue
                    if _par(h, _hdg(o, od, 3.0), 22.0):
                        hit = True; break
                if not hit:
                    break
                g = substring(g, 1.0, L) if j == 0 else substring(g, 0, L - 1.0); n_cut += 1
        G[i] = g
    stats.update({"tidy_double": n_two, "tidy_beside_m": n_cut})
    return [np.asarray(g.coords) for g in G if g.length >= KEEP_MIN]


MOUTH_ANG, MOUTH_W = 55.0, 4.5   # deg, m


def _through(p, g, tree, geoms):
    """True when street centrelines carry on on both sides of kerb g near p (points 12-25 m from p on each side of the kerb)."""
    t = g.project(p); h = _hdg(g, t, 3.0); n = np.array([-np.sin(h), np.cos(h)]); P = np.asarray(p.coords[0]); side = [0, 0]
    for k in tree.query(p.buffer(25.0)):
        s = geoms[int(k)].intersection(p.buffer(25.0))
        for ss in getattr(s, "geoms", [s]):
            if ss.geom_type != "LineString":
                continue
            for d in np.arange(0, ss.length, 1.0):
                q = np.asarray(ss.interpolate(d).coords[0]); r = np.hypot(*(q - P))
                if 12.0 <= r <= 25.0:
                    side[int((q - P) @ n > 0)] += 1
    return min(side) >= 3


def _turns_back(g, t, reach=25.0):
    """True when the kerb turns round (more than 150 deg) within reach m either side of t: a U across a road."""
    a, b = max(0.0, t - reach), min(g.length, t + reach)
    if b - a < 10:
        return False
    h0, h1 = _hdg(g, a + 2.0, 2.0), _hdg(g, b - 2.0, 2.0)
    d = abs((h1 - h0 + np.pi) % (2 * np.pi) - np.pi)
    return np.degrees(d) > 150


def mouths(out, streets, stats, tracks=()):
    """A kerb running across a street (version c review: "kerbs joined by a U-loop across the road where it continues"; the main
    kerb drawn on across a side street's mouth). Where a kerb crosses a street centreline (bridges, tunnels and lanes left out)
    steeper than MOUTH_ANG deg and the street carries on both sides of the kerb (not the head of a cul-de-sac, where the kerb
    rightly turns round), the part of the kerb within MOUTH_W m of that centreline is in the roadway and goes. A kerb that turns
    round across a vehicle track (fh 9) that carries the street on goes the same way."""
    br = STRtree(BRIDGES) if BRIDGES else None
    def on_bridge(s):
        m = s.interpolate(0.5, normalized=True)
        return br is not None and any(BRIDGES[int(k)].buffer(1.0).contains(m) for k in br.query(m.buffer(1.0)))
    S = [(s, False) for s in streets if not on_bridge(s)] + [(s, True) for s in tracks if not on_bridge(s)]
    geoms = [s for s, _ in S]; st = STRtree(geoms); res = []; n_cut = 0
    for c in out:
        g = LineString(c); cut = None
        for k in (int(x) for x in st.query(g, predicate="crosses")):
            s, is_track = S[k]; x = g.intersection(s)
            for p in [q for q in getattr(x, "geoms", [x]) if q.geom_type == "Point"]:
                if _par(_hdg(g, g.project(p), 2.0), _hdg(s, s.project(p), 2.0), 90 - MOUTH_ANG):
                    continue
                if not _through(p, g, st, geoms):
                    continue
                if not _turns_back(g, g.project(p)):    # straight across a mouth: left (cutting it opens the corner)
                    continue
                band = s.buffer(MOUTH_W).intersection(p.buffer(3 * MOUTH_W))
                cut = band if cut is None else cut.union(band)
        if cut is None:
            res.append(c); continue
        rest = g.difference(cut); n_cut += 1
        res += [np.asarray(q.coords) for q in getattr(rest, "geoms", [rest]) if q.geom_type == "LineString" and q.length >= KEEP_MIN]
    stats["mouth_cut"] = n_cut
    return res


GAP_JOIN, GAP_AHEAD, GAP_TURN, GAP_BACK = 10.0, 15.0, 110.0, 8.0   # m, m, deg, m: two free kerb ends this close, facing each other or meeting ahead within GAP_AHEAD, join


def gapjoin(out, streets, stats):
    """Open corners and short breaks (version c review: "north kerb of the main road is broken with a gap"): two free ends under
    GAP_JOIN m apart that point at each other, or whose lines would meet ahead of both within GAP_AHEAD m (a corner left open),
    are joined by a smooth curve tangent to both, never across a street centreline or another kerb."""
    G = [LineString(c) for c in out]
    tree = STRtree(G); st = STRtree(streets) if streets else None
    ends = []
    for i, g in enumerate(G):
        if g.length < 4.0 or np.hypot(*(np.asarray(g.coords[0]) - g.coords[-1])) < 0.05:
            continue
        for j in (0, -1):
            e = Point(g.coords[j])
            if any(G[int(k)].distance(e) < 1.0 for k in tree.query(e.buffer(1.0)) if int(k) != i):
                continue
            t = 0.0 if j == 0 else g.length
            q = np.asarray(g.interpolate(min(max(t, 0), g.length) + (3.0 if j == 0 else -3.0)).coords[0])
            h = np.asarray(e.coords[0]) - q; h = h / max(np.hypot(*h), 1e-9)
            ends.append((i, j, np.asarray(e.coords[0]), h))
    P = np.array([e[2] for e in ends]) if ends else np.zeros((0, 2))
    from scipy.spatial import cKDTree
    used = set(); joins = []
    cand = []
    for a, b in (cKDTree(P).query_pairs(GAP_JOIN) if len(P) else []):
        (i1, j1, e1, h1), (i2, j2, e2, h2) = ends[a], ends[b]
        d = e2 - e1; L = np.hypot(*d); trim = (0.0, 0.0)
        if L < 0.3:
            continue
        if np.degrees(np.arccos(np.clip(h1 @ (-h2), -1, 1))) > GAP_TURN:   # a hairpin or V, not a corner
            continue
        A = np.c_[h1, -h2]
        if abs(np.linalg.det(A)) > 0.2:
            s1, s2 = np.linalg.solve(A, d)
            # an end already at or past the corner point (a kerb cut at a side street's mouth, a side kerb stopping on the
            # main kerb's line) is pulled back so the two meet in a round corner of about CORNER_R
            if not (-GAP_BACK < s1 < GAP_AHEAD and -GAP_BACK < s2 < GAP_AHEAD):
                continue
            t1, t2 = max(0.0, 4.0 - s1), max(0.0, 4.0 - s2)
            if t1 > 0.4 * G[i1].length or t2 > 0.4 * G[i2].length:
                continue
            g1 = G[i1]; g2 = G[i2]
            f1 = np.asarray(g1.interpolate(t1 if j1 == 0 else g1.length - t1).coords[0])
            f2 = np.asarray(g2.interpolate(t2 if j2 == 0 else g2.length - t2).coords[0])
            X = e1 + s1 * h1; s1, s2 = np.hypot(*(X - f1)), np.hypot(*(X - f2))
            if not (0.4 < s1 / max(s2, 1e-6) < 2.5) or (h1 @ (X - f1) <= 0) or (h2 @ (X - f2) <= 0):
                continue
            path = _bez(f1, X, f2, 12); trim = (t1, t2)
        else:
            if h1 @ d <= 0 or h2 @ (-d) <= 0:
                continue
            if np.degrees(np.arccos(np.clip(h1 @ (-h2), -1, 1))) > 30 or abs(h1[0] * d[1] - h1[1] * d[0]) > max(3.0, 0.6 * L):
                continue
            t = np.linspace(0, 1, 12)[:, None]; c1, c2 = e1 + h1 * L / 3, e2 + h2 * L / 3
            path = (1 - t) ** 3 * e1 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * e2
        w = LineString(path)
        if st is not None and len(st.query(w, predicate="intersects")):
            continue
        if any(G[int(k)].crosses(w) for k in tree.query(w) if int(k) not in (i1, i2)):
            continue
        cand.append((L, a, b, path, trim))
    for L, a, b, path, trim in sorted(cand, key=lambda x: x[0]):
        if a in used or b in used:
            continue
        for (i_, j_), t_ in ((ends[a][:2], trim[0]), (ends[b][:2], trim[1])):
            if t_ > 0:
                g_ = G[i_]; G[i_] = substring(g_, t_, g_.length) if j_ == 0 else substring(g_, 0, g_.length - t_)
        used.update((a, b)); joins.append((ends[a][:2], ends[b][:2], path)); CORNER_LOG.append(("gap", *map(float, path[len(path) // 2])))
    # merge: each line's coords, oriented, joined through the paths
    parent = list(range(len(G))); seqs = {i: [np.asarray(g.coords)] for i, g in enumerate(G)}
    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for (i1, j1), (i2, j2), path in joins:
        r1, r2 = find(i1), find(i2)
        c1, c2 = np.vstack(seqs[r1]), np.vstack(seqs[r2])
        e1 = G[i1].coords[j1]; e2 = G[i2].coords[j2]
        if r1 == r2:
            seqs[r1] = [np.vstack([c1, path[1:-1] if np.hypot(*(c1[-1] - e1)) < 1e-6 else path[::-1][1:-1], c1[:1]])]
            continue
        if np.hypot(*(c1[-1] - e1)) > 1e-6:
            c1 = c1[::-1]
        if np.hypot(*(c2[0] - e2)) > 1e-6:
            c2 = c2[::-1]
        seqs[r1] = [np.vstack([c1, path[1:-1], c2])]; parent[r2] = r1; del seqs[r2]
    stats["gap_joined"] = len(joins)
    return [s[0] if len(s) == 1 else np.vstack(s) for s in seqs.values()]


WOB_SIGMA, WOB_OFF, WOB_TURN = 8.0, 1.0, 12.0   # m, m, deg per 40 m


def unwobble(out, stats):
    """A kerb on a straight street drifting a few metres off its line and back (version c review: "west kerb wobbles back and forth
    across the green bike lane"; traced pieces on a painted lane edge). Each line is compared with itself smoothed over WOB_SIGMA
    m: where the smoothed line runs straight (turning under WOB_TURN deg over 40 m) and the line strays more than WOB_OFF m from
    it, the smoothed line is used there (blended over 10 m). Corners and curves keep their shape: there the smoothed line turns."""
    from scipy.ndimage import gaussian_filter1d
    res = []; n = 0
    for c in out:
        c = np.asarray(c, dtype=float); g = LineString(c); L = g.length
        if L < 60 or np.hypot(*(c[0] - c[-1])) < 0.05:
            res.append(c); continue
        step = 1.0; m = int(L / step)
        P = np.array([g.interpolate(x).coords[0] for x in np.linspace(0, L, m + 1)])
        Q = np.c_[gaussian_filter1d(P[:, 0], WOB_SIGMA / step, mode="nearest"), gaussian_filter1d(P[:, 1], WOB_SIGMA / step, mode="nearest")]
        h = np.unwrap(np.arctan2(np.gradient(Q[:, 1]), np.gradient(Q[:, 0])))
        k = int(20 / step); turn = np.zeros(len(Q))
        for i in range(len(Q)):
            turn[i] = abs(h[min(len(Q) - 1, i + k)] - h[max(0, i - k)])
        off = np.hypot(*(P - Q).T)
        bad = (off > WOB_OFF) & (np.degrees(turn) < WOB_TURN)
        bad[:k] = False; bad[-k:] = False
        if not bad.any():
            res.append(c); continue
        w = gaussian_filter1d(np.convolve(bad.astype(float), np.ones(11), "same").clip(0, 1), 3)
        w = np.clip(w * 1.5, 0, 1)[:, None]
        R = w * Q + (1 - w) * P; n += 1
        res.append(np.asarray(LineString(R).simplify(0.05).coords))
    stats["unwobble"] = n
    return res


def props(o, kind, traced_path, roads, _c={}):
    """Feature properties as the published layer has them: a traced kerb keeps its own (road, source, areas, ...); a piece the
    street layout added gets source "street offset", the road type of the nearest street and the areas of the nearest kerb."""
    if "t" not in _c:
        to = Transformer.from_crs(4326, 7856, always_xy=True).transform
        fs = [f for f in json.load(open(traced_path))["features"] if f.get("geometry") and len(f["geometry"]["coordinates"]) > 1]
        _c["g"] = [LineString([to(*q[:2]) for q in f["geometry"]["coordinates"]]) for f in fs]
        _c["p"] = [f.get("properties") or {} for f in fs]; _c["t"] = STRtree(_c["g"])
        _c["r"] = [(g, fh) for g, fh in roads if fh not in ka.SKIP_FH]; _c["rt"] = STRtree([g for g, _ in _c["r"]])
    g = LineString(o); m = g.interpolate(0.5, normalized=True)
    near = _c["p"][int(_c["t"].nearest(m))]
    if kind in ("traced", "block loop"):
        pr = dict(near)
    else:
        fh = _c["r"][int(_c["rt"].nearest(m))][1]
        pr = {"road": "lane" if fh == 7 else {1: "main", 2: "collector", 3: "local"}[ka.road_rank(fh)], "source": "street offset",
              "areas": near.get("areas", ""), "shape": "regular"}
    pr["length_m"] = round(g.length, 1)
    return pr


def main(a):
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    traced = ka.read_kerbs(a[0])
    lots = [g for g in kr.load_faces(a[1]) if g.geom_type == "Polygon"]
    roads = ka.load_roads(a[2])
    import glob, os
    from shapely.geometry import shape
    seen = set()
    for fn in sorted(glob.glob(os.path.join(a[2], "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            if pr.get("roadontype") in (2, 3) and f.get("geometry") and pr.get("OBJECTID") not in seen:
                seen.add(pr.get("OBJECTID")); g = shape(f["geometry"])
                BRIDGES.extend(q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString")
    area = None
    global LOT_GUIDE
    LOT_GUIDE = "--lot-guide" in a
    if "--box" in a:
        i = a.index("--box"); area = box(*map(float, a[i + 1:i + 5]))
    elif "--traced-only-area" in a:
        area = ka.traced_area(ka.Kerbs(traced))
    st = {}
    if "--no-untangle" not in a:
        traced = untangle(traced, st)
    if LOT_GUIDE:
        traced = lot_drift(traced, lots, roads, st, area)
    out = build(traced, lots, roads, area, st)
    loops = [o for o in out if np.hypot(*(o[0] - o[-1])) < 0.5]
    if "--loops" not in a:
        out = fill(traced, [o for o in out if np.hypot(*(o[0] - o[-1])) < 0.5],
                   [g for g, fh in roads if fh not in ka.SKIP_FH], area, st)
        n_tr = len(out) - st["fill_pieces"]; n_fi = len(out)
        out = guide(out, loops, [g for g, fh in roads if fh not in ka.SKIP_FH], st)   # no join across any street, lanes included
        kind = ["traced"] * n_tr + ["block fill"] * (n_fi - n_tr) + ["block guide"] * (len(out) - n_fi)
        if "--no-soften" not in a:
            out = [soften(o) for o in out]
        if "--no-untangle" not in a:
            tr_t = STRtree([LineString(o) for o, k in zip(out, kind) if k == "traced"])
            out = final_clean(out, st)
            # ends the clean-up opened (a jog or stub taken out at a corner) are joined again by the same rules, then checked again
            st2 = {}; n0 = len(out)
            out = guide(out, loops, [g for g, fh in roads if fh not in ka.SKIP_FH], st2)
            out = out[:n0] + [soften(o) for o in out[n0:]]
            st["reguide_closed"] = st2.get("guide_closed", 0)
            st3 = {}; out = final_clean(out, st3); st["reclean"] = sum(v for v in st3.values())
            # version d (Jacky 7 Nov 2026 via the kerb reviewer: X crossings at corners, knots, hooks, doubles, open corners):
            # crossings and T's become round corners, kerbs across a street go, open corners and short breaks are joined,
            # hooks and doubles are cut; the same shapes kerbreview.py fails
            streets = [g for g, fh in roads if fh not in ka.SKIP_FH]
            out = corners(out, streets, st)
            out = mouths(out, [g for g, fh in roads if fh not in ka.SKIP_FH and fh != 7], st, [g for g, fh in roads if fh == 9])
            out = gapjoin(out, streets, st)
            st4 = {}; out = corners(out, streets, st4); st["corners2"] = {k: v for k, v in st4.items() if v}
            out = unwobble(out, st)
            out = unhook(out, st)
            out = tidy(out, st)
            if "--keep-motorway" not in a:
                out = no_motorway(out, roads, st)
            # a cleaned line is a traced kerb when its middle still lies on one, else an added piece
            kind = ["traced" if len(tr_t.query(LineString(o).interpolate(0.5, normalized=True), predicate="dwithin", distance=0.3))
                    else "block guide" for o in out]
    else:
        kind = ["block loop"] * len(out)
    feats = [{"type": "Feature", "properties": props(o, k, a[0], roads),
              "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(x, y)] for x, y in o]}}
             for o, k in zip(out, kind)]
    json.dump({"type": "FeatureCollection", "features": feats}, open(a[3], "w"))
    print("RESULT", json.dumps(st), len(feats))


if __name__ == "__main__":
    main(sys.argv[1:])
