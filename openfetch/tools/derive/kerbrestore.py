"""Win back kerb lines dropped whole (card KN23, 20 Nov 2026; Jacky 15:30Z: "for 2D it does not have to be that precise, only odd shapes
fail"; case P-0237). Lines were dropped by batch because they sat 2-3 m inside the road or behind the verge, and by the old bar that was a
fail. Under the 20 Nov bar (about 3 m off is fine in 2D; odd shapes fail) most of those lines are fine, so each dropped line is judged
again, side by side, and only the odd piece is cut. Cuts are made only where a real kerb turns: at a side-street or lane mouth, and each
cut end is finished with a kerb return into that street (quadratic fillet, radius up to 4 m) so no end is left free.

  1. mouths: the line crosses a street centreline (ground level, street or lane class, not along the line's own street): cut the
     mouth (half the crossed street's class width, as kerbgrid.HALF_W, stretched for a slanting crossing) and add a return at each end;
  2. block side = the stretch between two mouths (or a line end). Every metre of it is measured against the cadastre:
       hug  = nearer than HUG_M to a lot (kerb along a wall, a lane or in a yard; Erskineville n18, n09 on the 20 Nov labels);
       far  = farther than FAR_M from any lot (kerb in the carriageway more than about 3 m past a normal footpath, a mall; n15, n17);
     a side is left out whole when it hugs lots (within 0.5 m of a lot line for 25 m or more), sits in the carriageway (over 8 m from any lot and
     within 3 m of a street centreline for over 15 % of it) or is not along a road (over 10 % of it farther than the street's half width + 6 m)
     (blank beats odd). Nothing measured the other way (LiDAR needs a grid, the cadastre is everywhere), so the review does the rest;
  3. a side shorter than MIN_SIDE is left out.
  4. MID-SIDE CUT (card KN24, 20 Nov; case P-0239): a long side left out whole for one local bad stretch (a hugging run, a stretch in the
     carriageway or away from the road) is cut at that stretch instead: the bad metres (padded PAD_M each end, runs closer than JOIN_M
     joined) are removed and each good piece of MIN_SUB m or more is kept. A mid cut end is allowed only where a real kerb can finish
     there (kerb lead, 20 Nov: pack1 failed 11 of 30 on hooks mid-street): at a side street or lane (a street other than the line's own passes
     within its half width + MOUTH_NEAR m at 25 degrees or more: the end gets a kerb return into it, as at a mouth) or onto another kerb line
     within JOIN_KERB_M (the end is left touching it). A piece with an end that can do neither is left out, so a side whose bad stretch is
     not near a street or another kerb stays out whole. A side with more than MAX_CUT_SHARE of it bad stays out whole. Sides that already
     passed (kept) are never touched by this step.
     CORNERS (scenario 11, 21 Nov; the kerb lead's pack2 held 27 odd of 30 kept, "hooks at the corner"): 58 of 64 mid cut ends sat where the
     line itself turns its own block corner (45 degrees or more within CORNER_M m into the removed stretch), so the "side street" was the very
     street the line turns into and the 3 m return curled back on it. Such an end now finishes at the corner's own geometry (CORNER_MODE
     "entry": the piece stops where the line starts to turn, no return; "own": the line's own corner is kept up to where it comes within
     CORNER_LOT_M of a lot), never with an added curl. A return into a side street is made only into a real gap between lots (the return and
     MOUTH_CLEAR m past it along the side street touch no lot), else the end cannot finish there.
Kept geometry that was never cut is the published line, byte for byte (no smoothing, no moves).

    python3 kerbrestore.py lines.geojson lots_dir roads_dir out.geojson report.json
    python3 kerbrestore.py --selftest
lots_dir and roads_dir hold <x>_<y>.json km-square cells from kerbgrid-run/fetchin.py (MGA56 metres, lots plus 300 m margin).
"""
import glob, gzip, json, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

HALF_W = {1: 9.0, 2: 8.0, 3: 7.0, 4: 6.5, 5: 5.5, 6: 4.5, 7: 3.0}   # as kerbgrid.HALF_W; paths (8-11) are not streets
HUG_M, HUG_RUN, FAR_M, CARRIAGE_M = 0.5, 25.0, 8.0, 3.0   # kerb lead 20 Nov: the first rule left out 24 good sides of 28
AWAY_M, ROAD_SHARE = 6.0, 0.9
BAD_SHARE, MIN_SIDE = 0.15, 15.0
RADIUS, SAME_ST_DEG, MERGE_M = 4.0, 25.0, 6.0
MIN_SUB, PAD_M, JOIN_M, RUN_M = 20.0, 2.0, 10.0, 6.0   # mid-side cut: smallest kept piece, margin round a bad stretch, join gap, shortest far/away stretch
MAX_CUT_SHARE, MID_R, MOUTH_NEAR, JOIN_KERB_M = 0.4, 3.0, 3.0, 1.5
CORNER_M, CORNER_DEG, STRAIGHT_DEG, CORNER_LOT_M, MOUTH_CLEAR, JUNCTION_M, POST_M, CORNER_R = 12.0, 45.0, 5.0, 1.0, 6.0, 15.0, 12.0, 4.0
CORNER_MODE = os.environ.get("KERB_CORNER_MODE", "build")
ARM_CORNER = os.environ.get("KERB_ARM_CORNER", "1") == "1"   # round 4: corners from the line's own two straights
TIER_A_SHARE, TIER_A_RUN = 0.03, 8.0   # tier A: nearly nothing flagged; tier B: kept but with up to BAD_SHARE flagged (reviewed on its own)


