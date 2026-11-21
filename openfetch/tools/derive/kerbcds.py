#!/usr/bin/env python3
"""Cul-de-sac kerbs as their own line (kerb scenario 9, 21 Nov 2026). kerblot.py rings a whole block and keeps it only when every
side passes, so a dead-end street inside a block that fails on another side (bush, rail, a lane, no measure) stays blank: 42 km of
the top-10 street-side gap sits on 327 dead-end streets (measure nsw-2026-11-20-c). KN8 (derive c52cf1f) let such blocks through the
inlet gate and won 2 blocks, because the other gates still refused them. Here the cul-de-sac is drawn on its own, from the land:
  1. stem = the named street (fh 2-6, on the ground) from its dead end back to the first junction, at most STEM_MAX m.
  2. reserve = the land between lots (cadastre) within ZONE m of the stem, strips under LANE_W wide (walkways) taken off, the piece
     holding the stem's end. It must close round the end inside the zone (an open walkway or park beyond is refused).
  3. footpath width d = the road-most continuous chain of LiDAR kerb drops on the reserve's front (kerb_chain), seen along SEEN_MIN
     of it with no long gap or jump. No measure, no kerb (never guessed).
  4. kerb = the reserve's edge pushed in by d; only the part nearer the stem than any other centreline is kept; each end then runs on
     round the corner return until it meets an existing kerb (JOIN m) or the corner straightens (RETURNS; off stops at the mouth).
  5. parts already kerbed (within JOIN m of an existing kerb) are cut out; pieces under MIN_LEN m are dropped; every piece keeps
     CL_CLEAR m from every centreline except the stem's last TIP m (a centreline drawn to the bulb's middle or edge).

    python3 kerbcds.py roads_dir lots_dir grids_dir kerbs.geojson[.gz][,council.json@4283,...] out.geojson [--why why.json] [--cells cells.txt]
        [--photo photo_cache_dir] [--igrids intensity_dir] [--rise]   (kerbcdscut.py: cut stretches not beside paving / off the kerb rise)
    python3 kerbcds.py --selftest
roads_dir / lots_dir: <x>_<y>.json in MGA56 (EPSG 7856) from the multiCRS layers (P-0244: the plain layers answer GDA94 numbers);
kerbs: every published and council kerb in lon/lat (council files from GDA94 portals with @4283); out in lon/lat.
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
SMOOTH = 2           # profiles either side joined in a median before reading drops (Parramatta known answer, 21 Nov 2026)
DISH = None          # off: a drop whose road side rises back by DISH of it within 1.5-2.5 m read as a dish invert (H7 at 0.8 cut known-answer hits 71->43 %)
CAND_FLAT = 0.08     # m: each side of a candidate drop lies within this of a line (kerbpcw.P_FLAT 0.05 for the strongest drop)
SKIP = 0.5           # chain cost of a sample with no reading used
RESTART = 3.0        # chain cost of starting a new chain (four agreeing readings at least pay for it)
JUMP_W = 1.0         # chain cost per m of width change between readings
DROP_W = 2.0         # chain reward per m of kerb drop
OUT_W = 0.05         # chain reward per m out from the lot front (the kerb is the road-side step)
ROW, ROAD_ROW = 1.0, 0.5   # m further out, share of readings: a road-side row of drops that replaces the chain
HOP, HOP_SKIP = 0.6, 0.3     # m: most width change between neighbouring readings, plus this per skipped sample
STRAY = 6.0          # m of other front facing the stem allowed apart from the cul-de-sac's own run
MOUTH = 25.0         # m: each end of the cul-de-sac's front lies this near its junction
SEEN_MIN = float(os.environ.get('CDS_SEEN', 0.4))   # share of the cul-de-sac's samples with a width
GAP_MAX = int(os.environ.get('CDS_GAP', 10))       # samples (20 m) without a width bridged along the same kerb; a longer gap is not guessed
SEEN_ONLY = os.environ.get('CDS_SEEN_ONLY', '1') == '1'   # draw only where a kerb drop was read (H9); off: bridge and guess the returns
SEEN_BRIDGE = int(os.environ.get('CDS_BRIDGE', 10))  # samples without a reading drawn between two reads (H9b: = GAP_MAX, so only unread ends go; 2 cut 60 %, H9)
SEEN_TOL = 0.6       # m: a corner-return sample counts as read when a candidate drop lies this near its width
JUMP = 0.5           # m the width may change between two samples 2 m apart
CW_MIN = 2.5         # m: half a carriageway at least between the two kerbs (kerblot.CW_MIN)
JOIN = 1.5           # m: an end this near an existing kerb meets it; a kerb this near an existing one is already there
RETURN_MAX = 15.0    # m an end may run on round the corner return
RETURNS = True       # ends run round the corner return; False stops them at the reserve mouth (H5, refused in blind review 21 Nov: ends stopped 5-20 m short)
STRAIGHT = 4.0       # degrees: the corner has straightened when the line turns less than this over 3 m
LOOP_MAX = 15.0      # m: loops this short in the offset line are trimmed (notches, splays)
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


def _dish(h, f, drop):
    """True where the ground past a drop's foot f rises back by DISH of the drop within 1.5-2.5 m: a V-shaped dish drain (round 7)."""
    if DISH is None:
        return False
    s = int(round(1.5 / kpw.STEP_D)); e = int(round(2.5 / kpw.STEP_D)); g = int(round(0.5 / kpw.STEP_D))
    foot, back = h[f:f + g], h[f + s:f + e]
    if np.isfinite(foot).sum() < 2 or np.isfinite(back).sum() < 2:
        return False
    return float(np.nanmedian(back) - np.nanmedian(foot)) >= DISH * drop


