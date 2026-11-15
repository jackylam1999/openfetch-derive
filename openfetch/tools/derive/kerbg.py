"""Version g clean-up of a finished kerb network (EPSG 7856 point arrays), run last in kerbnet.py main (8 Nov 2026).

Version f review (20 of 47 tiles wrong) showed the same few shapes over and over, and every one breaks a plain rule about kerbs:
  - a kerb sits beside a ground street: a stretch more than STREETLESS m from every street is a footpath, park edge or yard line
    (streetless); a kerb runs along its street, so a free end turning away from it is a tail into a yard (away);
  - a kerb is not drawn on a bridge (bridges);
  - a kerb never folds back on itself in a narrow hairpin unless it rounds a dead end (hairpins);
  - one kerb per street side: a second strand running beside another with no street or lot between them is a double (doubles);
  - kerbs never fork: where an end runs into another line (Y, T, X with tails), one smooth kerb is kept and the rest is cut back
    (junctions); two kerb ends either side of a dead-end street are joined by a round cap (caps);
  - a kerb turns with a radius, never a square corner (fillets).
"""
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring
from shapely.strtree import STRtree

KEEP_MIN = 8.0       # m, shorter leftovers go
TOUCH = 1.0          # m, an end this near another line touches it
STREETLESS = 16.0    # m, a stretch farther than this from every ground street is not a street kerb
STREETLESS_RUN = 6.0
STREETLESS_MED, STREETLESS_LINE = 11.0, 40.0   # m: a short line lying mostly this far from every street goes whole  # m, shortest such stretch cut
AWAY_RUN, AWAY_GAIN, AWAY_FAR = 10.0, 3.5, 7.0   # m: a free end gaining this much distance from its street over this run, ending this far out
BRIDGE_W, BRIDGE_ANG = 12.0, 30.0   # m, deg
HAIR_TURN, HAIR_LEN, HAIR_W = 150.0, 20.0, 10.0
FOLD_W, FOLD_K = 3.2, 0.45   # m, ratio: legs closer than this at +-a m of a point fold there   # deg within m, legs closer than m
DOUBLE_LO, DOUBLE_HI, DOUBLE_ANG, DOUBLE_RUN = 0.3, 5.0, 20.0, 8.0   # m, m, deg, m
CLEAR = 5.3          # m, a cut-back end stays this far from the line it ran into (past the reviewer's near, 5 m)
TAIL = 10.0          # m, a branch this short past a junction with a free far end is a tail
JOIN_TURN = 120.0     # deg, two arms meeting at a junction may carry on as one kerb up to this turn
CAP_MIN, CAP_MAX, CAP_ANG, CAP_END = 3.0, 16.0, 40.0, 14.0   # m, m, deg, m
LANE_MOUTH = 5.5   # m, a lane mouth this narrow may be closed by its two corners whatever they face
LANE_CAP_MIN, LANE_CAP_MAX = 2.7, 8.0   # m: a cap narrower than the reviewer's fold (2.5 m) would fold
FILLET_TURN, FILLET_ARM, FILLET_R = 50.0, 2.0, 4.0   # deg over +-m, m cut back each side


def _L(c):
    return LineString(c)


def _closed(c):
    return np.hypot(*(np.asarray(c[0]) - np.asarray(c[-1]))) < TOUCH


def _hd(g, t, s=2.0):
    a, b = g.interpolate(max(0.0, t - s)), g.interpolate(min(g.length, t + s))
    return np.arctan2(b.y - a.y, b.x - a.x)


def _ang(a, b, axial=True):
    d = abs(a - b) % (2 * np.pi)
    d = min(d, 2 * np.pi - d)
    if axial:
        d = min(d, np.pi - d)
    return np.degrees(d)


def _keep_runs(g, mask, ts, stats, key):
    """pieces of g where mask is False, at least KEEP_MIN long"""
    res = []; i = 0; n = len(ts)
    while i < n:
        j = i
        while j + 1 < n and mask[j + 1] == mask[i]:
            j += 1
        a, b = ts[i], ts[j]
        if mask[i]:
            stats[key] = stats.get(key, 0) + (b - a)
        elif b - a >= KEEP_MIN:
            res.append(np.asarray(substring(g, a, b).coords) if (a > 0 or b < g.length) else np.asarray(g.coords))
        i = j + 1
    return res