def load_streets(roads_dir):
    """[(LineString, functionhierarchy)] of ground-level streets and lanes (fh 1-7), each road segment once."""
    out, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(roads_dir, "*.json"))):
        for f in json.load(open(fn))["features"]:
            p = f.get("properties") or {}
            oid = p.get("OBJECTID", p.get("objectid"))
            if oid in seen or not f.get("geometry") or p.get("roadontype", 1) != 1 or p.get("functionhierarchy") not in HALF_W:
                continue
            seen.add(oid)
            g = shape(f["geometry"])
            out += [(q, p["functionhierarchy"]) for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString" and q.length > 0]
    return out


def load_lots(lots_dir):
    lots, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(lots_dir, "*.json"))):
        for f in json.load(open(fn))["features"]:
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if g.wkb in seen:
                continue
            seen.add(g.wkb)
            lots += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]
    return lots


def tangent(L, s, h=2.5):
    a, b = np.array(L.interpolate(max(0.0, s - h)).coords[0]), np.array(L.interpolate(min(L.length, s + h)).coords[0])
    v = b - a
    n = np.hypot(*v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def mouths(L, streets, tree):
    """Cut spans [(s0, s1, point, u, hw)] where L crosses a street other than its own: merged within MERGE_M, u = the crossed street's
    direction pointing away from the street L runs beside (None when that street is not found)."""
    found = []
    for j in tree.query(L):
        st, fh = streets[int(j)]
        x = L.intersection(st)
        for p in getattr(x, "geoms", [x]):
            if p.is_empty or p.geom_type != "Point":
                continue
            s = L.project(p)
            t, c = tangent(L, s), tangent(st, st.project(p))
            ang = np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, c))))))
            if ang < SAME_ST_DEG:
                continue                      # a shallow crossing is the line's own street curving, not a mouth
            found.append((s, p, fh, c, ang, int(j)))
    found.sort(key=lambda r: r[0])
    out = []
    for s, p, fh, c, ang, j in found:
        hw = min(HALF_W[fh] / max(np.sin(np.radians(ang)), 0.4), 2.5 * HALF_W[fh])
        if out and s - out[-1][0] < MERGE_M + hw:
            if hw > out[-1][4]:
                out[-1] = (s, out[-1][1], out[-1][2], out[-1][3], hw, out[-1][5])
            continue
        out.append((s, p, fh, c, hw, j))
    res = []
    for s, p, fh, c, hw, j in out:
        near = [k for k in tree.query(p.buffer(HALF_W[1] + 12.0)) if int(k) != j]
        u = None
        if near:
            k = min(near, key=lambda k: streets[int(k)][0].distance(p))
            m = streets[int(k)][0]
            if m.distance(p) < 30.0:
                q = np.array(m.interpolate(m.project(p)).coords[0])
                away = np.array(p.coords[0]) - q
                u = c if float(np.dot(c, away)) >= 0 else -c
        res.append((max(0.0, s - hw), min(L.length, s + hw), p, u, hw))
    return res


def arc(L, s_edge, direction, u, hw, room):
    """Kerb return at a cut end: Q is the mouth edge on the kerb (distance s_edge along L); the kerb leaves Q along direction (+1 or -1
    along L, away from the mouth) and the return turns into the side street along u. Quadratic fillet, radius up to RADIUS (not more
    than the street's half width or the room left on the side); points run from the kerb tangent point to the street."""
    r = min(RADIUS, hw, room)
    q = np.array(L.interpolate(s_edge).coords[0])
    a = np.array(L.interpolate(s_edge + direction * r).coords[0])
    b = q + u * r
    return r, [tuple(map(float, (1 - k) ** 2 * a + 2 * (1 - k) * k * q + k ** 2 * b)) for k in np.linspace(0.0, 1.0, 9)]


def sides_of(L, cuts):
    """[(s0, s1, cut_before, cut_after)] stretches of L between cut spans."""
    out, s = [], 0.0
    prev = None
    for c in cuts:
        if c[0] > s:
            out.append((s, c[0], prev, c))
        s, prev = c[1], c
    if s < L.length:
        out.append((s, L.length, prev, None))
    return out


def profile(L, s0, s1, lots, lt, streets, st_tree):
    """Per metre of [s0, s1]: (S, hug, far, away) boolean arrays (hug is raw: every metre within HUG_M of a lot line)."""
    S = np.arange(s0 + 0.5, s1, 1.0)
    P = shapely.points(np.array([L.interpolate(s).coords[0] for s in S]))
    d = shapely.distance(np.array(lots, dtype=object)[lt.nearest(P)], P) if len(lots) else np.full(len(S), 99.0)
    j = st_tree.nearest(P)
    sg = np.array([g for g, _ in streets], dtype=object)[j]
    dc = shapely.distance(sg, P)
    hw = np.array([HALF_W[fh] for _, fh in streets])[j]
    return S, d < HUG_M, (d > FAR_M) & (dc < CARRIAGE_M), dc > hw + AWAY_M


def longest(mask):
    run = best = 0
    for b in mask:
        run = run + 1 if b else 0
        best = max(best, run)
    return best


def flags(L, s0, s1, lots, lt, streets, st_tree):
    """Per metre judgement of [s0, s1] -> (share flagged, longest flagged stretch, why).
    hug  = within HUG_M of a lot line (cadastre), flagged only as a stretch of HUG_RUN m or more (a wall, lane or yard edge);
    far  = farther than FAR_M from any lot AND within CARRIAGE_M of a street centreline (the kerb is in the carriageway or a mall);
    away = farther than AWAY_M past the nearest street's half width: not along a road at all (a diagonal through trees, a yard);
           a side with over AWAY_SHARE of its length away is left out whole (kerb lead, 20 Nov)."""
    if len(np.arange(s0 + 0.5, s1, 1.0)) < 3:
        return 0.0, 0.0, None
    S, hug, far, away = profile(L, s0, s1, lots, lt, streets, st_tree)
    best = longest(hug)
    why = None
    if best >= HUG_RUN:
        why = "hugs lots"
    elif far.mean() > BAD_SHARE:
        why = "in the carriageway"
    elif away.mean() > 1 - ROAD_SHARE:
        why = "away from the road"
    bad = (hug if best >= HUG_RUN else np.zeros(len(S), bool)) | far | away
    return float(bad.mean()), float(max(best if best >= HUG_RUN else 0, 0)), why