def drops(h, t, lo, hi, flat=None):
    """Every kerb-like drop in one profile h(t) as (distance, drop), not only the strongest (kerbpcw.prof_step's line fit each
    side); drops within 0.5 m keep the strongest."""
    w = int(round(kpw.P_W / kpw.STEP_D)); r = int(round(kpw.DROP_RUN / kpw.STEP_D)); u = np.arange(w) * kpw.STEP_D
    out = []
    for e in range(max(w, int(lo / kpw.STEP_D)), min(len(t) - w - r, int(hi / kpw.STEP_D) + 1)):
        a, b = h[e - w:e], h[e + r:e + r + w]
        ma, mb = np.isfinite(a), np.isfinite(b)
        if ma.sum() < w / 2 or mb.sum() < w / 2:
            continue
        pa, pb = np.polyfit(u[ma], a[ma], 1), np.polyfit(u[mb], b[mb], 1)
        if max(abs(pa[0]), abs(pb[0])) > kpw.P_SLOPE:
            continue
        fl = CAND_FLAT if flat is None else flat
        if np.ptp(a[ma] - np.polyval(pa, u[ma])) > fl or np.ptp(b[mb] - np.polyval(pb, u[mb])) > fl:
            continue
        drop = np.polyval(pa, kpw.P_W + kpw.DROP_RUN / 2) - np.polyval(pb, -kpw.DROP_RUN / 2)
        if kpw.DROP_MIN <= drop <= kpw.DROP_MAX and not _dish(h, e + r, drop):
            out.append((t[e] + kpw.DROP_RUN / 2, float(drop)))
    groups = []
    for p, d in out:   # neighbouring window positions see the same step: one reading each, at the middle of its strongest
        if groups and p - groups[-1][-1][0] <= kpw.STEP_D * 1.5:
            groups[-1].append((p, d))
        else:
            groups.append([(p, d)])
    keep = []
    for g in groups:
        best = max(d for _, d in g)
        keep.append((float(np.median([p for p, d in g if d >= best - 0.02])), best))
    res = []
    for p, d in sorted(keep, key=lambda x: -x[1]):
        if all(abs(p - q) > 0.5 for q, _ in res):
            res.append((p, d))
    return sorted(res)


