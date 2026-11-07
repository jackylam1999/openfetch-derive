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
        for k in edge_ids:
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
    if "--box" in a:
        i = a.index("--box"); area = box(*map(float, a[i + 1:i + 5]))
    elif "--traced-only-area" in a:
        area = ka.traced_area(ka.Kerbs(traced))
    st = {}
    if "--no-untangle" not in a:
        traced = untangle(traced, st)
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