def runs_of(mask):
    """[(i0, i1)] of consecutive True entries (i1 exclusive)."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def bad_spans(L, s0, s1, lots, lt, streets, st_tree):
    """The bad stretches of one side as [(a, b)] metres along L, padded and joined, or None when the side cannot be cut (over MAX_CUT_SHARE bad).
    A hug stretch counts from HUG_RUN m; a far or away stretch from RUN_M m (a single wet metre at a mouth is not a stretch)."""
    S, hug, far, away = profile(L, s0, s1, lots, lt, streets, st_tree)
    bad = np.zeros(len(S), bool)
    for m, need in ((hug, HUG_RUN), (far, RUN_M), (away, RUN_M)):
        for i0, i1 in runs_of(m):
            if i1 - i0 >= need:
                bad[i0:i1] = True
    spans = []
    for i0, i1 in runs_of(bad):
        a, b = max(s0, S[i0] - 0.5 - PAD_M), min(s1, S[i1 - 1] + 0.5 + PAD_M)
        if spans and a - spans[-1][1] < JOIN_M:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    if not spans or sum(b - a for a, b in spans) > MAX_CUT_SHARE * (s1 - s0):
        return None
    return spans


def turn_deg(L, s, dr, t0):
    """Signed heading change (degrees) of L at s, walking dr (+1/-1), against t0."""
    t = tangent(L, s, 1.0) * dr
    return float(np.degrees(np.arctan2(t0[0] * t[1] - t0[1] * t[0], float(t0 @ t))))


def junction_near(p, streets, st_tree, reach=JUNCTION_M):
    """True when a street node where three or more street ends meet (a T or X junction) lies within reach m of p."""
    ends = []
    for j in st_tree.query(p.buffer(reach + 1.0)):
        g = streets[int(j)][0]
        ends += [g.coords[0], g.coords[-1]]
    E = np.array(ends) if ends else np.zeros((0, 2))
    q = np.array(p.coords[0])
    for e in E:
        if np.hypot(*(e - q)) <= reach and (np.hypot(*(E - e).T) < 1.0).sum() >= 3:
            return True
    return False


def turns_into_street(L, s, dr, streets, st_tree):
    """True when L at s (past the turn) runs along a street: a street centreline within its half width + AWAY_M, heading within SAME_ST_DEG."""
    s = min(max(s, 0.0), L.length)
    p, t = L.interpolate(s), tangent(L, s)
    for j in st_tree.query(p.buffer(HALF_W[1] + AWAY_M)):
        g, fh = streets[int(j)]
        if g.distance(p) <= HALF_W[fh] + AWAY_M:
            c = tangent(g, g.project(p))
            if np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, c)))))) < SAME_ST_DEG:
                return True
    return False


def extended(g, m):
    """g with its end segments run on straight by m metres (a centreline can stop a little short of the kerb line)."""
    c = np.array(g.coords)
    a, b = c[0] - (c[1] - c[0]) / max(np.hypot(*(c[1] - c[0])), 1e-9) * m, c[-1] + (c[-1] - c[-2]) / max(np.hypot(*(c[-1] - c[-2])), 1e-9) * m
    return LineString([tuple(a)] + [tuple(q) for q in c] + [tuple(b)])


WHY_BC = {}
OFFS = []


def why_none(k):
    WHY_BC[k] = WHY_BC.get(k, 0) + 1
    return None


def built_corner(L, s_edge, dr, streets, st_tree, lots, lt):
    """Scenario 11 round 2 (kerb lead, packA: ends stopped up to 8 m short of the corner, 5 odd free ends; corner curls 3 odd): finish a
    mid cut end as a real kerb corner. The kept straight runs on to the cross street's kerb and turns onto it with a CORNER_R m return.
    The cross street's kerb offset comes from this block, not a class width: the removed arm's lot line (its distance from the cross street's
    centreline less its own distance from the lots) less the footpath the kept arm measures (its median distance from the lots).
    -> (s on L where the kept line stops, [points of the run-on and return]) or None (no junction ahead, no removed arm along the cross
    street to measure, an offset outside 1.5 m .. the street's half width + 1.5 m, or new points that touch a lot)."""
    n = L.length
    sk = min(max(s_edge - dr * 12.0, 0.0), n)
    t = tangent(L, sk) * dr
    s_end = sk
    for k in np.arange(0.0, 14.01, 0.5):
        q = s_edge - dr * 12.0 + dr * k
        if not 0.0 <= q <= n:
            break
        if np.degrees(np.arccos(np.clip(float(np.dot(tangent(L, q, 1.0) * dr, t)), -1, 1))) > 8.0:
            break
        s_end = q
    P = np.array(L.interpolate(s_end).coords[0])
    ray = LineString([tuple(P - t * 20.0), tuple(P + t * 40.0)])      # the line may already have run past the mouth
    own_d, own_q, best = 1e9, None, None
    for j in st_tree.query(Point(P).buffer(45.0)):
        g, fh = streets[int(j)]
        c = tangent(g, g.project(Point(P)))
        ang = np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, c))))))
        if ang < SAME_ST_DEG:
            d = g.distance(Point(P))
            if d < own_d:
                own_d, own_q, g_own = d, np.array(g.interpolate(g.project(Point(P))).coords[0]), g
            continue
        if ang < CORNER_DEG:
            continue
        x = ray.intersection(extended(g, 10.0))
        for pt in getattr(x, "geoms", [x]):
            if not pt.is_empty and pt.geom_type == "Point":
                D = float(np.dot(np.array(pt.coords[0]) - P, t))
                if best is None or abs(D) < abs(best[0]):
                    best = (D, g, fh, tangent(g, g.project(pt)))
    if best is None or own_q is None:
        return why_none(1)
    nrm_hat = (P - own_q) / max(float(np.hypot(*(P - own_q))), 1e-9)
    D, g, fh, c = best
    reach = max(float(np.dot(np.array(q) - own_q, nrm_hat)) for q in g.coords)
    if reach < float(np.hypot(*(P - own_q))):
        return why_none(8)                       # the side street opens on the far side of the road (packB c07, c10, c12, c27, c29, c40): no corner on this kerb
    if not junction_near(Point(P + t * D), streets, st_tree):
        return why_none(6)                       # one street bending, not a junction: a return here would end mid-street
    nrm = P - own_q
    u = c if float(np.dot(c, nrm)) > 0 else -c
    sin_th = abs(float(t[0] * c[1] - t[1] * c[0]))
    arm, kept, arm_xy = [], [], []
    for k in np.arange(3.0, 60.0, 1.0):
        q = s_edge + dr * k
        if not 0.0 < q < n:
            break
        Q = L.interpolate(q)
        if np.degrees(np.arccos(min(1.0, abs(float(np.dot(tangent(L, q, 1.0), c)))))) < SAME_ST_DEG and g.distance(Q) < HALF_W[fh] + AWAY_M:
            arm.append(g.distance(Q) - min(lots[int(j)].distance(Q) for j in lt.query(Q.buffer(30.0))) if len(lt.query(Q.buffer(30.0))) else None)
            if k <= 25.0:
                arm_xy.append(Q.coords[0])
    arm = [v for v in arm if v is not None]
    from_arm = len(arm) >= 5
    if not from_arm:                              # the removed stretch runs on past a side street: the corner lot's line on this side
        C = Point(P + t * D)
        Pk = P + t * (D - 10.0)                  # a point on the kept side of the side street
        side_g = np.sign((Pk[0] - C.x) * c[1] - (Pk[1] - C.y) * c[0])
        ll_lots = []
        for j in lt.query(C.buffer(25.0)):
            lo = lots[int(j)]
            rp = np.array(lo.representative_point().coords[0])
            if lo.distance(C) < 25.0 and float(np.dot(rp - own_q, nrm)) > 0 and np.sign((rp[0] - C.x) * c[1] - (rp[1] - C.y) * c[0]) == side_g:
                ll_lots.append(g.distance(lo))
        arm = [min(ll_lots)] * 5 if ll_lots else []
    for k in np.arange(0.0, 30.0, 1.0):
        q = s_end - dr * k
        if 0.0 < q < n:
            Q = L.interpolate(q)
            near = lt.query(Q.buffer(15.0))
            if len(near):
                kept.append((g_own.distance(Q), min(lots[int(j)].distance(Q) for j in near)))
    if len(arm) < 5 or len(kept) < 5:
        return why_none(2)
    dk, fp = float(np.median([a for a, _ in kept])), float(np.median([b for _, b in kept]))
    ll = float(np.median(arm))
    off = ll * dk / max(dk + fp, 1e-6)           # the kept kerb's share of its own half reserve, applied to the side street's
    off = max(off, min(2.0, ll - 0.5))           # a lane's kerb (or edge) is never drawn closer than 2 m to its centreline (KN21 lane returns)
    OFFS.append((round(float(np.median(arm)), 1), round(dk, 1), round(fp, 1), round(off, 1), fh))
    if not 1.5 <= off <= HALF_W[fh] + 1.5:
        return why_none(3)
    e = D - off / max(sin_th, 0.5)
    hd = []
    for k in np.arange(2.0, 25.01, 1.0):          # the line's own side past its turn (any street angle: curved side streets, packC c38)
        q = s_edge + dr * k
        if 0.0 < q < n:
            hd.append((np.degrees(np.arccos(np.clip(float(np.dot(tangent(L, q, 1.0) * dr, t)), -1, 1))), L.interpolate(q).coords[0]))
    top = max((a for a, _ in hd), default=0.0)
    own_xy = [xy for a, xy in hd if a >= CORNER_DEG and a >= top - 10.0] if top >= CORNER_DEG else []
    if len(own_xy) >= 5 and ARM_CORNER:
        arm_xy, from_arm = own_xy, True
    if from_arm and len(arm_xy) >= 5 and ARM_CORNER:
        # round 4 (packC c38, c07, c33 and the "small hooks"): a corner placed from the centreline overshot the line's own corner by the
        # 1.5 m roads/LiDAR datum gap plus the lot-line-to-kerb share, into the junction. The removed arm is the line's own cross-street
        # side, so the corner is set where the kept straight meets the arm's own straight (both from the line, no centreline), and the
        # return runs CORNER_R m onto the arm: the line's own corner, rebuilt round, stopping on its own cross-street side.
        A = np.array(arm_xy)
        Am = A.mean(axis=0)
        w, V = np.linalg.eigh(np.cov((A - Am).T))
        ca = V[:, int(np.argmax(w))]
        den = t[0] * ca[1] - t[1] * ca[0]
        if abs(den) < 0.4:
            return why_none(9)                   # the arm runs nearly parallel: not a corner
        e = float(((Am[0] - P[0]) * ca[1] - (Am[1] - P[1]) * ca[0]) / den)
        X = P + t * e
        u = ca if float(np.dot(ca, Am - X)) > 0 else -ca
    else:
        X = P + t * e
    if not -30.0 <= e - CORNER_R <= 25.0:
        return why_none(4)
    T1, T2 = X - t * CORNER_R, X + u * CORNER_R
    curve = [tuple(map(float, (1 - k) ** 2 * T1 + 2 * (1 - k) * k * X + k ** 2 * T2)) for k in np.linspace(0.0, 1.0, 9)]
    if e - CORNER_R >= 0:
        s_cut, pts = s_end, [tuple(map(float, P))] + curve
    else:
        s_cut, pts = s_end + dr * (e - CORNER_R), curve
    if from_arm and not ARM_CORNER and L.distance(Point(T2)) > ll - off + 1.5:
        return why_none(7)                       # the return does not land beside the removed arm: a wrong cross street (roundabout ring, slip lane)
    new = LineString(pts)
    if sum(lots[int(j)].buffer(-0.5).intersection(new).length for j in lt.query(new)) > 1.0:   # more than a metre inside a lot (an own corner may graze the lot corner)
        return why_none(5)
    return s_cut, pts