def chain(cands, gap=None):
    """The kerb through a run of samples as continuous chains (21 Nov 2026, scenario 9): a profile often shows two steps (the kerb,
    and a fence footing or driveway lip on the lot side), and the strongest is not always the kerb, so a window of strongest
    readings never agrees. Shortest path over every sample's candidate drops: a sample left out costs SKIP, a width change costs
    JUMP_W per m (never more than HOP m between neighbours plus HOP_SKIP m per skipped sample), a stronger drop and the road-side
    step cost less, and a new chain (a corner, or the kerb found again after a long gap) costs RESTART, so a stray reading or two
    is never a chain. Returns widths (nan where left out)."""
    gap = GAP_MAX if gap is None else gap
    n = len(cands); F = [dict() for _ in range(n)]; G = np.zeros(n + 1); Gp = [None] * (n + 1)
    for i in range(n):
        for c, (p, d) in enumerate(cands[i]):
            own = -DROP_W * d - OUT_W * p
            top = (G[i] + RESTART + own, ("G", i))
            for k in range(1, gap + 2):
                j = i - k
                if j < 0:
                    break
                for cj, (cost, _) in F[j].items():
                    dp = abs(p - cands[j][cj][0])
                    if dp <= HOP + HOP_SKIP * (k - 1) and (v := cost + SKIP * (k - 1) + JUMP_W * dp + own) < top[0]:
                        top = (v, ("F", j, cj))
            F[i][c] = top
        G[i + 1], Gp[i + 1] = G[i] + SKIP, None
        for c, (cost, _) in F[i].items():
            if cost < G[i + 1]:
                G[i + 1], Gp[i + 1] = cost, (i, c)
    out = np.full(n, np.nan); i = n
    while i > 0:
        if Gp[i] is None:
            i -= 1; continue
        cur = Gp[i]
        while True:
            out[cur[0]] = cands[cur[0]][cur[1]][0]; back = F[cur[0]][cur[1]][1]
            if back[0] == "G":
                i = back[1]; break
            cur = (back[1], back[2])
    return out


def kerb_chain(cands, road_row=None):
    """The road-most consistent chain (hard rule, kerb lead 21 Nov 2026): a kerb drops down towards the road and is the row
    furthest out; a fence footing, garden edge or driveway lip lies on the lot side. After the cheapest chain, the chain through
    only the drops at least ROW m further out replaces it when it holds ROAD_ROW of its readings; repeated until none does."""
    cur = chain(cands)
    for _ in range(3):
        if not np.isfinite(cur).any():
            break
        ok = np.isfinite(cur); ref = np.interp(np.arange(len(cur)), np.flatnonzero(ok), cur[ok])
        out = [[c for c in cs if c[0] >= ref[i] + ROW] for i, cs in enumerate(cands)]
        nxt = chain(out)
        if np.isfinite(nxt).sum() < (ROAD_ROW if road_row is None else road_row) * ok.sum():
            break
        cur = nxt
    return cur


def candidates(ground, P, N, R, ok, flat=None, smooth=None):
    """Every sample's candidate kerb drops (distance on the LiDAR traces' footing, drop), none where not ok."""
    out = [[] for _ in range(len(P))]
    if not ok.any() or not ground.covers(P[ok]):
        return out
    t = np.arange(0.0, D_MAX + 1.5, kpw.STEP_D)
    with np.errstate(all="ignore"):
        H = np.nanmedian(kpw.profiles(ground, P[ok], N[ok], t), axis=0)
        sm = SMOOTH if smooth is None else smooth
        if sm:   # the median of a few neighbouring profiles: noise and one parked car fall out, a jog in the lot front stays local
            H = np.stack([np.nanmedian(H[max(0, k - sm):k + sm + 1], axis=0) for k in range(len(H))])
    for k, i in enumerate(np.flatnonzero(ok)):
        hi = min(D_MAX, R[i] - CW_MIN) - kpw.P_SHIFT
        out[i] = [(p + kpw.P_SHIFT, d) for p, d in drops(H[k], t, D_MIN - kpw.P_SHIFT, hi, flat)] if hi > D_MIN else []
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
    if not RETURNS:
        return idx, ["mouth", "mouth"]
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


def unloop(V, most=LOOP_MAX):
    """An offset line folds into a small loop where the lot front turns inwards (a notch, a splay at the mouth); a real kerb runs
    straight across it, as an offset curve is trimmed: each loop of `most` m or less is cut at its crossing. None when a larger
    loop is left (the line really crosses itself)."""
    V = [tuple(v) for v in V]
    for _ in range(50):
        segs = [LineString([V[k], V[k + 1]]) for k in range(len(V) - 1)]
        t = STRtree(segs); hit = None
        for a, g in enumerate(segs):
            for b in sorted(int(x) for x in t.query(g)):
                if b > a + 1 and g.intersects(segs[b]):
                    hit = (a, b, g.intersection(segs[b])); break
            if hit:
                break
        if hit is None:
            return np.array(V)
        a, b, x = hit
        if LineString(V[a + 1:b + 1]).length > most or x.geom_type != "Point":
            return None
        V = V[:a + 1] + [x.coords[0]] + V[b + 1:]
    return None


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