def _samples(g, step=1.0):
    return np.linspace(0, g.length, max(2, int(g.length // step) + 1))


def _runs(mask, ts, minrun):
    """mask with True runs shorter than minrun set back to False"""
    m = mask.copy(); i = 0; n = len(ts)
    while i < n:
        if not m[i]:
            i += 1; continue
        j = i
        while j + 1 < n and m[j + 1]:
            j += 1
        if ts[j] - ts[i] < minrun:
            m[i:j + 1] = False
        i = j + 1
    return m


def streetless(out, streets, stats):
    st = STRtree(streets); res = []
    for o in out:
        g = _L(o); ts = _samples(g)
        far = np.array([not len(st.query(g.interpolate(t), predicate="dwithin", distance=STREETLESS)) for t in ts])
        far = _runs(far, ts, STREETLESS_RUN)
        if g.length < STREETLESS_LINE and np.median([st.query(g.interpolate(t), predicate="dwithin", distance=STREETLESS_MED).size == 0
                                                       for t in ts]) > 0.5:
            stats["streetless_m"] = stats.get("streetless_m", 0) + g.length; continue
        res += [o] if not far.any() else _keep_runs(g, far, ts, stats, "streetless_m")
    return res


def bridges(out, bridge_lines, stats):
    if not bridge_lines:
        return out
    bt = STRtree(bridge_lines); res = []
    for o in out:
        g = _L(o)
        if not len(bt.query(g, predicate="dwithin", distance=BRIDGE_W)):
            res.append(o); continue
        ts = _samples(g); m = np.zeros(len(ts), bool)
        for k, t in enumerate(ts):
            p = g.interpolate(t)
            for b in bt.query(p, predicate="dwithin", distance=BRIDGE_W):
                r = bridge_lines[int(b)]; s_ = r.project(p)
                if not (0.5 < s_ < r.length - 0.5):   # beside the approach, not the bridge itself (h: V16 cut 12 m too far)
                    continue
                if _ang(_hd(g, t), _hd(r, s_, 1.0)) < BRIDGE_ANG:
                    m[k] = True; break
        m = _runs(m, ts, 3.0)
        res += [o] if not m.any() else _keep_runs(g, m, ts, stats, "bridge_m")
    return res


def _free(G, tree, i, p):
    return not any(int(k) != i and G[int(k)].distance(p) < TOUCH for k in tree.query(p, predicate="dwithin", distance=TOUCH))


def away(out, streets, stats):
    """a free end that runs away from its street (into a yard, across a footpath) is cut back to where it still ran along it"""
    st = STRtree(streets); G = [_L(o) for o in out]; tree = STRtree(G); res = []; n = 0
    def dist(p):
        return streets[int(st.nearest(p))].distance(p)
    for i, g in enumerate(G):
        if _closed(out[i]) or g.length < AWAY_RUN + KEEP_MIN:
            res.append(out[i]); continue
        a, b = 0.0, g.length
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            if not _free(G, tree, i, e):
                continue
            at = (lambda t: g.interpolate(t)) if j0 == 0 else (lambda t: g.interpolate(g.length - t))
            if dist(at(0.0)) < AWAY_FAR or dist(at(0.0)) - dist(at(AWAY_RUN)) < AWAY_GAIN:
                continue
            t = 0.0
            while t < g.length - KEEP_MIN and dist(at(t)) - dist(at(t + AWAY_RUN / 2)) > AWAY_GAIN / 4:
                t += 1.0
            n += 1
            if j0 == 0:
                a = t
            else:
                b = g.length - t
        if b - a >= KEEP_MIN:
            res.append(out[i] if (a == 0 and b == g.length) else np.asarray(substring(g, a, b).coords))
    stats["away_cut"] = n
    return res


TUNNELS_G = []   # j: tunnel centrelines (a road there is not on the ground)
OVER = []   # bridge and tunnel centrelines: a ground street ending on one is not a dead end
MAIN = []   # i: main roads (fh 1-4) with their functionhierarchy: out of scope, a walk stops at them
STOP = []   # i: bridges a kerb walking along its street stops at (long ones and main roads; not a local street's short bridge)
BRIDGE_SHORT = 45.0   # m
SHORT = []   # i: those short local bridges


def _along_short(r, h):
    """a short local bridge is above the ground: a kerb runs along it and on under it, so it never stops a join or a walk"""
    return any(r is b for b in SHORT)


def _end_dead(p, streets, st, reach):
    """a street centreline end (dead end) within reach of p"""
    for k in st.query(p, predicate="dwithin", distance=reach):
        r = streets[int(k)]
        for q in (Point(r.coords[0]), Point(r.coords[-1])):
            if q.distance(p) < reach and not any(int(m) != int(k) and streets[int(m)].distance(q) < 2.0
                                                 for m in st.query(q, predicate="dwithin", distance=2.0)) \
                    and not any(b.distance(q) < 2.0 for b in OVER):
                return True
    return False


def hairpins(out, streets, stats):
    """a line folding back on itself in a narrow U, with no dead-end street inside the U, is cut at the turn; the shorter leg goes
    when under 25 m"""
    st = STRtree(streets); res = []; n = 0
    for o in out:
        g = _L(o)
        if g.length < 2 * HAIR_W:
            res.append(o); continue
        ts = _samples(g); cut = None
        for t in ts:
            if t < 3 or t > g.length - 3:
                continue
            if any(g.interpolate(t - a).distance(g.interpolate(t + a)) < min(FOLD_W, FOLD_K * a)
                   for a in (5.0, 7.0, 9.0) if t - a >= 0 and t + a <= g.length):
                cut = t; break   # a fold (an island nose, a hook): legs this close are never two kerbs
            h0, h1 = _hd(g, t - HAIR_LEN / 2, 2.0), _hd(g, t + HAIR_LEN / 2, 2.0)
            if _ang(h0, h1, axial=False) < HAIR_TURN:
                continue
            p0, p1 = g.interpolate(max(0, t - HAIR_LEN / 2)), g.interpolate(min(g.length, t + HAIR_LEN / 2))
            if p0.distance(p1) > HAIR_W or _end_dead(g.interpolate(t), streets, st, 12.0):
                continue
            cut = t; break
        if cut is None:
            res.append(o); continue
        n += 1
        for a, b in ((0, cut - 1.0), (cut + 1.0, g.length)):
            if b - a >= 25.0 or (b - a >= KEEP_MIN and b - a >= g.length - (b - a)):
                res.append(np.asarray(substring(g, max(a, 0), b).coords))
    stats["hairpin_cut"] = n
    return res


SPUR_MAX = 120.0   # m, the longest narrow spur cut off a ring
FOLD_D, FOLD_ALONG = 3.0, 8.0   # m: the reviewer's fold (2.5 m, 8 m) with a margin


def folds(out, stats):
    """a line coming back within FOLD_D m of itself more than FOLD_ALONG m further along (an island nose, a hook, a tight U) is cut
    at the turn half way between; the shorter side goes when under 25 m"""
    res = []; n = 0
    for o in out:
        todo = [np.asarray(o)]
        while todo:
            c = todo.pop(); g = _L(c)
            ring = _closed(c)
            if g.length < FOLD_ALONG + 2:
                res.append(c); continue
            ts = np.arange(0.5, g.length, 1.0); P = [g.interpolate(t) for t in ts]; tr = STRtree(P); hit = None
            for k, p in enumerate(P):
                for m in tr.query(p, predicate="dwithin", distance=FOLD_D):
                    along = abs(ts[int(m)] - ts[k])
                    if ring:
                        along = min(along, g.length - along)
                    if along > FOLD_ALONG:
                        hit = (ts[k], ts[int(m)]); break
                if hit:
                    break
            if hit is None:
                res.append(c); continue
            n += 1
            t = 0.5 * (hit[0] + hit[1])
            if ring:   # a pinched ring: a small one goes; a big one loses the narrow spur (i, h V80: a 2 m lane drawn as a long
                if g.length < 60:   # thin U off the block loop): the street kerb carries straight on across the lane's mouth
                    continue
                t1, t2 = sorted(hit); a1 = t2 - t1
                if a1 <= g.length - a1:   # the spur is t1..t2: keep t2..end + start..t1
                    keep_ = np.vstack([np.asarray(substring(g, t2, g.length).coords), np.asarray(substring(g, 0, t1).coords)[1:]])
                else:   # the spur wraps the seam: keep t1..t2
                    keep_ = np.asarray(substring(g, t1, t2).coords)
                if min(a1, g.length - a1) > SPUR_MAX:
                    res.append(c); continue
                r2 = np.vstack([keep_, keep_[:1]])
                if len(r2) > 3 and LineString(r2).is_simple:
                    todo.append(r2); stats["spur_cut"] = stats.get("spur_cut", 0) + 1
                else:
                    res.append(c)
                continue
            A, B = substring(g, 0, max(0.0, t - 1.0)), substring(g, min(g.length, t + 1.0), g.length)
            keep = [x for x in (A, B) if x.length >= KEEP_MIN and x.length >= g.length - x.length]   # the longer side only
            todo += [np.asarray(x.coords) for x in keep]
    stats["fold_cut"] = n
    return res


def doubles(out, streets, lots, stats):
    """one kerb per street side: where two lines run side by side DOUBLE_LO-DOUBLE_HI m apart for DOUBLE_RUN m with no street
    centreline or property lot between them, the stretch is taken out of the shorter line"""
    for _ in range(2):
        G = [_L(o) for o in out]; tree = STRtree(G); st = STRtree(streets); lt = STRtree(lots) if lots else None
        order = sorted(range(len(G)), key=lambda i: G[i].length); gone = {}; done = set()
        for i in order:
            g = G[i]
            if not len(tree.query(g, predicate="dwithin", distance=DOUBLE_HI)) > 1:
                continue
            ts = _samples(g); m = np.zeros(len(ts), bool)
            for k, t in enumerate(ts):
                p = g.interpolate(t)
                for j in tree.query(p, predicate="dwithin", distance=DOUBLE_HI):
                    j = int(j)
                    if j == i or j in done:
                        continue
                    o = G[j]; d = o.distance(p)
                    if d < DOUBLE_LO:
                        continue
                    q = o.interpolate(o.project(p))
                    if _ang(_hd(g, t), _hd(o, o.project(p))) > DOUBLE_ANG:
                        continue
                    seg = LineString([p, q])
                    if seg.length > 0.01 and len(st.query(seg, predicate="intersects")):
                        continue
                    if lt is not None and seg.length > 0.5 and any(lots[int(x)].contains(seg.interpolate(0.5, normalized=True))
                                                                     for x in lt.query(seg)):
                        continue
                    m[k] = True; break
            m = _runs(m, ts, DOUBLE_RUN)
            if m.any():
                gone[i] = _keep_runs(g, m, ts, stats, "double_m"); done.add(i)
        if not gone:
            break
        out = [p for i, o in enumerate(out) for p in (gone[i] if i in gone else [o])]
    return out


def _cutback(g, j0, other, clear=CLEAR):
    """g with the end j0 (0 start, 1 end) cut back until it is `clear` m from `other`"""
    t = 0.0
    while t < g.length and other.distance(g.interpolate(t if j0 == 0 else g.length - t)) < clear:
        t += 0.5
    return t


def _join(a, b):
    """a's end meets b's start: one line. Ends that only come close (a touch) are each cut back JOIN_BACK m and bridged, so the
    join never doubles back on itself"""
    a = np.asarray(a); b = np.asarray(b)
    if np.hypot(*(a[-1] - b[0])) < 1e-6:
        return np.vstack([a, b[1:]])
    ga, gb = LineString(a), LineString(b)
    if ga.length > 2 * JOIN_BACK and gb.length > 2 * JOIN_BACK:
        a = np.asarray(substring(ga, 0, ga.length - JOIN_BACK).coords); b = np.asarray(substring(gb, JOIN_BACK, gb.length).coords)
    return np.vstack([a, b])


JOIN_BACK = 1.5
TEE_ANG = 35.0   # deg, an end meeting a line's middle at least this square is a T corner, kept


def junctions(out, streets, stats):
    """kerbs never fork. An end touching another line:
      - at that line's free end, carrying on within JOIN_TURN deg and not across a street: the two become one line;
      - in that line's middle, close to a free far end (a branch under TAIL m): the tail is cut off and the two become one corner;
      - anything else (a T, a Y sliding in, a third arm at a joint): the touching end is cut back CLEAR m from the other line."""
    nj = nt = nc = 0
    G = [_L(o) for o in out]; tree = STRtree(G); acts = []; busy = set()
    for i, g in enumerate(G):
        if i in busy or _closed(out[i]) or g.length < 1.0:
            continue
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            near = [int(k) for k in tree.query(e, predicate="dwithin", distance=TOUCH) if int(k) != i and G[int(k)].distance(e) < TOUCH]
            if not near:
                continue
            if any(k in busy for k in near):
                break
            he = _hd(g, 0.0 if j0 == 0 else g.length, 3.0) + (np.pi if j0 == 0 else 0.0)   # heading arriving at e
            act = None
            if len(near) == 1 and not _closed(out[near[0]]):
                j = near[0]; o = G[j]; s = o.project(e)
                k1, dd = min([(0, s), (1, o.length - s)], key=lambda x: x[1])
                if dd < TOUCH:   # end to end
                    hb = _hd(o, 0.0 if k1 == 0 else o.length, 3.0) + (0.0 if k1 == 0 else np.pi)   # heading leaving e along o
                    others = [int(k) for k in tree.query(e, predicate="dwithin", distance=CLEAR) if int(k) not in (i, j)]
                    if _ang(he, hb, axial=False) <= JOIN_TURN:
                        a = np.asarray(out[i]) if j0 == 1 else np.asarray(out[i])[::-1]
                        b = np.asarray(out[j]) if k1 == 0 else np.asarray(out[j])[::-1]
                        c = _join(a, b)
                        if _closed(c):   # the two make a ring: close it exactly
                            c = np.vstack([c[:-1], c[:1]]) if np.hypot(*(c[-1] - c[0])) > 1e-6 else c
                            ok = len(c) > 3 and LineString(c).is_simple and LineString(c).is_ring
                        else:
                            ok = LineString(c).is_simple
                        if ok:
                            act = ("join", i, j, c)
                elif dd < TAIL and dd < 0.5 * o.length:
                    far = Point(o.coords[0 if k1 == 0 else -1])
                    if _free(G, tree, j, far) and o.length - dd >= KEEP_MIN:
                        kc = np.asarray((substring(o, s, o.length) if k1 == 0 else substring(o, 0, s)).coords)
                        if k1 == 1:
                            kc = kc[::-1]   # now starts at the junction
                        v = kc[min(3, len(kc) - 1)] - kc[0]
                        if _ang(he, np.arctan2(v[1], v[0]), axial=False) <= JOIN_TURN + 30:
                            a = np.asarray(out[i]) if j0 == 1 else np.asarray(out[i])[::-1]
                            c = _join(a, kc)
                            if LineString(c).is_simple:
                                act = ("tail", i, j, c)
            if act is None and len(near) == 1:
                o = G[near[0]]; s_ = o.project(e)
                if 1.0 < s_ < o.length - 1.0 and _ang(he, _hd(o, s_, 2.0)) >= TEE_ANG:
                    continue   # h: a square T is a closed corner, kept (g cut it back and left a hole)
            if act is None:
                act = ("cut", i, j0, max(_cutback(g, j0, G[k]) for k in near))
                busy.add(i); busy.update(near)
            else:
                busy.update((act[1], act[2]))
            acts.append(act); break
    drop = set(); add = []
    for act in acts:
        if act[0] in ("join", "tail"):
            _, i, j, c = act; drop.update((i, j)); add.append(c)
            if act[0] == "join":
                nj += 1
            else:
                nt += 1
        else:
            _, i, j0, t = act; g = G[i]; nc += 1; drop.add(i)
            if g.length - t >= KEEP_MIN:
                add.append(np.asarray((substring(g, t, g.length) if j0 == 0 else substring(g, 0, g.length - t)).coords))
    out = [o for k, o in enumerate(out) if k not in drop] + add
    stats["junction_join"] = nj; stats["junction_tail"] = nt; stats["junction_cut"] = nc
    return out


def junctions_all(out, streets, stats):
    """junctions() repeated until nothing changes (each pass handles a batch of non-overlapping spots)"""
    tot = {}
    for _ in range(40):
        s = {}; out = junctions(out, streets, s)
        for k, v in s.items():
            tot[k] = tot.get(k, 0) + v
        if not any(s.values()):
            break
    for k, v in tot.items():
        stats[k] = stats.get(k, 0) + v
    return out


def _bez(p0, c0, c1, p1, n=16):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c0 + 3 * (1 - t) * t ** 2 * c1 + t ** 3 * p1


def caps(out, streets, stats, dead=True, dmin=CAP_MIN, dmax=CAP_MAX):
    """two free kerb ends either side of a dead-end street, facing the same way, are joined by a round cap. dead=False (i, h near
    ends: in a narrow street any kerb end lies within 5 m of the kerb across): the two kerbs of a narrow street that both stop
    side by side, a street centreline between them, are closed with a cap whatever the centreline does"""
    st = STRtree(streets); G = [_L(o) for o in out]; tree = STRtree(G)
    ends = []
    for i, g in enumerate(G):
        if _closed(out[i]) or g.length < 4:
            continue
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            if _free(G, tree, i, e):
                h = _hd(g, 0.0 if j0 == 0 else g.length, 3.0) + (np.pi if j0 == 0 else 0.0)
                ends.append((i, j0, e, h))
    used = set(); pairs = []
    et = STRtree([x[2] for x in ends])
    cand = []
    for a, (i, j0, e, h) in enumerate(ends):
        for b in et.query(e, predicate="dwithin", distance=dmax):
            b = int(b)
            if b <= a:
                continue
            i2, k0, e2, h2 = ends[b]
            d = e.distance(e2)
            if i2 == i or d < dmin or _ang(h, h2, axial=False) > (CAP_ANG if dead or d > LANE_MOUTH else 100.0):   # i (h V82): lane mouth corners
                continue
            u = np.array([e2.x - e.x, e2.y - e.y]) / d   # across, about square to the kerbs
            if abs(np.cos(h) * u[0] + np.sin(h) * u[1]) > (0.5 if dead else 1.01):   # i (h V69): a lane's ends may stop staggered
                continue
            mid = Point((e.x + e2.x) / 2, (e.y + e2.y) / 2)
            seg = LineString([e, e2])
            if not dead:
                if not len(st.query(seg, predicate="intersects")):
                    continue
            elif not _end_dead(mid, streets, st, d / 2 + CAP_END):
                continue
            cand.append((d, a, b))
    for d, a, b in sorted(cand):
        if a in used or b in used:
            continue
        i, j0, e, h = ends[a]; i2, k0, e2, h2 = ends[b]
        if any(x in (i, i2) for p in pairs for x in (p[0], p[2])):
            continue
        p0 = np.array([e.x, e.y]); p1 = np.array([e2.x, e2.y]); k = 0.66 * d
        cap = _bez(p0, p0 + k * np.array([np.cos(h), np.sin(h)]), p1 + k * np.array([np.cos(h2), np.sin(h2)]), p1)
        a_ = np.asarray(out[i]) if j0 == 1 else np.asarray(out[i])[::-1]
        b_ = np.asarray(out[i2]) if k0 == 0 else np.asarray(out[i2])[::-1]
        if _ang(h, h2, axial=False) > CAP_ANG:
            # two corners curling apart into a lane mouth (h V82): both curls are taken back until a straight piece across closes
            # the mouth with no fold, as the street kerb runs past a lane with a laid-back crossing
            got = None
            for t in np.arange(0.0, 8.01, 0.5):
                ga, gb = LineString(a_), LineString(b_)
                if ga.length - t < KEEP_MIN or gb.length - t < KEEP_MIN:
                    break
                at = np.asarray(substring(ga, 0, ga.length - t).coords) if t else a_
                bt = np.asarray(substring(gb, t, gb.length).coords) if t else b_
                q0, q1 = at[-1], bt[0]; dq = np.hypot(*(q1 - q0))
                if dq < 0.3:
                    continue
                c_ = np.linspace(q0, q1, max(3, int(dq) + 1)); jn = np.vstack([at, c_[1:-1], bt])
                if LineString(jn).is_simple and not _folds_near(jn, len(at)):
                    got = (c_, at, bt); break
            if got is None:
                continue
            cap, a_, b_ = got
        cl = LineString(cap)
        if not LineString(_join(_join(a_, cap), b_)).is_simple:
            continue
        if any(G[int(m)].crosses(cl) for m in tree.query(cl) if int(m) not in (i, i2)):
            continue
        used.update((a, b)); pairs.append((i, j0, i2, k0, cap, a_, b_))
    if not pairs:
        return out
    drop = set(); add = []
    for i, j0, i2, k0, cap, a, b in pairs:
        add.append(_join(_join(a, cap), b)); drop.update((i, i2))
    stats["caps" if dead else "lane_caps"] = stats.get("caps" if dead else "lane_caps", 0) + len(pairs)
    return [o for k, o in enumerate(out) if k not in drop] + add


CJ_CORNER, CJ_RAY, CJ_STRAIGHT, CJ_LAT, CJ_CLOSE = 8.0, 9.0, 30.0, 2.5, 2.5   # m


def _free_ends(out, G, tree, minlen=4.0):
    ends = []
    for i, g in enumerate(G):
        if _closed(out[i]) or g.length < minlen:
            continue
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            if _free(G, tree, i, e):
                h = _hd(g, 0.0 if j0 == 0 else g.length, 3.0) + (np.pi if j0 == 0 else 0.0)
                ends.append((i, j0, e, h))
    return ends


def corner_join(out, streets, stats):
    """two free kerb ends that are one kerb broken apart are joined: facing each other on one line up to CJ_STRAIGHT m apart (a
    broken straight kerb), or turning a corner (their rays meet within CJ_RAY m ahead of both, CJ_CORNER m apart) with a round
    curve. Never across a street centreline or another kerb."""
    st = STRtree(streets); G = [_L(o) for o in out]; tree = STRtree(G)
    ends = _free_ends(out, G, tree); et = STRtree([x[2] for x in ends]); cand = []
    for a, (i, j0, e, h) in enumerate(ends):
        for b in et.query(e, predicate="dwithin", distance=CJ_STRAIGHT):
            b = int(b)
            if b <= a:
                continue
            i2, k0, e2, h2 = ends[b]
            p0 = np.array([e.x, e.y]); p1 = np.array([e2.x, e2.y]); d = np.hypot(*(p1 - p0))
            if i2 == i:   # a loop left just open: closed
                if d <= CJ_CLOSE and G[i].length > 30:
                    cand.append((d, a, b, None))
                continue
            if d < 0.3:
                continue
            u0 = np.array([np.cos(h), np.sin(h)]); u1 = np.array([np.cos(h2), np.sin(h2)])
            v = (p1 - p0) / d
            lat = abs(u0[0] * (p1 - p0)[1] - u0[1] * (p1 - p0)[0])
            if _ang(h, h2 + np.pi, axial=False) < 20 and lat < max(CJ_LAT, min(4.0, 1.0 + 0.15 * d)) and np.dot(u0, v) > 0.85:
                # straight across, as the broken kerb ran; a step between the two ends (i: h gaps 5-26 m with a 2.5-4 m step) is an S
                curve = np.linspace(p0, p1, max(3, int(d) + 1)) if lat < CJ_LAT else _bez(p0, p0 + d / 3 * u0, p1 + d / 3 * u1, p1, max(6, int(d) + 1))
            elif d <= CJ_CLOSE and _ang(h, h2 + np.pi, axial=False) <= 100:   # ends this close: one kerb, whatever the rays do
                k = d / 3; curve = _bez(p0, p0 + k * u0, p1 + k * u1, p1, 6)
            elif d <= CJ_CORNER and 30 <= _ang(h, h2 + np.pi, axial=False) <= 135:
                M = np.array([u0, -u1]).T
                try:
                    s0, s1 = np.linalg.solve(M, p1 - p0)
                except np.linalg.LinAlgError:
                    continue
                if not (-0.5 <= s0 <= CJ_RAY and -0.5 <= s1 <= CJ_RAY):
                    continue
                s0, s1 = max(s0, 0.5), max(s1, 0.5)
                curve = _bez(p0, p0 + 0.6 * s0 * u0, p1 + 0.6 * s1 * u1, p1, 12)
            else:
                continue
            cl = LineString(curve)
            if any(not _along_short(streets[int(m)], h) for m in st.query(cl, predicate="intersects")):
                continue   # i: a short local bridge the kerb runs along (not across) does not stop the join
            if any(int(m) not in (i, i2) and G[int(m)].intersects(cl) for m in tree.query(cl)):
                continue
            cand.append((d, a, b, curve))
    used = set(); joins = {}; parent = {}
    def root(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    add = []; drop = set(); n = 0
    lines = {i: np.asarray(o) for i, o in enumerate(out)}
    for d, a, b, curve in sorted(cand, key=lambda x: x[0]):
        if a in used or b in used:
            continue
        i, j0, e, h = ends[a]; i2, k0, e2, h2 = ends[b]
        ri, r2 = root(i), root(i2)
        if curve is None:
            if i == i2 and ri == i:
                c = np.asarray(lines[ri]); c = np.vstack([c, c[:1]])
                if LineString(c).is_simple:
                    lines[ri] = c; used.update((a, b)); n += 1
            continue
        if ri == r2:
            continue
        A, B = lines[ri], lines[r2]
        pa = np.array([e.x, e.y]); pb = np.array([e2.x, e2.y])
        if np.hypot(*(A[-1] - pa)) > 1e-6:
            A = A[::-1]
        if np.hypot(*(B[0] - pb)) > 1e-6:
            B = B[::-1]
        if np.hypot(*(A[-1] - pa)) > 1e-6 or np.hypot(*(B[0] - pb)) > 1e-6:
            continue
        c = _join(_join(A, curve), B)
        if not LineString(c).is_simple:
            if np.hypot(*(c[0] - c[-1])) < TOUCH:   # i (h V87): the two were one kerb round a block already: the join closes the ring
                c = np.vstack([c[:-1], c[:1]])
            if not (np.hypot(*(c[0] - c[-1])) < 1e-6 and len(c) > 3 and LineString(c).is_simple):
                two = _lollipop(c, LineString(A).length)
                if two is None:
                    continue
                used.update((a, b)); n += 1
                new = max(lines) + 1; lines[new] = two[0]; parent[ri] = new; parent[r2] = new
                if two[1] is not None:
                    lines[new + 1] = two[1]
                del lines[ri]; del lines[r2]
                continue
        used.update((a, b)); n += 1
        new = max(lines) + 1; lines[new] = c; parent[ri] = new; parent[r2] = new
        del lines[ri]; del lines[r2]
    stats["corner_join"] = stats.get("corner_join", 0) + n
    return list(lines.values())


def fillets(out, stats):
    """a turn sharper than FILLET_TURN deg over +-FILLET_ARM m is rounded: the corner FILLET_R m each side becomes a curve"""
    res = []; n = 0
    for o in out:
        g = _L(o)
        for _ in range(20):
            if g.length < 2 * FILLET_R + 1:
                break
            ts = np.arange(FILLET_ARM, g.length - FILLET_ARM, 0.5)
            if not len(ts):
                break
            turn = np.array([_ang(_hd(g, t - FILLET_ARM / 2, FILLET_ARM / 2), _hd(g, t + FILLET_ARM / 2, FILLET_ARM / 2), axial=False)
                             for t in ts])
            k = int(np.argmax(turn))
            if turn[k] < FILLET_TURN:
                break
            t = ts[k]; r = min(FILLET_R, t - 0.1, g.length - t - 0.1)
            if r < 1.0:
                break
            a, b = t - r, t + r
            pa, pc, pb = [np.asarray(g.interpolate(x).coords[0]) for x in (a, t, b)]
            curve = _bez(pa, pa + 0.66 * (pc - pa), pb + 0.66 * (pc - pb), pb, 10)
            c = np.vstack([np.asarray(substring(g, 0, a).coords)[:-1], curve, np.asarray(substring(g, b, g.length).coords)[1:]])
            g2 = LineString(c)
            if not g2.is_simple and g.is_simple:
                break
            g = g2; n += 1
        res.append(np.asarray(g.coords))
    stats["fillets"] = n
    return res


_RT = []


def _simple(g):
    """simple also as readers see it: through lon/lat (GDA2020, 7844) at 8 decimals and back"""
    if not g.is_simple:
        return False
    if not _RT:
        from pyproj import Transformer
        _RT.extend([Transformer.from_crs(7856, 7844, always_xy=True).transform, Transformer.from_crs(7844, 7856, always_xy=True).transform])
    fr, to = _RT
    q = [to(*[round(v, 8) for v in fr(x, y)]) for x, y in g.coords]
    return LineString(q).is_simple


def endtrim(out, stats):
    """a line whose end comes back within END_NEAR m of itself (a tiny hook left by a cut or a join; it reads as a self-touch once
    rounded to lon/lat) loses that bit of end"""
    res = []; n = 0
    for o in out:
        g = _L(o)
        if not _closed(np.asarray(g.coords)):
            for _ in range(10):
                if g.length < KEEP_MIN:
                    break
                L = g.length
                hook0 = substring(g, 0, 1.5).distance(substring(g, 3.5, L)) < END_NEAR
                hook1 = substring(g, L - 1.5, L).distance(substring(g, 0, L - 3.5)) < END_NEAR
                if not (hook0 or hook1) and _simple(g):
                    break
                if hook0 or hook1:
                    g = substring(g, END_STEP if hook0 else 0.0, L - END_STEP if hook1 else L)
                else:
                    g = substring(g, END_STEP, L - END_STEP)
                n += 1
        res.append(np.asarray(g.coords))
    stats["end_trim"] = n
    return res


END_STEP, END_NEAR = 1.0, 0.1


BESIDE_D, BESIDE_CLEAR, BESIDE_DROP = 3.7, 3.9, 25.0   # m


def besides(out, stats):
    """a free end lying within BESIDE_D m beside another line that runs on past it in the same direction (a second strand, a corner
    that never met its kerb) is cut back until it is BESIDE_CLEAR m clear; lines left under BESIDE_DROP m with both ends free go"""
    n = 0
    for _ in range(3):
        G = [_L(o) for o in out]; tree = STRtree(G); cut = {}
        for i, g in enumerate(G):
            if _closed(out[i]) or g.length < 3:
                continue
            for j0 in (0, 1):
                t0 = 0.0 if j0 == 0 else g.length; e = Point(g.coords[0 if j0 == 0 else -1])
                if not _free(G, tree, i, e):
                    continue
                for k in tree.query(e, predicate="dwithin", distance=BESIDE_D):
                    k = int(k)
                    if k == i:
                        continue
                    o = G[k]; s_ = o.project(e)
                    if min(s_, o.length - s_) < 4.0 or _ang(_hd(g, t0, 2.0), _hd(o, s_, 3.0)) > 25:
                        continue
                    t = 0.0
                    while t < g.length and o.distance(g.interpolate(t if j0 == 0 else g.length - t)) < BESIDE_CLEAR:
                        t += 0.5
                    cut.setdefault(i, [0.0, 0.0])[j0] = max(cut.get(i, [0.0, 0.0])[j0], t); break
        if not cut:
            break
        res = []
        for i, o in enumerate(out):
            if i not in cut:
                res.append(o); continue
            g = G[i]; a, b = cut[i][0], g.length - cut[i][1]; n += 1
            if b - a < KEEP_MIN:
                continue
            h = substring(g, a, b)
            if h.length < BESIDE_DROP and _free(G, tree, i, Point(g.coords[0])) and _free(G, tree, i, Point(g.coords[-1])):
                continue
            res.append(np.asarray(h.coords))
        out = res
    stats["beside_cut"] = n
    return out


HOOK_RUN, HOOK_TURN, HOOK_NEAR = 10.0, 45.0, 5.0   # m, deg, m


def hooks(out, stats):
    """a free end that turns more than HOOK_TURN deg in its last HOOK_RUN m and stops within HOOK_NEAR m of another kerb's middle
    is a corner that never met its kerb (version f V59): the hooked bit is cut off at the start of the turn"""
    G = [_L(o) for o in out]; tree = STRtree(G); res = []; n = 0
    for i, g in enumerate(G):
        if _closed(out[i]) or g.length < HOOK_RUN + KEEP_MIN:
            res.append(out[i]); continue
        a, b = 0.0, g.length
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            if not _free(G, tree, i, e):
                continue
            mids = [int(k) for k in tree.query(e, predicate="dwithin", distance=HOOK_NEAR) if int(k) != i
                    and 3.0 < G[int(k)].project(e) < G[int(k)].length - 3.0]
            if not mids:
                continue
            at = (lambda t: t) if j0 == 0 else (lambda t: g.length - t)
            h_end, h_in = _hd(g, at(1.0), 1.0), _hd(g, at(HOOK_RUN), 1.5)
            if _ang(h_end, h_in, axial=False) < HOOK_TURN:
                continue
            t = 1.0
            while t < HOOK_RUN and _ang(_hd(g, at(t), 1.0), h_in, axial=False) > 15:
                t += 0.5
            n += 1
            if j0 == 0:
                a = t
            else:
                b = g.length - t
        if b - a >= KEEP_MIN:
            res.append(out[i] if (a == 0 and b == g.length) else np.asarray(substring(g, a, b).coords))
    stats["hook_cut"] = n
    return res


NEAR_D = 5.0   # m, the reviewer's near


def tees(out, streets, stats):
    """a free end stopping 1-5 m short of another kerb's middle with no street between (a T that never met, a stray starting off a
    kerb; version f V46) is cut back CLEAR m clear of it; a line left under 25 m with both ends free goes"""
    st = STRtree(streets); n = 0
    for _ in range(3):
        G = [_L(o) for o in out]; tree = STRtree(G); cut = {}
        for i, g in enumerate(G):
            if _closed(out[i]) or g.length < 3:
                continue
            for j0 in (0, 1):
                e = Point(g.coords[0 if j0 == 0 else -1])
                if not _free(G, tree, i, e):
                    continue
                for k in tree.query(e, predicate="dwithin", distance=NEAR_D):
                    k = int(k); o = G[k]
                    if k == i:
                        continue
                    s_ = o.project(e)
                    if min(s_, o.length - s_) < 3.0 and not _closed(out[k]):
                        continue   # near another end: corner_join's business
                    seg = LineString([e, o.interpolate(s_)])
                    if seg.length > 0.01 and len(st.query(seg, predicate="intersects")):
                        continue
                    t = _cutback(g, j0, o)
                    cut.setdefault(i, [0.0, 0.0])[j0] = max(cut.get(i, [0.0, 0.0])[j0], t); break
        if not cut:
            break
        res = []
        for i, o in enumerate(out):
            if i not in cut:
                res.append(o); continue
            g = G[i]; a, b = cut[i][0], g.length - cut[i][1]; n += 1
            if b - a < KEEP_MIN:
                continue
            h = substring(g, a, b)
            if h.length < BESIDE_DROP and _free(G, tree, i, Point(g.coords[0])) and _free(G, tree, i, Point(g.coords[-1])):
                continue
            res.append(np.asarray(h.coords))
        out = res
    stats["tee_cut"] = n
    return out


def endfix(out, stats):
    """last resort for a line still touching itself (as read in lon/lat): trim up to 6 m off an end, else split it at the knot"""
    res = []; n = 0
    for o in out:
        g = _L(o)
        if _closed(np.asarray(g.coords)) or _simple(g):
            res.append(o); continue
        n += 1; done = False
        for t in np.arange(0.5, 6.01, 0.5):
            for a, b in ((t, g.length), (0.0, g.length - t), (t, g.length - t)):
                if b - a >= KEEP_MIN and _simple(substring(g, a, b)):
                    res.append(np.asarray(substring(g, a, b).coords)); done = True; break
            if done:
                break
        if not done:
            import kerbnet
            kept = [c for c in kerbnet.deknot([np.asarray(g.coords)], {}) if _L(c).length >= KEEP_MIN]
            stats["endfix_dropped_m"] = stats.get("endfix_dropped_m", 0) + int(g.length - sum(_L(c).length for c in kept)); res += kept
    stats["end_fix"] = n
    return res


def ringseat(out, stats):
    """a closed loop's start/end point is moved to the vertex farthest from every other line (a seam next to another kerb reads as a
    free end to the reviewer)"""
    G = [_L(o) for o in out]; tree = STRtree(G); res = []; n = 0
    for i, o in enumerate(out):
        c = np.asarray(o)
        if not _closed(c) or len(c) < 4:
            res.append(c); continue
        c = np.vstack([c[:-1], c[:1]])
        near = [G[int(k)] for k in tree.query(G[i], predicate="dwithin", distance=8.0) if int(k) != i]
        if not near or min(x.distance(Point(c[0])) for x in near) >= 6.0:
            res.append(c); continue
        d = [min(x.distance(Point(q)) for x in near) for q in c[:-1]]
        k = int(np.argmax(d)); n += 1
        res.append(np.vstack([c[k:-1], c[:k + 1]]))
    for k, c in enumerate(res):   # a loop that touches itself (as read in lon/lat): another seam, else opened at the seam
        if not _closed(c) or _simple(_L(c)):
            continue
        for m in range(1, len(c) - 1):
            r = np.vstack([c[m:-1], c[:m + 1]])
            if _simple(_L(r)):
                res[k] = r; break
        if _closed(res[k]) and not _simple(_L(res[k])):
            stats["ring_open"] = stats.get("ring_open", 0) + 1
            import kerbnet
            fr, to = _RT   # untied where it touches, in the coordinates readers get
            q = np.array([to(*[round(v, 8) for v in fr(x, y)]) for x, y in res[k]])
            parts = [p for p in kerbnet.deknot([q[:-1]], {}) if _simple(_L(p))]
            res[k] = parts[0] if parts else res[k]; res.extend(parts[1:])
    stats["ring_seat"] = n
    return res


def clean(out, streets, bridge_lines, lots, stats, tunnels=(), level=None, local_bridges=()):
    OVER[:] = bridge_lines; TUNNELS_G[:] = list(tunnels)
    # i (h gaps 19-29 m at rail and creek bridges, one side drawn and the other not): a local street's short bridge carries its
    # kerbs over like any street; the walk goes on over it and bridges() leaves kerbs beside it alone
    short = [b for b in local_bridges if b.length <= BRIDGE_SHORT]
    same = lambda b, t: b.distance(t) < 0.5 and b.hausdorff_distance(t) < 1.0   # the same centreline (cells hold copies)
    bridge_lines = [b for b in bridge_lines if not any(same(b, t) for t in tunnels)] if tunnels else bridge_lines
    bridge_lines = [b for b in bridge_lines if not any(same(b, t) for t in short)]
    STOP[:] = bridge_lines; SHORT[:] = short
    streets = list(streets) + short
    out = [np.asarray(o) for o in out if len(o) > 1]
    over = STRtree(list(tunnels) + list(OVER)) if (list(tunnels) or OVER) else None
    MAIN[:] = [(g, fh) for g, fh in (level or []) if fh in SCOPE_W   # j: a main road in a tunnel or on a bridge has no ground width
               and not (over is not None and any(same(g, over.geometries[int(k)]) for k in over.query(g, predicate="dwithin", distance=0.5)))]
    LOTS[:] = list(lots or []); _MT[:] = []
    global FH7
    l7 = [g for g, fh in (level or []) if fh == 7]; FH7 = STRtree(l7) if l7 else None
    S = lambda f, *a: (lambda o: f(o, *a))
    steps = [("end_hooks", S(end_hooks, stats)), ("bridges", S(bridges, bridge_lines, stats)), ("streetless", S(streetless, streets, stats)), ("away", S(away, streets, stats)),
             ("hairpins", S(hairpins, streets, stats)), ("folds", S(folds, stats)), ("doubles", S(doubles, streets, lots, stats)),
             ("junctions", S(junctions_all, streets, stats)), ("caps", S(caps, streets, stats)), ("corner_join", S(corner_join, streets, stats)),
             ("unroad", S(unroad, streets, stats)),
             ("on_centre", S(on_centre, streets, stats)),
             ("in_lots", S(in_lots, streets, lots, stats)),   # j: never inside a property; redrawn by sides / extend after
             ("sides", S(sides, streets, level, lots, stats)),   # i: a street side with no kerb gets one (own or other side's offset)
             ("extend", S(extend, streets, stats)),   # h: every cut is redrawn: free ends carried on along their street, then closed
             ("close_near", S(close_near, streets, stats)), ("caps", S(caps, streets, stats)), ("corner_join", S(corner_join, streets, stats)),
             ("fillets", S(fillets, stats)), ("junctions", S(junctions_all, streets, stats)), ("besides", S(besides, stats)),
             ("close_near", S(close_near, streets, stats)), ("flare", S(flare, streets, stats)),
             ("extend", S(extend, streets, stats)),   # ends opened again by the steps since
             ("junctions", S(junctions_all, streets, stats)),
             ("main_tails", S(main_tails, streets, stats)),
             ("lane_caps", S(caps, streets, stats, False, LANE_CAP_MIN, LANE_CAP_MAX)),   # i: leftovers along a main road (the scope cut made again, nearest street only)
             ("close_near", S(close_near, streets, stats)), ("flare", S(flare, streets, stats)), ("corner_join", S(corner_join, streets, stats)),
             ("besides", S(besides, stats)), ("folds", S(folds, stats)),
             ("in_lots", S(in_lots, streets, lots, stats)),
             ("close_near", S(close_near, streets, stats)),
             ("pair_join", S(pair_join, streets, stats)),   # j: a kerb broken at a driveway is one kerb
             ("off_centre_ends", S(off_centre_ends, streets, stats)),
             ("short", lambda o: [c for c in o if _L(c).length >= KEEP_MIN]),   # i: a stub about to go must not hold an end shut
             ("near_ends", S(near_ends, streets, stats)),
             ("corner_join", S(corner_join, streets, stats)),
             ("lane_caps", S(caps, streets, stats, False, LANE_CAP_MIN, LANE_CAP_MAX)),   # corners flared since
             ("besides", S(besides, stats)), ("ring_shut", S(ring_shut, stats)), ("despike", S(despike, stats)), ("pair_join", S(pair_join, streets, stats)), ("endtrim", S(endtrim, stats)), ("endfix", S(endfix, stats)),
             ("ringseat", S(ringseat, stats)), ("ring_shut", S(ring_shut, stats)),
             ("roundabouts", S(roundabouts, level, lots, stats)),   # j: a local roundabout's island
             ("guard", S(guard, stats))]   # j: the reviewer's shape rules once more
    import os
    trace = os.environ.get("KERBG_TRACE")
    for name, f in steps:
        out = f(out)
        if trace:
            print("  after", name, len(out), "near", _near_count(out), flush=True)
        if os.environ.get("KERBG_WATCH"):
            wx, wy = map(float, os.environ["KERBG_WATCH"].split(","))
            print("  watch", name, [(round(_L(o).length), [round(v, 1) for v in o[k]]) for o in out for k in (0, -1)
                                    if np.hypot(o[k][0] - wx, o[k][1] - wy) < 8], flush=True)
    for k in list(stats):
        if isinstance(stats[k], float):
            stats[k] = int(stats[k])
    return [o for o in out if _L(o).length >= KEEP_MIN]


EXT_MAX, EXT_STEP, EXT_HIT, EXT_MIN = 150.0, 1.0, 1.2, 2.0   # m
EXT_OFF_LO, EXT_OFF_HI, EXT_TURN = 1.3, 12.0, 50.0   # m, m, deg (i: lo was 0.5 - a walk under 1.3 m off a centreline drew a line down the middle of the street)
EXT_MEET = 14.0   # m, a free end of the kerb alongside this far ahead is met with an S curve
EXT_ACROSS = 2.2   # m, a kerb alongside this near on either side stops the walk (the reviewer's dup is 2 m)
EXT_BESIDE = 3.0   # m, a kerb running alongside this near stops the walk (the reviewer's dup is 2 m, merge 3 m)


def _unit(v):
    n = np.hypot(*v)
    return v / n if n > 1e-9 else v


def _street_dir(r, s):
    a = r.interpolate(max(0.0, s - 1.0)); b = r.interpolate(min(r.length, s + 1.0))
    return _unit(np.array([b.x - a.x, b.y - a.y]))


def _walk(e, h, i, streets, st, G, tree, maxlen=EXT_MAX):
    """from a free end e heading h, carry the kerb on along its street at the offset it already has, until it meets another kerb
    ('kerb'), reaches a cross street ('junction'), the street ends ('dead'), turns away ('turn') or EXT_MAX is reached ('far')"""
    p = np.array([e.x, e.y]); u = np.array([np.cos(h), np.sin(h)])
    k0 = int(st.nearest(e)); r0 = streets[k0]; d0 = r0.distance(e)
    if not (EXT_OFF_LO <= d0 <= EXT_OFF_HI):
        return None, "off"
    pts = [p.copy()]; walked = 0.0; cur = k0
    while walked < maxlen:
        P = Point(*p); r = streets[cur]; s_ = r.project(P)
        if s_ <= 0.05 or s_ >= r.length - 0.05:
            nb = [int(k) for k in st.query(P, predicate="dwithin", distance=d0 + 3.0) if int(k) != cur]
            nb = [k for k in nb if abs(streets[k].distance(P) - d0) < 2.0 and 0.05 < streets[k].project(P) < streets[k].length - 0.05]
            if not nb:
                return pts, "dead"
            cur = nb[0]; r = streets[cur]; s_ = r.project(P)
        t = _street_dir(r, s_)
        if np.dot(t, u) < 0:
            t = -t
        if np.degrees(np.arccos(np.clip(np.dot(t, u), -1, 1))) > EXT_TURN:
            return pts, "turn"
        q = p + EXT_STEP * t; Q = Point(*q)
        cands = [int(k) for k in st.query(Q, predicate="dwithin", distance=d0 + 2.0)]
        best = min(cands, key=lambda k: streets[k].distance(Q)) if cands else cur
        rq = streets[cur] if cur in cands else streets[best]
        foot = rq.interpolate(rq.project(Q)); n = _unit(np.array([Q.x - foot.x, Q.y - foot.y]))
        q = np.array([foot.x, foot.y]) + n * d0; Q = Point(*q)
        for k in cands:   # another street this close: the kerb has reached the cross street's kerb line (a corner)
            if k == cur or (_along_short(streets[k], 0.0) and not _along_short(streets[cur], 0.0)):
                continue
            rk = streets[k]; sk = rk.project(Q)
            if rk.distance(Q) < d0 + 1.0 and _ang(np.arctan2(t[1], t[0]), np.arctan2(*_street_dir(rk, sk)[::-1])) > 30:
                return pts, "junction"
        if _main_near(Q, streets[cur].distance(Q)):
            return pts, "main"   # i: a main road is out of scope: the kerb stops at its edge, never runs on along it
        if any(b.distance(Q) < d0 + 2.0 and _ang(np.arctan2(t[1], t[0]), _hd(b, b.project(Q), 1.0)) < 30 for b in STOP):
            return pts, "bridge"   # i: only a bridge along the street; an overpass crossing above it does not stop the kerb
        hq = np.arctan2(t[1], t[0])
        if any(_ang(hq, _hd(G[int(k)], G[int(k)].project(Q), 2.0)) < 25 and G[int(k)].distance(Q) > 0.05
               and not len(st.query(LineString([Q, G[int(k)].interpolate(G[int(k)].project(Q))]), predicate="intersects"))
               for k in tree.query(Q, predicate="dwithin", distance=EXT_BESIDE) if int(k) != i):
            for k in tree.query(Q, predicate="dwithin", distance=EXT_BESIDE + EXT_MEET):   # the kerb ahead, drawn a little off line
                k = int(k)
                if k == i or _closed(np.asarray(G[k].coords)):
                    continue
                for c0 in (G[k].coords[0], G[k].coords[-1]):
                    c0 = np.array(c0); dv = c0 - p; dl = np.hypot(*dv)
                    if 0.5 < dl < EXT_MEET and np.dot(dv / dl, u) > 0.8 and _free(G, tree, k, Point(*c0)):
                        tail = c0 + (np.array(G[k].interpolate(2.0 if np.allclose(c0, G[k].coords[0]) else G[k].length - 2.0).coords[0]) - c0)
                        v1 = _unit(tail - c0)
                        bz = _bez(p, p + dl / 3 * u, c0 - dl / 3 * v1, c0, 10)
                        if not any(int(m) not in (i, k) and G[int(m)].intersects(LineString(bz)) for m in tree.query(LineString(bz))):
                            return pts + list(bz[1:]), "kerb"
            ks = [int(k) for k in tree.query(Q, predicate="dwithin", distance=EXT_BESIDE) if int(k) != i]
            k = min(ks, key=lambda k: G[k].distance(Q)); o = G[k]; s2 = o.project(Q)
            s3 = s2 + (4.0 if np.dot(_street_dir(o, s2), u) > 0 else -4.0)
            if 0.0 <= s3 <= o.length:   # run into it a few metres on: one kerb (a tail it leaves behind goes in junctions())
                f = o.interpolate(s3); c0 = np.array([f.x, f.y]); dl = np.hypot(*(c0 - p))
                bz = _bez(p, p + dl / 3 * u, c0, c0, 8)
                if not any(int(m) not in (i, k) and G[int(m)].intersects(LineString(bz)) for m in tree.query(LineString(bz))) \
                        and not LineString(bz[:-1]).intersects(o):
                    return pts + list(bz[1:]), "kerb"
            return pts, "beside"   # another kerb runs alongside here: carrying on would double it
        if len(pts) > 1 and any(_ang(hq, _hd(G[int(k)], G[int(k)].project(Q), 2.0)) < 25 and G[int(k)].distance(Q) > 0.05
                                for k in tree.query(Q, predicate="dwithin", distance=EXT_ACROSS) if int(k) != i):
            return pts, "narrow"   # the kerb across is this close: a footway or a median, not a street to line
        hit = [int(k) for k in tree.query(Q, predicate="dwithin", distance=EXT_HIT) if int(k) != i]
        if not hit and len(pts) > 6:
            own = G[i] if i is not None else None
            if own is not None and own.distance(Q) < EXT_HIT:
                return pts, "self"
        if hit:
            k = min(hit, key=lambda k: G[k].distance(Q)); f = G[k].interpolate(G[k].project(Q))
            pts.append(np.array([f.x, f.y])); return pts, "kerb"
        if LineString([p, q]).intersects(G[i]) and len(pts) > 2:
            return pts, "self"
        pts.append(q); u = _unit(q - p); walked += EXT_STEP; p = q
    return pts, "far"


def _cells(q):
    cx, cy = int(q.x // 3), int(q.y // 3)
    return [(cx + a, cy + b) for a in (-1, 0, 1) for b in (-1, 0, 1)]


def extend(out, streets, stats, maxlen=EXT_MAX, keep=("kerb", "junction", "dead", "far", "bridge", "turn", "narrow", "main")):
    """h (g left holes, 'deleted, not fixed', and kerbs stopping short of junctions, bends and bridges): every free end is carried
    on along its street at its own offset until it meets a kerb, a cross street, a dead end or a bridge"""
    st = STRtree(streets); n = 0; m = 0.0
    for _ in range(3):
        G = [_L(o) for o in out]; tree = STRtree(G); ends = _free_ends(out, G, tree, minlen=6.0); grow = {}; taken = {}
        for i, j0, e, h in ends:
            pts, why = _walk(e, h, i, streets, st, G, tree, maxlen)
            if pts is None or why not in keep or len(pts) < 2:
                continue
            ext = LineString(pts)
            if ext.length < EXT_MIN and why != "kerb":
                continue
            if ext.length < 0.05:
                continue
            if why != "kerb" and any(int(k) != i and G[int(k)].intersects(ext) for k in tree.query(ext)):
                continue
            if why == "kerb" and any(int(k) != i and G[int(k)].distance(Point(pts[-1])) > 0.05 and G[int(k)].intersects(LineString(pts[:-1]))
                                     for k in tree.query(ext) if len(pts) > 2):
                continue
            smp = [ext.interpolate(t) for t in np.arange(0.5, ext.length, 1.0)]
            if any(q.distance(z) < EXT_BESIDE for q in smp for c in _cells(q) for z in taken.get(c, ())):
                continue   # another end's new piece already runs here this pass
            for q in smp:
                taken.setdefault((int(q.x // 3), int(q.y // 3)), []).append(q)
            grow.setdefault(i, [None, None])[j0] = np.asarray(pts); n += 1; m += ext.length
        if not grow:
            break
        res = []
        for i, o in enumerate(out):
            if i not in grow:
                res.append(o); continue
            c = np.asarray(o); a, b = grow[i]
            if a is not None:
                c = np.vstack([a[::-1][:-1], c])
            if b is not None:
                c = np.vstack([c, b[1:]])
            if not LineString(c).is_simple:
                c = np.asarray(o)
                if b is not None and LineString(np.vstack([c, b[1:]])).is_simple:
                    c = np.vstack([c, b[1:]])
                elif a is not None and LineString(np.vstack([a[::-1][:-1], c])).is_simple:
                    c = np.vstack([a[::-1][:-1], c])
            res.append(c)
        out = res
    stats["extend"] = stats.get("extend", 0) + n; stats["extend_m"] = stats.get("extend_m", 0) + m
    return out


CLOSE_AHEAD = 10.0   # m, a kerb straight ahead of a free end this near is closed onto too
CLOSE_D = 6.0   # m, a free end this near another kerb is closed onto it (the reviewer's near is 5 m)


def close_near(out, streets, stats):
    """h: a free end within CLOSE_D m of another kerb is closed onto it with a short round piece (a corner or a T), never cut back:
    to the other kerb's end when that is within 3 m of the nearest point (one line), else onto its side. Not across a street
    unless the street ends there (a dead-end cap), never across another kerb"""
    st = STRtree(streets); n = 0
    for _ in range(3):
        G = [_L(o) for o in out]; tree = STRtree(G); ends = _free_ends(out, G, tree, minlen=3.0); done = {}; busy = set()
        cand = []
        for i, j0, e, h in ends:
            for k in tree.query(e, predicate="dwithin", distance=CLOSE_AHEAD):
                k = int(k)
                if k == i:
                    continue
                o = G[k]; s_ = o.project(e); d = o.distance(e)
                if d < TOUCH:
                    continue
                if d > CLOSE_D:   # farther off: only a kerb straight ahead of the end (the cross street's kerb at a mouth)
                    f = o.interpolate(s_)
                    if np.cos(h) * (f.x - e.x) / d + np.sin(h) * (f.y - e.y) / d < 0.8:
                        continue
                cand.append((d, i, j0, e, h, k, s_))
        for d, i, j0, e, h, k, s_ in sorted(cand, key=lambda x: x[0]):
            if (i, j0) in done or i in busy or k in busy:
                continue
            o = G[k]; p0 = np.array([e.x, e.y]); u0 = np.array([np.cos(h), np.sin(h)])
            to_end = None
            if not _closed(out[k]):
                for k1, sv in ((0, 0.0), (1, o.length)):
                    if abs(s_ - sv) < 3.0 and _free(G, tree, k, Point(o.coords[0 if k1 == 0 else -1])):
                        to_end = k1
            if to_end is not None:
                q = o.coords[0 if to_end == 0 else -1]; p1 = np.array(q)
                hb = _hd(o, 0.0 if to_end == 0 else o.length, 3.0) + (np.pi if to_end == 0 else 0.0)
                u1 = np.array([np.cos(hb), np.sin(hb)])
            else:
                f = o.interpolate(s_); p1 = np.array([f.x, f.y]); u1 = None
                if _ang(h, _hd(o, s_, 2.0)) < TEE_ANG:   # sliding into its side: a Y, not a corner
                    continue
            dd = np.hypot(*(p1 - p0))
            if dd < 0.05:
                continue
            if np.dot(u0, (p1 - p0) / dd) < -0.2:   # behind the end: not where this kerb was going
                continue
            kk = dd / 3
            curve = _bez(p0, p0 + kk * u0, p1 + (kk * u1 if u1 is not None else kk * 0.0 * u0), p1, 8)
            cl = LineString(curve)
            if len(st.query(cl, predicate="intersects")):
                mid = cl.interpolate(0.5, normalized=True)
                if not _end_dead(mid, streets, st, dd / 2 + CAP_END):
                    continue
            if any(int(m) not in (i, k) and G[int(m)].intersects(cl) for m in tree.query(cl)):
                continue
            if LineString(curve[:-1]).intersects(o) if len(curve) > 2 else False:
                continue
            a = np.asarray(out[i]) if j0 == 1 else np.asarray(out[i])[::-1]
            if to_end is not None:
                b = np.asarray(out[k]) if to_end == 0 else np.asarray(out[k])[::-1]
                c = np.vstack([a, curve[1:-1], b])
                if not LineString(c).is_simple:
                    continue
                done[(i, j0)] = ("join", k, c); busy.update((i, k))
            else:
                c = np.vstack([a, curve[1:]])
                if not LineString(c).is_simple:
                    continue
                done[(i, j0)] = ("tee", None, c); busy.add(i)
        if not done:
            break
        drop = set(); add = []
        for (i, j0), (kind, k, c) in done.items():
            drop.add(i); add.append(c); n += 1
            if kind == "join":
                drop.add(k)
        out = [o for q, o in enumerate(out) if q not in drop] + add
    stats["close_near"] = stats.get("close_near", 0) + n
    return out


FLARE_AHEAD, FLARE_R0, FLARE_R1 = 14.0, 2.0, 4.0   # m


def flare(out, streets, stats):
    """h: a narrow street's kerb that stops at the mouth onto a cross street with no kerb of its own side to turn into (a main road,
    out of scope) is given its corner: a quarter circle turning away from its street, as a kerb return does, so the two kerbs of the
    lane no longer end facing each other a few metres apart"""
    st = STRtree(streets); n = 0
    G = [_L(o) for o in out]; tree = STRtree(G); ends = _free_ends(out, G, tree, minlen=6.0); grow = {}
    for i, j0, e, h in ends:
        nr = [(G[int(k)].distance(e), int(k)) for k in tree.query(e, predicate="dwithin", distance=NEAR_D) if int(k) != i]
        own = int(st.nearest(e)); r0 = streets[own]; s0 = r0.project(e); hs = _hd(r0, s0, 2.0)
        ahead = None; over = False
        for t in np.arange(0.0, FLARE_AHEAD, 0.5):
            q = Point(e.x + t * np.cos(h), e.y + t * np.sin(h))
            for m in st.query(q, predicate="dwithin", distance=2.0):
                m = int(m)
                if m != own and _ang(hs, _hd(streets[m], streets[m].project(q), 2.0)) > 30:
                    ahead = t; break
            if ahead is None and any(b.distance(q) < 2.0 and _ang(hs, _hd(b, b.project(q), 2.0)) > 30 for b in OVER):
                ahead = t; over = True   # i (h gaps 19-21 m): a cross street on a bridge is a mouth too, kerb near or not
            if ahead is not None:
                break
        if ahead is None or (not nr and not over):
            continue
        foot = r0.interpolate(s0); side = _unit(np.array([e.x - foot.x, e.y - foot.y]))
        u = np.array([np.cos(h), np.sin(h)]); w = side - np.dot(side, u) * u
        if np.hypot(*w) < 0.3:
            continue
        w = _unit(w); R0 = float(np.clip(ahead + 1.0, FLARE_R0, FLARE_R1)); p0 = np.array([e.x, e.y])
        for R in (R0, 0.7 * R0, 0.45 * R0):
            a = np.linspace(0, np.pi / 2, 12)[1:]
            arc = p0 + R * (np.sin(a)[:, None] * u + (1 - np.cos(a))[:, None] * w)
            cl = LineString(np.vstack([p0, arc]))
            if len(st.query(cl, predicate="intersects")):
                continue
            hits = [cl.project(cl.intersection(G[int(m)]).representative_point()) for m in tree.query(cl)
                    if int(m) != i and G[int(m)].intersects(cl)]
            if hits:   # the corner meets the cross street's kerb: it ends on it (a closed corner)
                t = min(hits)
                if t < 0.3:
                    break
                arc = np.asarray(substring(cl, 0, t).coords)[1:]
            grow.setdefault(i, [None, None])[j0] = arc
            break
    res = []
    for i, o in enumerate(out):
        c = np.asarray(o)
        if i in grow:
            a0, a1 = grow[i]
            c2 = c
            if a1 is not None:
                c2 = np.vstack([c2, a1])
            if a0 is not None:
                c2 = np.vstack([a0[::-1], c2])
            if LineString(c2).is_simple:
                c = c2; n += (a0 is not None) + (a1 is not None)
        res.append(c)
    stats["flare"] = stats.get("flare", 0) + n
    return res


UNROAD_MIN, UNROAD_K, UNROAD_MAX = 2.5, 0.8, 25.0   # m, ratio, m


def unroad(out, streets, stats):
    """h: a free end lying in a cross street's carriageway (a kerb run on into the junction, or across a main road) is taken back
    to that street's kerb line, where extend / close_near / flare then turn its corner"""
    st = STRtree(streets); n = 0; m = 0.0
    G = [_L(o) for o in out]; tree = STRtree(G); cut = {}
    for i, j0, e, h in _free_ends(out, G, tree, minlen=UNROAD_MAX + KEEP_MIN):
        g = G[i]; at = (lambda t: g.interpolate(t)) if j0 == 0 else (lambda t: g.interpolate(g.length - t))
        ref = at(10.0); own = int(st.nearest(ref)); dref = streets[own].distance(ref); hs = _hd(streets[own], streets[own].project(ref), 2.0)
        lim = max(UNROAD_MIN, UNROAD_K * dref)
        def inroad(p):
            for k in st.query(p, predicate="dwithin", distance=lim):
                k = int(k); r = streets[k]
                if k != own and r.distance(p) < lim and _ang(hs, _hd(r, r.project(p), 2.0)) > 30:
                    return True
            return False
        t = 0.0
        while t < UNROAD_MAX and inroad(at(t)):
            t += 0.5
        if t > 0:
            cut.setdefault(i, [0.0, 0.0])[j0] = t
    res = []
    for i, o in enumerate(out):
        if i not in cut:
            res.append(o); continue
        g = G[i]; a, b = cut[i][0], g.length - cut[i][1]
        if b - a < KEEP_MIN:
            res.append(o); continue
        n += 1; m += g.length - (b - a)
        res.append(np.asarray(substring(g, a, b).coords))
    stats["unroad"] = n; stats["unroad_m"] = m
    return res


SIDE_STEP, SIDE_RAY, SIDE_RUN, SIDE_END, SIDE_NEAR, SIDE_MIN_OFF = 2.0, 14.0, 12.0, 10.0, 30.0, 2.2   # m
SIDE_LOT, SIDE_AROUND, SIDE_MAX_OFF = 25.0, 40.0, 12.0   # m
SIDE_PAR, SIDE_SHARE, SIDE_CLEAR, SIDE_KEEP = 35.0, 0.25, 3.5, 10.0   # deg, share of a side, m, m
SCOPE_W = {1: 14.0, 2: 11.0, 3: 11.0, 4: 8.5}   # m, kerbnet.SCOPE_W: a main road's carriageway and verge band


def _rays(g, ts, s, reach):
    import shapely
    P = shapely.line_interpolate_point(g, ts)
    A = np.array([[p.x, p.y] for p in shapely.line_interpolate_point(g, np.maximum(ts - 1.0, 0))])
    B = np.array([[p.x, p.y] for p in shapely.line_interpolate_point(g, np.minimum(ts + 1.0, g.length))])
    T = B - A; T /= np.maximum(np.hypot(T[:, 0], T[:, 1]), 1e-9)[:, None]
    N = np.stack([-T[:, 1], T[:, 0]], 1) * s
    P0 = np.array([[p.x, p.y] for p in P])
    return P0, T, N, shapely.linestrings(np.stack([P0, P0 + N * reach], 1))


def sides(out, streets, level, lots, stats):
    """i (h review: a whole street with no kerbs, one side of a street missing along the whole tile, both 'deleted, not fixed'):
    every local street (fh 5-7) is walked on both sides; where a side has no kerb for SIDE_RUN m or more, with no cross street in
    the way (a mouth), a kerb is drawn at that side's own offset elsewhere on the street, else at the other side's (a street is about
    symmetric), else for a lane with nothing drawn at either side, just inside the property line. The ends are then joined by extend /
    close_near / corner_join like any other free end. Never within SIDE_CLEAR m of another kerb, across a street, on a main road or
    in a lot."""
    import shapely, os
    if not level:
        return out
    fh_of = {g.wkb: fh for g, fh in level}
    lvt = STRtree([g for g, _ in level])
    def fh_get(g):   # the same centreline may come back with other coordinates (another cell's copy): match by shape
        if g.wkb in fh_of:
            return fh_of[g.wkb]
        c = [(level[int(k)][0].hausdorff_distance(g), level[int(k)][1]) for k in lvt.query(g, predicate="dwithin", distance=1.0)]
        c = [x for x in c if x[0] < 2.0]
        return min(c)[1] if c else None
    st = STRtree(streets)
    main = [g for g, fh in level if fh in SCOPE_W]; mt = STRtree(main) if main else None
    G = [_L(o) for o in out]; Ga = np.array(G, dtype=object); gt = STRtree(G)
    lt = STRtree(lots) if lots else None; La = np.array(lots, dtype=object) if lots else None
    new = []; nt = None; n = 0; m = 0.0
    def hits(rays, P0, T, arr, tree, own=None, par=False):
        d = np.full(len(rays), np.inf)
        ri, ki = tree.query(rays, predicate="intersects")
        if own is not None:
            keep = ki != own; ri, ki = ri[keep], ki[keep]
        if not len(ri):
            return d
        X = shapely.intersection(rays[ri], arr[ki])
        C = shapely.centroid(X); dd = shapely.distance(shapely.points(P0[ri]), C)
        if par:
            s_ = shapely.line_locate_point(arr[ki], C)
            a = shapely.line_interpolate_point(arr[ki], np.maximum(s_ - 1.0, 0)); b = shapely.line_interpolate_point(arr[ki], s_ + 1.0)
            v = shapely.get_coordinates(b) - shapely.get_coordinates(a)
            v /= np.maximum(np.hypot(v[:, 0], v[:, 1]), 1e-9)[:, None]
            ok = np.abs(np.sum(v * T[ri], 1)) > np.cos(np.radians(SIDE_PAR))
            ri, dd = ri[ok], dd[ok]
        np.minimum.at(d, ri, dd)
        return d
    sa = np.array(streets, dtype=object)
    def lot_d(rays, P0):   # distance along each ray to the first property lot (a road parcel holding the centreline is not one)
        d = np.full(len(rays), np.inf)
        if lt is None:
            return d
        li, lk = lt.query(rays, predicate="intersects")
        if not len(li):
            return d
        inside = shapely.contains(La[lk], shapely.points(P0[li])); li, lk = li[~inside], lk[~inside]
        np.minimum.at(d, li, shapely.distance(shapely.points(P0[li]), shapely.intersection(rays[li], La[lk])))
        return d
    todo = []; verge = {}; koff = {}
    for gi, g in enumerate(streets):
        fh = fh_get(g)
        if fh not in (5, 6, 7) or g.length < 2 * SIDE_END + SIDE_RUN:
            continue
        ts = np.arange(SIDE_END, g.length - SIDE_END + 0.01, SIDE_STEP)
        R = {}
        for s in (1, -1):
            P0, T, N, rays = _rays(g, ts, s, SIDE_RAY)
            anyk = hits(rays, P0, T, Ga, gt)
            park = hits(rays, P0, T, Ga, gt, par=True)
            mouth = hits(rays, P0, T, sa, st, own=gi)
            lotd = lot_d(_rays(g, ts, s, SIDE_LOT)[3], P0)
            R[s] = (P0, N, anyk, park, mouth, lotd)
            c = np.isfinite(park) & (park < mouth) & np.isfinite(lotd)
            verge.setdefault(fh, []).extend((lotd[c] - park[c]).tolist())
            c2 = np.isfinite(park) & (park < mouth)
            koff.setdefault(fh, []).extend(park[c2].tolist())
        todo.append((gi, g, fh, ts, R))
    # the verge (kerb to property line) each street class has where both are known: a side with nothing to copy is drawn there
    VG = {f: float(np.median([x for x in v if -0.5 <= x <= 8.0])) for f, v in verge.items() if len([x for x in v if -0.5 <= x <= 8.0]) > 50}
    stats["sides_verge"] = {str(f): round(v, 2) for f, v in VG.items()}
    # j (i review V32: a street arm between drawn streets with nothing either side and a park, not lots, on one side): the class's
    # usual kerb offset where neither a kerb nor a property line is there to measure from
    KO = {f: float(np.median([x for x in v if SIDE_MIN_OFF <= x <= SIDE_MAX_OFF])) for f, v in koff.items()
          if len([x for x in v if SIDE_MIN_OFF <= x <= SIDE_MAX_OFF]) > 50}
    stats["sides_koff"] = {str(f): round(v, 2) for f, v in KO.items()}
    for gi, g, fh, ts, R in todo:
        cov = {s: np.isfinite(R[s][3]) & (R[s][3] < R[s][4]) for s in R}
        if os.environ.get('KERBG_SIDES_DBG'):
            print('street', fh, round(g.length), round(cov[1].mean(), 2), round(cov[-1].mean(), 2), [round(v) for v in g.coords[0]])
        if not (cov[1].mean() >= SIDE_SHARE or cov[-1].mean() >= SIDE_SHARE):
            # nothing drawn either side: inside the drawn area (kerbs around it) and between property lots, else left alone
            ends_drawn = all(len(gt.query(Point(g.coords[x]), predicate="dwithin", distance=SIDE_RAY)) for x in (0, -1))
            if not len(gt.query(g.interpolate(0.5, normalized=True), predicate="dwithin", distance=SIDE_AROUND)) \
                    or (min(np.isfinite(R[1][5]).mean(), np.isfinite(R[-1][5]).mean()) < 0.5 and not ends_drawn):
                continue
        for s in (1, -1):
            P0, N, anyk, park, mouth, lotd = R[s]
            miss = ~(np.isfinite(anyk) & (anyk < mouth)) & ~np.isfinite(mouth)
            if not miss.any():
                continue
            # the offset where it is missing: this side's own kerb within SIDE_NEAR m along, else the other side's (mirrored) there,
            # else the property line less the street class's verge
            offs = np.full(len(ts), np.nan)
            ok_off = lambda v: v is not None and np.isfinite(v) and SIDE_MIN_OFF <= v <= SIDE_MAX_OFF
            for k in np.nonzero(miss)[0]:
                # j (i review tiles 2, 8: the first offset found was under SIDE_MIN_OFF, so nothing was drawn): the first offset
                # in this order that is a street kerb's is used
                cands = []
                for side, reach in ((s, SIDE_NEAR), (-s, SIDE_NEAR / 2)):
                    w = cov[side] & (np.abs(ts - ts[k]) <= reach)
                    if w.sum() >= 3:
                        if side == -s and np.isfinite(lotd[k]):
                            # j (i review tile 2: the other side's kerb 1.7 m off a centreline drawn off the middle): a street is
                            # symmetric about its reserve, not its centreline: this side's property line less the other side's verge
                            wv = w & np.isfinite(R[side][5])
                            if wv.sum() >= 3:
                                vg = float(np.median(R[side][5][wv] - R[side][3][wv]))
                                if -0.5 <= vg <= 8.0:
                                    cands.append(lotd[k] - vg)
                        cands.append(float(np.median(R[side][3][w])))
                if fh in VG and np.isfinite(lotd[k]):
                    cands.append(lotd[k] - VG[fh])
                if fh in KO:
                    cands.append(KO[fh])
                for v in cands:
                    if ok_off(v):
                        offs[k] = v; break
            miss &= np.isfinite(offs)
            if not miss.any():
                continue
            off = None
            if os.environ.get('KERBG_SIDES_DBG'):
                print('sides', fh, s, round(g.length), 'own', round(cov[s].mean(), 2), 'oth', round(cov[-s].mean(), 2), 'off', off, int(miss.sum()), [round(v) for v in g.coords[0]])
            if off is not None:
                offs = np.full(len(ts), off)
            fin = np.nonzero(np.isfinite(offs))[0]
            offs = np.interp(np.arange(len(offs)), fin, offs[fin])
            if len(offs) >= 5:   # smoothed along the street
                offs = np.convolve(np.pad(offs, 2, mode="edge"), np.ones(5) / 5, mode="valid")
            Q = P0 + N * offs[:, None]
            ok = miss & (offs >= SIDE_MIN_OFF) & (offs <= SIDE_MAX_OFF)
            Qp = shapely.points(Q)
            # clear of every kerb, of other streets (a cross street's carriageway), main roads and lots
            for k, q in enumerate(Qp):
                if not ok[k]:
                    continue
                if len(gt.query(q, predicate="dwithin", distance=SIDE_CLEAR)) or (nt is not None and len(nt.query(q, predicate="dwithin", distance=SIDE_CLEAR))):
                    ok[k] = False; continue
                if any(int(j) != gi and streets[int(j)].distance(q) < max(offs[k] - 1.0, 1.5) for j in st.query(q, predicate="dwithin", distance=offs[k])):
                    ok[k] = False; continue
                if mt is not None and any(main[int(j)].distance(q) < SCOPE_W[fh_of.get(main[int(j)].wkb, 4)] for j in mt.query(q, predicate="dwithin", distance=14.0)):
                    ok[k] = False; continue
                if lt is not None and any(lots[int(j)].contains(q) and lots[int(j)].exterior.distance(q) > 1.0 for j in lt.query(q)):
                    ok[k] = False
            k = 0
            while k < len(ok):
                if not ok[k]:
                    k += 1; continue
                j = k
                while j + 1 < len(ok) and ok[j + 1]:
                    j += 1
                if (j - k) * SIDE_STEP >= SIDE_KEEP:
                    c = Q[k:j + 1]; cl = LineString(c)
                    if cl.is_simple and not len(st.query(cl, predicate="crosses")) and not len(gt.query(cl, predicate="intersects")):
                        new.append(c); n += 1; m += cl.length
                k = j + 1
        if new:
            nt = STRtree([_L(x) for x in new])
    stats["sides"] = n; stats["sides_m"] = int(m)
    return out + new


def _near_count(out):
    """the reviewer's near: a free end 1-5 m from another line"""
    G = [_L(o) for o in out if len(o) > 1]; tree = STRtree(G); n = 0
    for i, g in enumerate(G):
        if g.length < 3:
            continue
        for e in (Point(g.coords[0]), Point(g.coords[-1])):
            d = [G[int(k)].distance(e) for k in tree.query(e, predicate="dwithin", distance=NEAR_D) if int(k) != i]
            if d and min(d) >= TOUCH:
                n += 1
    return n


MAIN_REACH, MAIN_STEP, MAIN_SMOOTH, MAIN_KEEP, MAIN_OWN = 60.0, 4.0, 16.0, 5.0, 10.0   # m
LOTS = []   # j: property lots, to measure each main road's own width


def _main_widths():
    """j (i review V29, V43, V65, V78 and tile 30: kerbs on a main road's carriageway, across its junction, past its stop line,
    along a motorway's edge): a main road's width is not one number per class (SCOPE_W). Its property line is measured every
    MAIN_STEP m on each side (the first lot along a ray, a lot holding the centreline is a road parcel, not one), smoothed over
    +-MAIN_SMOOTH m with the street mouths (no lot) left out: (s, left, right) per main centreline"""
    import shapely
    lt = STRtree(LOTS) if LOTS else None; La = np.array(LOTS, dtype=object) if LOTS else None; W = []
    for g, fh in MAIN:
        ts = np.arange(0.0, g.length + 0.01, MAIN_STEP) if g.length > MAIN_STEP else np.array([0.0, g.length])
        row = [ts]
        for s in (1, -1):
            if lt is None:
                row.append(np.full(len(ts), np.nan)); continue
            P0, T, N, rays = _rays(g, ts, s, MAIN_REACH)
            d = np.full(len(ts), np.inf)
            li, lk = lt.query(rays, predicate="intersects")
            if len(li):
                inside = shapely.contains(La[lk], shapely.points(P0[li])); li, lk = li[~inside], lk[~inside]
                np.minimum.at(d, li, shapely.distance(shapely.points(P0[li]), shapely.intersection(rays[li], La[lk])))
            sm = np.full(len(ts), np.nan)
            for k in range(len(ts)):
                w = d[(np.abs(ts - ts[k]) <= MAIN_SMOOTH) & np.isfinite(d)]
                if len(w) >= 3:
                    sm[k] = float(np.median(w))
            row.append(sm)
        W.append(row)
    return W


_MW = []


def _main_near(q, own_d):
    """q lies on a main road's carriageway: more than MAIN_KEEP m inside its property line on that side (j), or, where its width
    could not be measured, nearer to it than to q's own street and within its class band (i)"""
    if not MAIN:
        return False
    if not _MT or _MT[0] is not MAIN[0][0]:
        _MT[:] = [MAIN[0][0], STRtree([g for g, _ in MAIN])]
        _MW[:] = _main_widths()
    for j in _MT[1].query(q, predicate="dwithin", distance=MAIN_REACH):
        j = int(j); g, fh = MAIN[j]
        dd = g.distance(q)
        s_ = g.project(q); f = g.interpolate(s_); t = _street_dir(g, s_)
        side = 1 if t[0] * (q.y - f.y) - t[1] * (q.x - f.x) > 0 else -1
        ts, wl, wr = _MW[j]; w = wl if side == 1 else wr
        fin = np.nonzero(np.isfinite(w))[0]; W = np.nan
        if len(fin):
            k = fin[int(np.argmin(np.abs(ts[fin] - s_)))]
            if abs(ts[k] - s_) <= MAIN_SMOOTH + MAIN_STEP:
                W = float(w[k])
        if np.isfinite(W):
            if dd < W - MAIN_KEEP and dd < own_d + MAIN_OWN:   # a wide forecourt with no lots is not all carriageway
                return True
        elif dd < own_d and dd < SCOPE_W[fh]:
            return True
    return False


_MT = []


def main_tails(out, streets, stats):
    """i (h review V41, V65, V78: a zigzag on a motorway, a line along an arterial's kerb, side-street kerbs run on into a main
    road): any stretch of 4 m or more whose nearest street is a main road (fh 1-4), within its carriageway band, goes"""
    if not MAIN:
        return out
    st = STRtree(streets); res = []; cut = 0.0
    for o in out:
        g = _L(o)
        if not len(_MT_q(g)):
            res.append(o); continue
        ts = _samples(g)
        m = np.array([_main_near(g.interpolate(t), streets[int(st.nearest(g.interpolate(t)))].distance(g.interpolate(t))) for t in ts])
        m = _runs(m, ts, 4.0)
        if not m.any():
            res.append(o); continue
        res += _keep_runs(g, m, ts, stats, "main_tail_m")
    return res


def _MT_q(g):
    _main_near(Point(g.coords[0]), 0.0)
    return _MT[1].query(g, predicate="dwithin", distance=MAIN_REACH) if _MT else []


def end_hooks(out, stats):
    """i: a line whose last metres double back (a clip at the traced-area edge leaves a 2 m hook) loses the hook, so its end
    points the way the kerb runs and the walk carries it on (h: kerbs broken where 1 km cells meet, gap and self flags)"""
    res = []; n = 0
    for o in out:
        c = np.asarray(o)
        for _ in range(2):
            for end in (0, 1):
                while len(c) > 3:
                    a, b, d = (c[-3], c[-2], c[-1]) if end else (c[2], c[1], c[0])
                    v1, v2 = b - a, d - b; l2 = np.hypot(*v2)
                    if l2 < 3.0 and l2 > 0 and np.dot(v1, v2) / (np.hypot(*v1) * l2 + 1e-9) < -0.2:
                        c = c[:-1] if end else c[1:]; n += 1
                    else:
                        break
        res.append(c)
    stats["end_hooks"] = n
    return res


CENTRE_D, CENTRE_RUN = 1.5, 10.0   # m


def on_centre(out, streets, stats):
    """i (h tile 'good' 1: one line drawn down the middle of a street, its two kerbs missing): a stretch lying on a street's
    centreline (within CENTRE_D m, running along it for CENTRE_RUN m) is not a kerb; it goes, and sides() then draws both kerbs"""
    st = STRtree(streets); res = []
    for o in out:
        g = _L(o)
        if not len(st.query(g, predicate="dwithin", distance=CENTRE_D)):
            res.append(o); continue
        ts = _samples(g); m = np.zeros(len(ts), bool)
        for k, t in enumerate(ts):
            p = g.interpolate(t)
            for j in st.query(p, predicate="dwithin", distance=CENTRE_D):
                r = streets[int(j)]
                if _ang(_hd(g, t), _hd(r, r.project(p), 2.0)) < 20:
                    m[k] = True; break
        m = _runs(m, ts, CENTRE_RUN)
        res += [o] if not m.any() else _keep_runs(g, m, ts, stats, "on_centre_m")
    return res


def _lollipop(c, la):
    """i (h V87: a short kerb starting on another kerb's side and running round an island back to it): the joined line comes
    back onto its own start (or end); it is split there into the closed island ring and the kerb running on (a T, kept)"""
    L = LineString(c)
    for rev in (False, True):
        q = np.asarray(c[::-1]) if rev else np.asarray(c)
        Lq = LineString(q); P = Point(q[0]); lo = (L.length - la) if rev else la
        lo = min(max(lo, 1.0), Lq.length - 1.0)
        rest = substring(Lq, lo, Lq.length)
        if rest.distance(P) > TOUCH:
            continue
        s_t = lo + rest.project(P)
        if s_t < 8.0:
            continue
        ring = np.asarray(substring(Lq, 0, s_t).coords); ring = np.vstack([ring[:-1], ring[:1]])
        tail = np.asarray(substring(Lq, s_t, Lq.length).coords) if Lq.length - s_t >= KEEP_MIN else None   # a stub past the T goes
        if len(ring) > 3 and LineString(ring).is_simple and (tail is None or LineString(tail).is_simple):
            return ring, tail
    return None


NT_TRIM, NT_CLEAR = 8.0, 5.1   # m


NT_NOSTREET = 3.0   # m


def near_ends(out, streets, stats):
    """i (h near 177, cap ~145: a kerb end left 1-5 m from another kerb reads as a corner or join left open): last pass over the
    ends still open. An end pointing at the other kerb (35 deg or squarer) runs on straight onto it, a T, unless that crosses a
    street or another kerb; an end running alongside it is taken back until NT_CLEAR m clear when that costs at most NT_TRIM m"""
    st = STRtree(streets); n_t = n_c = 0
    G = [_L(o) for o in out]; tree = STRtree(G); grow = {}; cut = {}
    for i, j0, e, h in _free_ends(out, G, tree, minlen=3.0):
        nr = [(G[int(k)].distance(e), int(k)) for k in tree.query(e, predicate="dwithin", distance=NEAR_D) if int(k) != i]
        if not nr:
            continue
        d, k = min(nr); o = G[k]
        if d < TOUCH:
            continue
        f = o.interpolate(o.project(e)); u = np.array([np.cos(h), np.sin(h)])
        if _ang(h, _hd(o, o.project(e), 2.0)) >= TEE_ANG:
            seg = LineString([e, f])
            ahead = np.dot(u, np.array([f.x - e.x, f.y - e.y]) / max(d, 1e-9))
            # j (i review V93: a median nose left hooked 2.8 m off its other side, a centreline drawn through the nose): no street
            # fits in a gap under NT_NOSTREET m, so a centreline there does not stop the T
            if ahead > 0.5 and (d < NT_NOSTREET or not len(st.query(seg, predicate="intersects"))) \
                    and not any(int(m) not in (i, k) and G[int(m)].intersects(seg) for m in tree.query(seg)):
                grow.setdefault(i, [None, None])[j0] = np.array([f.x, f.y]); n_t += 1
                continue
        g = G[i]; t = 0.0
        while t <= NT_TRIM and o.distance(g.interpolate(t if j0 == 0 else g.length - t)) < NT_CLEAR:
            t += 0.5
        if t <= NT_TRIM and g.length - t >= KEEP_MIN:
            cut.setdefault(i, [0.0, 0.0])[j0] = t; n_c += 1
    res = []
    for i, o in enumerate(out):
        c = np.asarray(o); g = G[i]
        if i in cut:
            a, b = cut[i]; c = np.asarray(substring(g, a, g.length - b).coords)
        if i in grow:
            a0, a1 = grow[i]
            c2 = c
            if a1 is not None and (i not in cut or cut[i][1] == 0):
                c2 = np.vstack([c2, a1[None]])
            if a0 is not None and (i not in cut or cut[i][0] == 0):
                c2 = np.vstack([a0[None], c2])
            if LineString(c2).is_simple:
                c = c2
        res.append(c)
    stats["near_tee"] = n_t; stats["near_trim"] = n_c
    return res


def despike(out, stats):
    """i (self flags where a walk or a join met its line: vertices a few mm apart doubling back, a knot once rounded): repeated
    vertices (under 5 cm apart) go, and so does a vertex where the line turns back on itself (over 150 deg) within 1 m"""
    res = []; n = 0
    for o in out:
        c = [np.asarray(p, float) for p in o]; ring = len(c) > 3 and np.hypot(*(c[0] - c[-1])) < 1e-6
        changed = True
        while changed and len(c) > 2:
            changed = False; k = 1
            while k < len(c) - 1:
                a, b, d = c[k - 1], c[k], c[k + 1]
                v1, v2 = b - a, d - b; l1, l2 = np.hypot(*v1), np.hypot(*v2)
                if l1 < 0.05 or (min(l1, l2) < 1.0 and l1 > 0 and l2 > 0 and np.dot(v1, v2) / (l1 * l2) < -0.866):
                    del c[k]; n += 1; changed = True
                else:
                    k += 1
            if len(c) > 2 and np.hypot(*(c[-1] - c[-2])) < 0.05 and not ring:
                del c[-2]; n += 1; changed = True
        res.append(np.array(c))
    stats["despike"] = n
    return res


def ring_shut(out, stats):
    """i (h fold at 337754 6248057: a block loop left 2 m open, its two ends side by side): a line whose own two ends lie within
    3 m of each other is closed into a ring; if that would cross itself, the shorter overlapping end is trimmed back instead"""
    res = []; n = 0
    for o in out:
        c = np.asarray(o); g = _L(c)
        if g.length > 30 and 1e-6 < np.hypot(*(c[0] - c[-1])) < 3.0:
            r = np.vstack([c, c[:1]])
            if _simple(LineString(r)):
                res.append(r); n += 1; continue
            for t in np.arange(0.5, 6.01, 0.5):
                for a, b in ((t, g.length), (0.0, g.length - t)):
                    q = np.asarray(substring(g, a, b).coords); r = np.vstack([q, q[:1]])
                    if np.hypot(*(q[0] - q[-1])) < 4.0 and _simple(LineString(r)):
                        break
                else:
                    continue
                break
            else:
                res.append(c); continue
            res.append(r); n += 1; continue
        res.append(c)
    stats["ring_shut"] = n
    return res


def _folds_near(c, k, reach=20.0):
    """the reviewer's fold (two points of one line under FOLD_D_REV m apart, more than FOLD_ALONG m apart along it) within reach
    m of vertex k"""
    g = LineString(c); s0 = g.project(Point(c[min(k, len(c) - 1)]))
    ts = np.arange(max(0.0, s0 - reach), min(g.length, s0 + reach), 1.0)
    P = [g.interpolate(t) for t in ts]
    for a in range(len(P)):
        for b in range(a + 9, len(P)):
            if P[a].distance(P[b]) < 2.6:
                return True
    return False


RB_AREA, RB_COMPACT, RB_LANE, RB_R = 2500.0, 0.8, 4.3, (3.5, 8.0)   # m2, isoperimetric ratio, m, m


def roundabouts(out, level, lots, stats):
    """j (i review V33: a local roundabout's raised island not drawn): a roundabout is a small round face of local centrelines
    (fh 5-7, on the ground) with no property lot in it; the spokes mapped into its middle split it, so neighbouring small faces
    are taken together. Its island is a circle one lane (RB_LANE m) inside the ring, drawn when nothing is drawn there yet and the
    island is big enough to be raised (RB_R)"""
    from shapely.ops import polygonize, unary_union
    if not level:
        return out
    over = STRtree(list(OVER) + list(TUNNELS_G)) if (OVER or TUNNELS_G) else None
    ground = [(g, fh) for g, fh in level if not (over is not None and len(over.query(g, predicate="dwithin", distance=0.5))
                                                    and any(over.geometries[int(k)].hausdorff_distance(g) < 1.0 for k in over.query(g, predicate="dwithin", distance=0.5)))]
    loc = [g for g, fh in ground if fh in (5, 6, 7)]
    if not loc:
        return out
    lt = STRtree(loc)
    faces = [f for f in polygonize(unary_union([g for g, _ in ground])) if f.area < RB_AREA]
    if not faces:
        return out
    ft = STRtree(faces); par = list(range(len(faces)))
    def root(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    for i, f in enumerate(faces):
        for k in ft.query(f, predicate="touches"):
            k = int(k)
            if k != i and f.boundary.intersection(faces[k].boundary).length > 1.0:
                par[root(i)] = root(k)
    grp = {}
    for i in range(len(faces)):
        grp.setdefault(root(i), []).append(faces[i])
    lot_t = STRtree(lots) if lots else None
    G = [_L(o) for o in out]; gt = STRtree(G) if G else None; n = 0
    for fs in grp.values():
        U = unary_union(fs)
        if U.geom_type != "Polygon" or U.area >= RB_AREA or 4 * np.pi * U.area / U.length ** 2 < RB_COMPACT:
            continue
        rim = U.exterior
        on = sum(seg.length for seg in [rim.intersection(loc[int(k)].buffer(0.5)) for k in lt.query(rim, predicate="dwithin", distance=0.5)])
        if on < 0.8 * rim.length:
            continue
        if lot_t is not None and any(lots[int(k)].representative_point().within(U) for k in lot_t.query(U)):
            continue
        R = float(np.sqrt(U.area / np.pi)); r = R - RB_LANE; c = U.centroid
        if not (RB_R[0] <= r <= RB_R[1]):
            continue
        if gt is not None and len(gt.query(c, predicate="dwithin", distance=r + 1.5)):
            continue
        ring = np.asarray(c.buffer(r, 16).exterior.coords)
        out = out + [ring]; n += 1
    stats["roundabouts"] = n
    return out


IN_LOT, IN_LOT_RUN = 2.0, 4.0   # m, m


def in_lots(out, streets, lots, stats):
    """j (i review tiles 1, 4, 5, 14, V42: a stub into a roof, lines across a depot forecourt, a kerb drifting into yards): a kerb
    lies in the street, never inside a property. Any stretch of IN_LOT_RUN m or more lying more than IN_LOT m inside a lot (a lot
    holding a street centreline is a road parcel or a private road, not one) is taken out; the ends left are carried on and joined
    by the steps after (extend, close_near, corner_join), so the kerb is redrawn along its street, not left open"""
    import shapely
    if not lots:
        return out
    lt = STRtree(lots); st = STRtree(streets); road = {}
    def prop(k):
        if k not in road:
            road[k] = len(st.query(lots[k], predicate="intersects")) == 0
        return road[k]
    res = []
    for o in out:
        g = _L(o); ks = [int(k) for k in lt.query(g, predicate="intersects")]
        ks = [k for k in ks if prop(k)]
        if not ks:
            res.append(o); continue
        ts = _samples(g, 0.5); P = shapely.line_interpolate_point(g, ts)
        m = np.zeros(len(ts), bool)
        for k in ks:
            L = lots[k]; c = shapely.contains(L, P)
            if c.any():
                ii = np.nonzero(c)[0]
                m[ii] |= shapely.distance(L.exterior, P[ii]) > IN_LOT
        m = _runs(m, ts, IN_LOT_RUN)
        if not m.any():
            res.append(o); continue
        res += _keep_runs(g, m, ts, stats, "in_lot_m")
    return res


PJ_MAX, PJ_ANG, STUB_MAX = 20.0, 30.0, 15.0   # m, deg, m
NOSE_W, NOSE_ANG, LANE_MOUTH_GAP = (2.7, 6.0), 35.0, 10.0   # m, deg, m
FH7 = None   # j: STRtree of lane centrelines (fh 7)


def _unkerbed(r, seg, G, tree, near=12.0, side=6.0):
    """a street with no kerb of its own: no kerb within side m of its centreline away from the crossing (near m)"""
    from shapely.ops import unary_union
    rest = r.difference(seg.buffer(near))
    if rest.is_empty or rest.length < 5.0:
        return False
    return not len(tree.query(rest, predicate="dwithin", distance=side))


def _is_fh7(g):
    return any(FH7.geometries[int(k)].hausdorff_distance(g) < 1.0 for k in FH7.query(g, predicate="dwithin", distance=0.5))


def _join_clear(c, n0, n1, clear=2.6, skip=5.0):
    """the joining stretch c[n0:n1] keeps clear of the rest of its own line (no hook, loop or fold where it was made)"""
    g = LineString(c); cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
    a, b = cum[max(n0, 0)], cum[min(n1, len(c) - 1)]
    for t in np.arange(a, b + 0.01, 0.5):
        q = g.interpolate(t)
        for lo, hi in ((0.0, t - skip), (t + skip, g.length)):
            if hi - lo > 0.5 and substring(g, lo, hi).distance(q) < clear:
                return False
    return True


def pair_join(out, streets, stats):
    """j (i review tiles 9, 10, 11: a straight kerb broken 5-20 m at a driveway or a lane, two square ends facing each other; the
    reviewer's near): two free ends that face each other (each pointing at the other within PJ_ANG) up to PJ_MAX m apart are one
    kerb: joined with a smooth curve unless that crosses a street centreline or another kerb. A short piece (under STUB_MAX m) with
    both ends free and one of them near another kerb is a stub (i tiles 1, 28: into a roof, at a junction): it goes"""
    st = STRtree(streets)
    G = [_L(o) for o in out]; tree = STRtree(G)
    ends = _free_ends(out, G, tree, minlen=3.0)
    et = STRtree([e for _, _, e, _ in ends]) if ends else None
    cand = []
    for a, (i, j0, e, h) in enumerate(ends):
        u = np.array([np.cos(h), np.sin(h)])
        for b in et.query(e, predicate="dwithin", distance=PJ_MAX):
            b = int(b)
            if b <= a:
                continue
            k, j1, f, hk = ends[b]
            v = np.array([f.x - e.x, f.y - e.y]); d = np.hypot(*v)
            if k == i and G[i].length < max(50.0, 4 * d):   # a long kerb round a block left open: shut into its ring
                continue
            if d < 1.0:
                continue
            v /= d; w = np.array([np.cos(hk), np.sin(hk)])
            if np.dot(u, v) >= np.cos(np.radians(PJ_ANG)) and np.dot(w, -v) >= np.cos(np.radians(PJ_ANG)):
                cand.append((d, a, b, "on"))
            elif k != i and NOSE_W[0] <= d <= NOSE_W[1] and np.dot(u, w) > np.cos(np.radians(NOSE_ANG)) and abs(np.dot(u, v)) < 0.5:
                # j (i review tile 3, V93: a median nose or a footway strip left open, two kerbs ending side by side): a
                # round cap, unless a street runs between them (that is a lane, capped by caps())
                cand.append((d + PJ_MAX, a, b, "nose"))
    cand.sort(); used = set(); pairs = []
    for d, a, b, how in cand:
        i, j0, e, h = ends[a]; k, j1, f, hk = ends[b]
        if i in used or k in used:
            continue
        p0 = np.array([e.x, e.y]); p1 = np.array([f.x, f.y])
        if how == "nose":
            d -= PJ_MAX; r = 0.7 * d
            bz = _bez(p0, p0 + r * np.array([np.cos(h), np.sin(h)]), p1 + r * np.array([np.cos(hk), np.sin(hk)]), p1, 12)
        else:
            bz = _bez(p0, p0 + d / 3 * np.array([np.cos(h), np.sin(h)]), p1 + d / 3 * np.array([np.cos(hk), np.sin(hk)]), p1, 10)
        seg = LineString(bz)
        crossed = [int(m) for m in st.query(seg, predicate="intersects")]
        if how == "on" and d <= LANE_MOUTH_GAP:
            # j (i review V96: a kerb cut square either side of a lane with no kerbs of its own): the kerb runs on across the
            # lane's mouth (a layback), so a lane centreline (fh 7) does not stop the join there
            crossed = [m for m in crossed if not ((FH7 is not None and _is_fh7(streets[m])) or _unkerbed(streets[m], seg, G, tree))]
        if crossed or any(int(m) not in (i, k) and G[int(m)].intersects(seg) for m in tree.query(seg)):
            continue
        A = np.asarray(out[i]); A = A if j0 == 1 else A[::-1]
        if k == i:
            c = np.vstack([A, bz[1:-1], A[:1]])
            if abs(Polygon(c).area) < 200.0 or not LineString(c[:-1]).is_simple or not _join_clear(c, len(A) - 1, len(A) + len(bz) - 2):
                continue
            used.add(i); pairs.append((i, k, c)); continue
        B = np.asarray(out[k]); B = B if j1 == 0 else B[::-1]
        c = np.vstack([A, bz[1:-1], B])
        if not LineString(c).is_simple or not _join_clear(c, len(A) - 1, len(A) + len(bz) - 2):
            continue
        used.add(i); used.add(k); pairs.append((i, k, c))
    res = [o for n, o in enumerate(out) if n not in used] + [c for _, _, c in pairs]
    stats["pair_join"] = stats.get("pair_join", 0) + len(pairs)
    # stubs
    G = [_L(o) for o in res]; tree = STRtree(G); drop = set()
    for i, g in enumerate(G):
        if g.length >= STUB_MAX or _closed(res[i]):
            continue
        es = [Point(g.coords[0]), Point(g.coords[-1])]
        if not all(_free(G, tree, i, e) for e in es):
            continue
        if any(any(int(k) != i and int(k) not in drop and G[int(k)].distance(e) < NEAR_D for k in tree.query(e, predicate="dwithin", distance=NEAR_D)) for e in es):
            drop.add(i)
    stats["stub_drop"] = stats.get("stub_drop", 0) + len(drop)
    return [o for n, o in enumerate(res) if n not in drop]


GUARD_FOLD_D, GUARD_FOLD_ALONG, GUARD_INSIDE_D, GUARD_INSIDE_SHARE, GUARD_INSIDE_MAX = 2.55, 8.0, 2.7, 0.75, 40.0   # m, m, m, share, m


def guard(out, stats):
    """j (j trial runs: a 9 m join lying inside a corner it doubles, a 2.47 m hairpin): the last pass applies the reviewer's own
    shape rules once more, with a margin: a short line lying mostly within GUARD_INSIDE_D m of other kerbs doubles them and goes; a
    line folding back on itself within GUARD_FOLD_D m (more than GUARD_FOLD_ALONG m apart along it) is cut at the fold and its
    shorter side goes"""
    G = [_L(o) for o in out]; tree = STRtree(G); drop = set(); res = []; nf = 0
    for i, g in enumerate(G):
        if g.length > GUARD_INSIDE_MAX or _closed(out[i]):
            continue
        oth = [G[int(k)] for k in tree.query(g, predicate="dwithin", distance=GUARD_INSIDE_D) if int(k) != i and int(k) not in drop]
        if not oth:
            continue
        ts = _samples(g, 1.0)
        near = np.mean([min(o.distance(g.interpolate(t)) for o in oth) < GUARD_INSIDE_D for t in ts])
        if near >= GUARD_INSIDE_SHARE:
            drop.add(i)
    for i, o in enumerate(out):
        if i in drop:
            continue
        g = G[i]
        if _closed(o) or g.length < GUARD_FOLD_ALONG + 2:
            res.append(o); continue
        ts = _samples(g, 1.0); P = [g.interpolate(t) for t in ts]; pt = STRtree(P); cut = None
        for a, p in enumerate(P):
            for b in pt.query(p, predicate="dwithin", distance=GUARD_FOLD_D):
                b = int(b)
                if b > a and ts[b] - ts[a] > GUARD_FOLD_ALONG:
                    cut = (ts[a] + ts[b]) / 2; break
            if cut is not None:
                break
        if cut is None:
            res.append(o); continue
        nf += 1
        keep = (0.0, cut - GUARD_FOLD_ALONG / 2) if cut > g.length / 2 else (cut + GUARD_FOLD_ALONG / 2, g.length)
        if keep[1] - keep[0] >= KEEP_MIN:
            res.append(np.asarray(substring(g, *keep).coords))
    stats["guard_inside"] = len(drop); stats["guard_fold"] = nf
    return res


OFFC_D, OFFC_MAX = 1.5, 30.0   # m


def off_centre_ends(out, streets, stats):
    """j (i review V98: a lane kerb walked up the lane's centreline and stopped there, 0.8 m off it): a kerb end lying within
    OFFC_D m of a ground street centreline is not a kerb; the end is taken back until it is OFFC_D m clear (up to OFFC_MAX m)"""
    st = STRtree(streets); G = [_L(o) for o in out]; tree = STRtree(G); res = []; n = 0
    for i, o in enumerate(out):
        g = G[i]
        if _closed(o) or g.length < KEEP_MIN:
            res.append(o); continue
        cut = [0.0, 0.0]
        for j0 in (0, 1):
            e = Point(g.coords[0 if j0 == 0 else -1])
            if not _free(G, tree, i, e):
                continue
            t = 0.0
            while t <= OFFC_MAX and t < g.length:
                q = g.interpolate(t if j0 == 0 else g.length - t)
                if not len(st.query(q, predicate="dwithin", distance=OFFC_D)):
                    break
                t += 0.5
            if 0 < t <= OFFC_MAX:
                cut[j0] = t
        if cut[0] or cut[1]:
            if g.length - cut[0] - cut[1] >= KEEP_MIN:
                res.append(np.asarray(substring(g, cut[0], g.length - cut[1]).coords)); n += 1
            continue
        res.append(o)
    stats["off_centre_end"] = n
    return res