def own_corner(L, s_edge, dr, lots=None, lt=None, streets=None, st_tree=None):
    """None when L runs on without turning past the cut end; else the distance along L where the kept piece should stop so it finishes on the
    line's own corner: the corner entry (last point turning less than STRAIGHT_DEG from the piece's own heading) in mode "entry", or the
    farthest point of the turn that stays CORNER_LOT_M or more from every lot in mode "own". dr = +1 when the removed stretch lies after s_edge."""
    lo, hi = 0.0, L.length
    t0 = tangent(L, s_edge - dr * 12.0) * dr          # the piece's own heading, well back from the cut (the turn can start inside the 2 m pad)
    ks = np.arange(-10.0, CORNER_M + 0.01, 0.5)
    ks = [k for k in ks if lo < s_edge + dr * k < hi]
    ang = [abs(turn_deg(L, s_edge + dr * k, dr, t0)) for k in ks]
    if not ang or max(a for k, a in zip(ks, ang) if k >= 0) < CORNER_DEG:
        return None
    if streets is not None:
        k_apex = next(k for k, a in zip(ks, ang) if a >= CORNER_DEG / 2)
        apex = L.interpolate(s_edge + dr * k_apex)
        if not junction_near(apex, streets, st_tree):
            return None                          # a bend in one street, not a block corner: a stop here would be a free end mid-street
        if not turns_into_street(L, s_edge + dr * (k_apex + POST_M), dr, streets, st_tree):
            return None                          # the line turns into a driveway or a yard, not along the cross street
    entry = None
    for k, a in zip(ks, ang):
        if a >= STRAIGHT_DEG:
            break
        entry = k
    if entry is None:
        return None
    if CORNER_MODE == "entry" or lots is None:
        return s_edge + dr * (entry - 1.0)
    best = entry
    for k, a in zip(ks, ang):
        if k <= entry:
            continue
        P = L.interpolate(s_edge + dr * k)
        if len(lots) and min(lots[int(j)].distance(P) for j in lt.query(P.buffer(CORNER_LOT_M + 0.5))) < CORNER_LOT_M if len(lt.query(P.buffer(CORNER_LOT_M + 0.5))) else False:
            break
        best = k
        if a >= CORNER_DEG + 30 or k >= CORNER_M:
            break
    return s_edge + dr * best