def widths_along(ground, P, N, R, ok, idx, n):
    """Footpath width at each cul-de-sac sample: the road-most continuous chain of LiDAR kerb drops (kerb_chain) where it covers
    SEEN_MIN of the cul-de-sac with no gap over GAP_MAX samples and no jump over JUMP; otherwise no kerb (runs measured on their
    own drew odd shapes in blind pack 1). Returns (widths, how, detail) or (None, why, detail)."""
    cands = candidates(ground, P, N, R, ok)
    dd = kerb_chain([cands[i] for i in idx]); seen_i = np.isfinite(dd); det = {"seen": round(float(seen_i.mean()), 2)}
    det["_seen"], det["_cands"] = seen_i, cands
    gap = max((len(list(g)) for v, g in itertools.groupby(seen_i) if not v), default=0)
    if seen_i.mean() >= SEEN_MIN and gap <= GAP_MAX:
        dd = np.interp(np.arange(len(idx)), np.flatnonzero(seen_i), dd[seen_i])
        dd = np.array([np.median(dd[max(0, k - 1):k + 2]) for k in range(len(dd))])
        if np.max(np.abs(np.diff(dd))) <= JUMP:
            return dd, "chain", det
    if seen_i.mean() < SEEN_MIN:
        return None, "kerb not seen in the LiDAR along most of the cul-de-sac", det
    if gap > GAP_MAX:
        return None, "kerb not seen along part of the cul-de-sac", det
    return None, "footpath width jumps along the cul-de-sac", det


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
    dd, how, det = widths_along(ctx["ground"], P, N, R, ok, idx, n)
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
    read = dict(zip(idx, det.pop("_seen"))); cands = det.pop("_cands")
    idx, ends = extend(idx, n, K, seen, near)
    pieces = []
    for run in read_runs(idx, read, cands, d) if SEEN_ONLY else [idx]:
        V = unloop(K[run])
        if V is None:
            return [], "kerb crosses itself", det
        bad = clear_of(V, st, ot, others)
        if bad is not None:
            return [], "kerb runs within 2 m of a centreline", {**det, "at": [round(x, 1) for x in V[bad]]}
        pieces += kerb_pieces(V, near)
    if not pieces:
        return [], "kerb already there" if not SEEN_ONLY else "kerb not seen along enough of the cul-de-sac", det
    det["ends"] = ends
    return pieces, None, det


def read_runs(idx, read, cands, d):
    """Runs of idx where the LiDAR read a kerb (the chain on the cul-de-sac, a drop within SEEN_TOL of the width on a corner
    return), gaps of SEEN_BRIDGE samples or fewer between reads joined (round 9: guessed stretches drew tips past the road end,
    hooks and spikes)."""
    ok = [bool(read[i]) if i in read else any(abs(p - d[i]) <= SEEN_TOL for p, _ in cands[i]) for i in idx]
    on = np.flatnonzero(ok)
    for a, b in zip(on[:-1], on[1:]):
        if b - a - 1 <= SEEN_BRIDGE:
            ok[a:b] = [True] * (b - a)
    return [[idx[k] for k in range(a, b + 1)] for a, b in keep_runs_lin(ok)]


def keep_runs_lin(flags):
    out, a = [], None
    for k, f in enumerate(list(flags) + [False]):
        if f and a is None:
            a = k
        elif not f and a is not None:
            out.append((a, k - 1)); a = None
    return out