def clear_of_lots(pts, u, lots, lt):
    """True when the return pts and MOUTH_CLEAR m past its end along u touch no lot (a real street or lane gap between lots)."""
    if lots is None or not len(lots):
        return True
    end = np.array(pts[-1])
    probe = LineString([tuple(p) for p in pts[1:]] + [tuple(end + u * MOUTH_CLEAR)])
    return not any(lots[int(j)].buffer(-0.2).intersects(probe) for j in lt.query(probe))


def kerb_join(L, s_edge, others, own):
    """True when another kerb line lies within JOIN_KERB_M of the cut end (the end is left touching it)."""
    if others is None:
        return False
    p = L.interpolate(s_edge)
    return any(int(j) != own and others[1][int(j)].distance(p) <= JOIN_KERB_M for j in others[0].query(p.buffer(JOIN_KERB_M)))


def mid_cut(L, s_edge, streets, st_tree, others=None, own=None):
    """How the kerb finishes at a cut in mid-side, or None when it cannot finish properly (the kerb lead 20 Nov: a real kerb never returns in the
    middle of a street; it ends at a lane, a driveway or a side-street mouth, or on another kerb): either
      mouth: a street other than the line's own passes within its half width + MOUTH_NEAR m of the end and meets the line at 25 degrees or more:
             a pseudo mouth (s, s, point, u, hw) whose return turns into that street, as at a crossing; or
      join:  another kerb line (others, a shapely STRtree of the lines, own = this line's own index) lies within JOIN_KERB_M of the end:
             ("join",) and the end is left as it is, touching that kerb."""
    p = L.interpolate(s_edge)
    t = tangent(L, s_edge)
    cross, own_st = [], None
    for j in st_tree.query(p.buffer(HALF_W[1] + 12.0)):
        g, fh = streets[int(j)]
        d = g.distance(p)
        c = tangent(g, g.project(p))
        if np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, c)))))) < SAME_ST_DEG:
            if own_st is None or d < own_st.distance(p):
                own_st = g
        elif d <= HALF_W[fh] + MOUTH_NEAR:
            cross.append((d, g, fh, c))
    if cross and own_st is not None:
        d, g, fh, c = min(cross, key=lambda r: r[0])
        away = np.array(p.coords[0]) - np.array(own_st.interpolate(own_st.project(p)).coords[0])
        return (s_edge, s_edge, p, c if float(np.dot(c, away)) >= 0 else -c, min(HALF_W[fh], 2 * MID_R))
    if others is not None:
        for j in others[0].query(p.buffer(JOIN_KERB_M)):
            if int(j) != own and others[1][int(j)].distance(p) <= JOIN_KERB_M:
                return ("join",)
    return None


def clear_return(L, s0, s1, cb, ca, lots, lt):
    """Every added return of the piece [s0, s1] opens into a real gap between lots (clear_of_lots)."""
    room = (s1 - s0) / 3.0
    for c, s, d in ((cb, s0, +1), (ca, s1, -1)):
        if c is not None and len(c) > 3 and c[3] is not None:
            _, pts = arc(L, s, d, c[3], c[4], room)
            if not clear_of_lots(pts, c[3], lots, lt):
                return False
    return True


def make_piece(L, s0, s1, cb, ca):
    """-> (piece xy, number of returns) for the stretch [s0, s1] of L, each end with its kerb return when given (cb/ca carry u and half width)."""
    room = (s1 - s0) / 3.0
    r0 = r1 = 0.0
    head, tail = [], []
    if cb is not None and len(cb) > 3 and cb[3] is not None:
        r0, c = arc(L, s0, +1, cb[3], cb[4], room)
        head = c[::-1]
    if ca is not None and len(ca) > 3 and ca[3] is not None:
        r1, c = arc(L, s1, -1, ca[3], ca[4], room)
        tail = c
    lo, hi = (s0 + r0, s1 - r1)
    if s0 == 0 and s1 == L.length and not head and not tail:
        return [tuple(c) for c in L.coords], 0        # never cut: the published line, byte for byte
    body = [(x, y) for x, y in L.coords if lo + 0.01 < L.project(Point(x, y)) < hi - 0.01]
    pa, pb = L.interpolate(lo).coords[0], L.interpolate(hi).coords[0]
    mid = ([] if not head else head[:-1]) + [(pa[0], pa[1])] + body + [(pb[0], pb[1])] + ([] if not tail else tail[1:])
    return mid, int(bool(head)) + int(bool(tail))


def judge(line_xy, streets, st_tree, lots, lt, others=None, own=None):
    """-> (pieces [list of xy], sides [dict]). Each kept side is one piece; a cut end carries its kerb return. A side left out whole for a
    local stretch is cut at that stretch (step 4 of the module note): its good sub-pieces are kept with "cut_mid" and listed in the side dict
    under "pieces"; sides[i]["why"] stays the whole-side reason so the funnel still counts it."""
    L = LineString(line_xy)
    cuts = mouths(L, streets, st_tree)
    sides, pieces = [], []
    for s0, s1, cb, ca in sides_of(L, cuts):
        share, run, why = flags(L, s0, s1, lots, lt, streets, st_tree)
        n = {"s0": round(s0, 1), "s1": round(s1, 1), "len_m": round(s1 - s0, 1), "flagged": round(share, 2), "longest_flag_m": run}
        if s1 - s0 < MIN_SIDE:
            why = "short side"
        n["why"] = why
        sides.append(n)
        if why in ("hugs lots", "in the carriageway", "away from the road") and s1 - s0 >= 2 * MIN_SUB:
            spans = bad_spans(L, s0, s1, lots, lt, streets, st_tree)
            if spans:
                n["cut_spans_m"] = [[round(a, 1), round(b, 1)] for a, b in spans]
                edges = [s0] + [x for a, b in spans for x in (a, b)] + [s1]
                subs = []
                for k in range(0, len(edges), 2):
                    a, b = edges[k], edges[k + 1]
                    if b - a < MIN_SUB:
                        continue
                    c0, c1 = cb, ca
                    if CORNER_MODE == "build":
                        heads = {}
                        for end, dr in (("a", -1), ("b", +1)):
                            se = a if end == "a" else b
                            if se == (s0 if end == "a" else s1):
                                continue
                            bc = built_corner(L, se, dr, streets, st_tree, lots, lt)
                            if bc is None:
                                heads[end] = ("join", None, se) if kerb_join(L, se, others, own) else None
                            else:
                                heads[end] = ("built", bc[1], bc[0])
                        if any(v is None for v in heads.values()):
                            continue
                        a2 = heads["a"][2] if "a" in heads else a
                        b2 = heads["b"][2] if "b" in heads else b
                        if b2 - a2 < MIN_SUB or flags(L, a2, b2, lots, lt, streets, st_tree)[2]:
                            continue
                        q, nr = make_piece(L, a2, b2, cb if "a" not in heads else None, ca if "b" not in heads else None)
                        if "a" in heads and heads["a"][0] == "built":
                            q, nr = [p for p in heads["a"][1][::-1]] + q[1:], nr + 1
                        if "b" in heads and heads["b"][0] == "built":
                            q, nr = q[:-1] + [p for p in heads["b"][1]], nr + 1
                        subs.append((q, nr, a2, b2))
                        continue
                    if a != s0:
                        k = own_corner(L, a, -1, lots, lt, streets, st_tree)
                        if k is not None:
                            a, c0 = max(a, k) if CORNER_MODE == "entry" else min(a, k), ("corner",)
                        else:
                            c0 = mid_cut(L, a, streets, st_tree, others, own)
                    if b != s1:
                        k = own_corner(L, b, +1, lots, lt, streets, st_tree)
                        if k is not None:
                            b, c1 = min(b, k) if CORNER_MODE == "entry" else max(b, k), ("corner",)
                        else:
                            c1 = mid_cut(L, b, streets, st_tree, others, own)
                    if (a != s0 and c0 is None) or (b != s1 and c1 is None) or b - a < MIN_SUB:
                        continue
                    if not clear_return(L, a, b, c0, c1, lots, lt):
                        continue
                    if flags(L, a, b, lots, lt, streets, st_tree)[2]:
                        continue
                    q, nr = make_piece(L, a, b, c0, c1)
                    subs.append((q, nr, a, b))
                n["pieces"] = [{"s0": round(a, 1), "s1": round(b, 1), "returns": nr, "q": q} for q, nr, a, b in subs]
        if why:
            continue
        q, nr = make_piece(L, s0, s1, cb, ca)
        n["returns"] = nr
        pieces.append(q)
    return pieces, sides