def lines_mga(paths):
    """Kerb lines in MGA56 from lon/lat files; "file@4283" reads a GDA94 portal's file (the datum step is applied, P-0216)."""
    from pyproj import Transformer
    out = []
    for item in paths:
        pth, _, epsg = item.partition("@")
        T = Transformer.from_crs(int(epsg or 4326), 7856, always_xy=True)
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
    import kerbcdscut as kcut
    photo = kcut.Photo(a[a.index("--photo") + 1]) if "--photo" in a else None
    inten = kcut.igrids(a[a.index("--igrids") + 1]) if "--igrids" in a else None
    cal = kcut.cell_cal(roads, inten) if inten else None
    from pyproj import Transformer
    B = Transformer.from_crs(7856, 4326, always_xy=True)
    feats, why = [], collections.Counter(); whys = []
    for st in stems(roads):
        x, y = st["tip"].coords[0]
        if cells is not None and (int(x // 1000), int(y // 1000)) not in cells:
            continue
        pieces, w, det = one(st, ctx)
        if pieces and (photo or inten or "--rise" in a):
            pieces, det["cut_m"] = kcut.apply(pieces, st["stem"], st["tip"], photo, inten, MIN_LEN, cal, ctx["ground"])
            w = w if pieces else "cut: not beside paving or off the road edge"
        why[w or "drawn"] += 1
        whys.append({"tip": [round(x, 1), round(y, 1)], "name": st["name"], "why": w or "drawn", **det})
        for k, q in enumerate(pieces):
            ll = [list(map(lambda v: round(v, 7), B.transform(*v))) for v in q]
            feats.append({"type": "Feature", "properties": {"id": f"C{int(x)}_{int(y)}-{k}", "street": st["name"], **det},
                          "geometry": {"type": "LineString", "coordinates": ll}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    if "--why" in a:
        json.dump(whys, open(a[a.index("--why") + 1], "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
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
    z = unloop(np.array([(0, 0), (10, 0), (12, 2), (11, 3), (11, -1), (20, 0)]))     # a small fold is trimmed at its crossing
    assert z is not None and LineString(z).is_simple and len(z) == 5, z
    assert all(abs(c[1]) > 6.0 for c in L.coords)                                  # never onto the through street's carriageway
    kerb = [LineString([(-100, 7), (-9, 7)]), LineString([(9, 7), (100, 7)])]        # existing kerbs along the through street
    ctx["kerb_t"] = STRtree(kerb)
    pieces, why, det = one(S[0], ctx)
    assert why is None and det["ends"] == ["join", "join"], det
    global RETURNS
    RETURNS = False
    assert one(S[0], ctx)[2]["ends"] == ["mouth", "mouth"]
    RETURNS = True
    ctx["ground"] = _Fake(res, 0.0)                                                # no step: not measured, nothing drawn
    assert one(S[0], ctx)[1].startswith("kerb not seen")
    walk = lots[3].difference(box(-2, 60, 2, 120))                                 # a 4 m walkway past the bulb: still closed
    ctx2 = {**ctx, "lots": lots[:3] + [walk], "lots_t": STRtree(lots[:3] + [walk]), "ground": _Fake(res, 3.0), "kerb_t": None}
    assert one(S[0], ctx2)[1] is None, one(S[0], ctx2)[1]
    park = lots[3].difference(box(-30, 60, 30, 120))                               # a 60 m open reserve past the end: refused
    ctx3 = {**ctx2, "lots": lots[:3] + [park], "lots_t": STRtree(lots[:3] + [park])}
    assert one(S[0], ctx3)[1] == "reserve runs on past the street end", one(S[0], ctx3)[1]
    rng = np.random.default_rng(5)                                                 # two rows: a 20 cm lip at 1.2 m, the 12 cm kerb at 3.0 m
    cands = [[(1.2 + rng.normal(0, 0.05), 0.20), (3.0 + rng.normal(0, 0.05), 0.12)] if k % 3 else [(3.0, 0.12)] for k in range(30)]
    cands[7] = [(5.5, 0.3)]                                                        # a stray reading in the road
    got = kerb_chain(cands)
    assert np.nanmedian(got) > 2.8 and np.isfinite(got).mean() > 0.9 and not abs(got[7] - 5.5) < 1, got
    t = np.arange(0.0, 8.5, kpw.STEP_D)
    h = np.where(t < 1.2, 0.2, 0.0) + np.where(t < 3.0, 0.0, -0.12)               # the drops() reader sees both steps
    assert [round(p, 1) for p, _ in drops(h, t, 0.75, 6.75)] == [1.2, 3.0], drops(h, t, 0.75, 6.75)
    rd = {i: f for i, f in enumerate([0, 0, 1, 1, 0, 0, 0, 1, 1, 0])}                # unread ends trimmed, an inner gap bridged
    assert read_runs(list(range(10)) + [10, 11], rd, [[]] * 10 + [[(3.0, 0.1)], [(9.0, 0.1)]], [3.0] * 12) == [list(range(2, 11))]
    print("kerbcds selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(selftest() if a == ["--selftest"] else main(a))