def selftest():
    """A 10 m collector (fh 4, x axis) with a local street (fh 6) crossing at x=100, lots 4.5 m back along the north side."""
    from shapely.geometry import box
    main = (LineString([(-50, 0), (250, 0)]), 4)
    side = (LineString([(100, -80), (100, 80)]), 6)
    st = [main, side]
    tree = STRtree([s for s, _ in st])
    lots = [box(-50, 11, 90, 40), box(110, 11, 250, 40)]
    lt = STRtree(lots)
    kerb = [(-50 + 0.4 * k, 6.5) for k in range(0, 751)]                 # kerb 6.5 m north of the centreline: lot front at 11 is 4.5 m behind
    piece, sides = judge(kerb, st, tree, lots, lt)
    assert len(sides) == 2 and all(s["why"] is None for s in sides), sides
    assert len(piece) == 2 and all(p[0] != p[-1] for p in piece)
    # the gap between the two pieces is the mouth (about 4.5 m each side of x=100), and each end turns north into the side street
    left, right = piece
    assert 92.0 < left[-1][0] < 100.0 and left[-1][1] > 6.5 + 3.0, left[-3:]
    assert 100.0 < right[0][0] < 108.0 and right[0][1] > 6.5 + 3.0, right[:3]
    # a kerb hugging the lots (0.5 m off them, 10.5 m from the centreline) is left out whole; one in the road 12 m from the lots too
    hug = [(-50 + 0.4 * k, 10.8) for k in range(0, 751)]
    _, sides = judge(hug, st, tree, lots, lt)
    assert [s["why"] for s in sides] == ["hugs lots", "hugs lots"], sides
    far = [(-50 + 0.4 * k, 2.0) for k in range(0, 751)]
    far = [(x, y) for x, y in far]
    _, sides = judge(far, st, tree, [box(-50, 20, 250, 40)], STRtree([box(-50, 20, 250, 40)]))
    assert [s["why"] for s in sides] == ["in the carriageway", "in the carriageway"], sides
    away = [(-50 + 0.4 * k, 25.0) for k in range(0, 751)]               # 25 m from the street, 14 m behind the lot fronts: not along a road
    _, sides = judge(away, st, tree, [box(-50, 40, 250, 60)], STRtree([box(-50, 40, 250, 60)]))
    assert [s["why"] for s in sides] == ["away from the road", "away from the road"], sides
    away = [(-50 + 0.4 * k, 25.0) for k in range(0, 751)]               # 25 m from the street, 14 m behind the lot fronts: not along a road
    _, sides = judge(away, st, tree, [box(-50, 40, 250, 60)], STRtree([box(-50, 40, 250, 60)]))
    assert [s["why"] for s in sides] == ["away from the road", "away from the road"], sides
    # MID-SIDE CUT (KN24): a 300 m kerb with one 60 m stretch where a lot comes right up to it was left out whole by the hug rule; the
    # stretch goes and the two good pieces stay ONLY where each cut end can finish: here two side streets start just short of the kerb at
    # the cut ends (a return into each); with no street or kerb there the whole side stays out (no hook mid-street)
    lots2 = [box(-50, 11, 30, 40), box(46, 6.7, 94, 40), box(110, 11, 250, 40)]   # side streets at x=38 and 102 in real gaps; a lot up to the kerb between
    lt2 = STRtree(lots2)
    k300 = kerb[:int(300 / 0.4)]
    mouthst = [main, (LineString([(38, 8), (38, 80)]), 6), (LineString([(102, 8), (102, 80)]), 6)]
    piece, sides = judge(k300, mouthst, STRtree([g for g, _ in mouthst]), lots2, lt2)
    # side streets that stop short of the main road meet no junction node: no corner is built there and the stretch stays out (round 2)
    assert [s["why"] for s in sides] == ["hugs lots"] and not sides[0].get("pieces"), sides
    st2 = [main]
    tree2 = STRtree([g for g, _ in st2])
    _, sides = judge(k300, st2, tree2, lots2, lt2)
    assert not sides[0].get("pieces"), "a cut end with no street or kerb near got a hook mid-street"
    other = LineString([(44.5, 7.0), (44.5, 40.0)])
    oth = (STRtree([other, LineString(k300)]), [other, LineString(k300)])
    _, sides = judge(k300, st2, tree2, lots2, lt2, oth, 1)
    assert len(sides[0]["pieces"]) == 1 and sides[0]["pieces"][0]["returns"] == 0, sides    # a cut end touching another kerb is left as it is
    # SCENARIO 11 (21 Nov): the cut end sits where the line turns its own block corner (east along the street, then round a 5 m corner
    # north up a side street at x=100, where it runs on the lot line): the piece stops at the corner entry with no added curl, every point
    # on the published line; and a return toward a side street that opens on the far side of the road (lots unbroken on the kerb's side)
    # is refused, so that end cannot finish and the piece stays out
    cx, cy, R = 95.0, 11.5, 5.0
    turn = [(-50 + 0.5 * k, 6.5) for k in range(0, 291)] + [(cx + R * np.sin(t), cy - R * np.cos(t)) for t in np.linspace(0.1, np.pi / 2, 12)]
    turn += [(100.0, 11.5 + 0.5 * k) for k in range(1, 161)]
    lots3 = [box(-50, 11, 100, 120), box(109, 11, 200, 120)]                # the block west of the side street; the arm up it runs on the lot line
    st3 = [(LineString([(-50, 0), (104.5, 0)]), 4), (LineString([(104.5, 0), (250, 0)]), 4), (LineString([(104.5, 0.0), (104.5, 120.0)]), 6)]
    for mode in ("entry", "own"):
        globals()["CORNER_MODE"] = mode
        piece, sides = judge(turn, st3, STRtree([g for g, _ in st3]), lots3, STRtree(lots3))
        pcs = [q for n in sides for q in n.get("pieces", [])]
        assert len(pcs) == 1 and pcs[0]["returns"] == 0, (mode, sides)
        q = pcs[0]["q"]
        Lt = LineString(turn)
        assert all(Lt.distance(Point(c)) < 1e-6 for c in q), "corner piece left the published line"
        assert q[-1][1] < 6.5 + (0.3 if mode == "entry" else 4.0) and q[-1][0] > 85.0, (mode, q[-3:])
    globals()["CORNER_MODE"] = "build"
    lots5 = [box(-50, 9.5, 100, 120), box(110, 11, 200, 120)]                # 3 m footpath on the main street; arm on the lot line 5.5 m out
    st5 = [(LineString([(-50, 0), (105.5, 0)]), 4), (LineString([(105.5, 0), (250, 0)]), 4), (LineString([(105.5, 0.0), (105.5, 120.0)]), 6)]
    piece, sides = judge(turn, st5, STRtree([g for g, _ in st5]), lots5, STRtree(lots5))
    pcs = [q for n in sides for q in n.get("pieces", [])]
    assert len(pcs) == 1 and pcs[0]["returns"] == 1, sides
    q = pcs[0]["q"]
    # round 4: the corner is where the kept straight (y = 6.5) meets the line's own cross-street side (x = 100), rebuilt with a 4 m return
    # that stops on that side: no centreline is used, so a roads/LiDAR datum gap cannot push it into the junction
    assert abs(q[-1][0] - 100.0) < 0.3 and abs(q[-1][1] - 10.5) < 0.3, q[-4:]
    assert max(x for x, _ in q) < 100.3, "the corner overshoots the line's own cross-street side"
    bend = [st3[0], st3[2]]                                               # one street bending north (no junction): no stop mid-street
    _, sides = judge(turn, bend, STRtree([g for g, _ in bend]), lots3, STRtree(lots3))
    assert not any(n.get("pieces") for n in sides), ("free end at a bend", sides)
    far = [main, (LineString([(100, -80), (100, -8)]), 6)]                  # side street on the far (south) side only
    lots4 = [box(-50, 11, 40, 40), box(40, 6.7, 100, 40), box(100, 11, 250, 40)]
    _, sides = judge(k300, far, STRtree([g for g, _ in far]), lots4, STRtree(lots4))
    assert not any(n.get("pieces") and any(p["returns"] for p in n["pieces"]) for n in sides), ("return into lots", sides)
    # a side mostly bad stays out whole
    _, sides = judge(k300, mouthst, STRtree([g for g, _ in mouthst]), [box(-50, 11, 40, 40), box(40, 6.7, 240, 40)], STRtree([box(-50, 11, 40, 40), box(40, 6.7, 240, 40)]))
    assert not sides[0].get("pieces"), sides
    # a shallow crossing (the street curving under the kerb) is not a mouth; an untouched line comes back unchanged
    bend = LineString([(0, 0), (200, 0)])
    assert mouths(LineString([(0, 2), (200, 2)]), [(bend, 4)], STRtree([bend])) == []
    keep, _ = judge(kerb[:200], st, tree, lots, lt)
    assert keep == [[tuple(c) for c in kerb[:200]]], "uncut line moved"
    print("kerbrestore selftest pass")
    return 0


def feat(q, back, props):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(*c)] for c in q]}, "properties": props}


def main(a):
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    op = gzip.open if a[0].endswith(".gz") else open
    F = json.load(op(a[0], "rt"))["features"]
    lots, streets = load_lots(a[1]), load_streets(a[2])
    lt, st_tree = STRtree(lots), STRtree([s for s, _ in streets])
    out, rep, funnel = [], [], {}
    allxy = [[to(*c[:2]) for c in f["geometry"]["coordinates"]] for f in F]
    alls = [LineString(q) for q in allxy]
    others = (STRtree(alls), alls)
    for k, f in enumerate(F):
        xy = allxy[k]
        pieces, sides = judge(xy, streets, st_tree, lots, lt, others, k)
        p = f["properties"]
        area = (p.get("areas") or "").split(",")[0] or "?"
        z = funnel.setdefault(area, {"lines": 0, "km": 0.0, "sides": 0, "sides_kept": 0, "km_kept": 0.0, "why": {}, "returns": 0})
        z["lines"] += 1
        z["km"] += LineString(xy).length / 1000
        z["sides"] += len(sides)
        for s in sides:
            if s["why"]:
                z["why"][s["why"]] = z["why"].get(s["why"], 0.0) + s["len_m"] / 1000
        for q in pieces:
            z["sides_kept"] += 1
            z["km_kept"] += LineString(q).length / 1000
        z["returns"] += sum(s.get("returns", 0) for s in sides)
        kept = [n for n in sides if not n["why"]]
        for i, (q, n) in enumerate(zip(pieces, kept)):
            tier = "A" if n["flagged"] <= TIER_A_SHARE and n["longest_flag_m"] <= TIER_A_RUN else "B"
            out.append(feat(q, back, dict(p, piece=i, of=len(pieces), tier=tier, flagged=n["flagged"], returns=n.get("returns", 0))))
        for n in sides:
            subs = n.pop("pieces", [])
            n["n_pieces"] = len(subs)
            for j, sp in enumerate(subs):
                z["mid_pieces"] = z.get("mid_pieces", 0) + 1
                z["mid_km"] = z.get("mid_km", 0.0) + LineString(sp["q"]).length / 1000
                z["returns"] += sp["returns"]
                out.append(feat(sp["q"], back, dict(p, piece=j, of=len(subs), tier="C", flagged=n["flagged"], returns=sp["returns"], cut_mid=True,
                                                    side_s0=n["s0"], side_s1=n["s1"], why_whole=n["why"], s0=sp["s0"], s1=sp["s1"])))
                sp.pop("q")
        rep.append({"i": p.get("src_index", k), "area": area, "sides": sides})
    for z in funnel.values():
        z["km"], z["km_kept"], z["mid_km"] = round(z["km"], 1), round(z["km_kept"], 1), round(z.get("mid_km", 0.0), 1)
        z["why"] = {w: round(v, 1) for w, v in z["why"].items()}
    json.dump({"type": "FeatureCollection", "features": out}, open(a[3], "w"))
    json.dump({"check": "openfetch-derive kerbrestore.py", "file": os.path.basename(a[0]), "funnel": funnel, "lines": rep}, open(a[4], "w"))
    print(json.dumps(funnel, indent=0)[:3000])
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
