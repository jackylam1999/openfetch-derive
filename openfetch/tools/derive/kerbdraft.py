#!/usr/bin/env python3
"""Drafter's rules for kerb lines after kerbregular.py has made them straight and round (Jacky 5 Nov 2026, notes on the
Town Hall / Waterloo picture): trace the way a person does when the kerb cannot be seen.

  1. join   two ends on the same straight line across a gap (a tree, a car), up to JOIN_MAX m, when the gap does not cross a
            road centreline (a side street) and does not run through a property (lot)
  2. bridge two ends near each other that point at each other but sit on different lines (a corner hidden by trees, a parking
            bay taper): a tangent corner when the two directions cross ahead of both ends, else a straight diagonal; never across
            a centreline or through a lot
  3. corner two kerbs that cross near their ends at a junction are cut at the crossing and joined with a round corner; a kerb end
            that runs over a road centreline is cut back before it
  3b block every block corner kerbaudit.py finds open (from road centrelines and properties) is rebuilt: the kerb ends of its
            two roads are extended to where their lines cross and rounded by road type (local 6, collector 9, main 12 m)
  3c extend a kerb that stops mid-street (photo lost it) is carried on along its street at its own offset while it keeps its
            verge to the frontage: to the next piece of the line (tapered join), before a side street, at a dead end; it stops
            where another kerb runs alongside (never a second line in the road), at a fork, or where the frontage changes
  3d turn   a kerb that stops at a side street on its own side turns the corner into it (round 6/9/12 m): onto the side street's
            traced kerb, else onto one drawn from that street's frontage moved out by this kerb's verge
     dead   a dead end is capped by straights and two equal round corners on the side kerbs' own headings (no jogs)
  4. cap    a kerb end that runs into a property (house lot, not a road lot) stops at the lot edge
  5. drop   short pieces still on their own after 1-4 (broken bits nobody can use, e.g. tram stops and medians in the CBD)
  6. weld   two ends that touch and carry on each other's line become one kerb
  Mouths: a kerb is cut at a side street only where the properties behind it open (not at driveways, footpath lines or roads on
  bridges: 941 wrong 8 m cuts in version 2026-11-06-e), and road centrelines of tracks and paths (functionhierarchy 8-11) are
  not streets for any rule.

Items are dicts {"p": Nx2 array (metres), "i": index of the source feature, "filled": metres not seen in the photo}.
"""
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree
from shapely.ops import unary_union

JOIN_MAX = 40.0       # m, same-line gap
JOIN_LAT = 0.8        # m sideways
JOIN_ANG = np.radians(6)
BRIDGE_MAX = 15.0     # m, corner / parking-bay gap
BRIDGE_ANG = np.radians(70)  # each end must point within this of the other end
CROSS_END = 10.0      # m, a crossing this close to both ends is a junction corner
CORNER_R = 5.0        # m, largest round corner made at a junction
CAP_MAX = 15.0        # m, longest kerb end cut back at a property
DROP_LEN = 20.0       # m, shorter lone pieces are dropped
DEAD_REACH = 25.0     # m, kerb ends this close to where a dead-end road stops are capped across it
CLOSE = 5.0           # m, two ends this close that do not form a clean corner are simply joined
LINK_MIN = 8.0        # m, both pieces must be at least this long to be joined or bridged (short bits are noise more often)


class World:
    """Lots (houses = lots with no road centreline in them) and road centrelines, for the 'never through' checks."""

    def __init__(self, lots, roads):
        self.roads = [r for r in roads if r.length > 0]
        self.rtree = STRtree(self.roads) if self.roads else None
        houses = []
        rt = self.rtree
        for g in lots:
            if not g.is_valid:
                g = g.buffer(0)
            if g.is_empty or g.area < 20:
                continue
            if rt is not None and len(rt.query(g, predicate="intersects")):
                continue  # a road lot or a lot a road runs through: not a house
            s = g.buffer(-0.5)
            if not s.is_empty:
                houses.append(s)
        self.houses = houses
        self.htree = STRtree(houses) if houses else None
        # deeper inside a house lot: a joining line may graze a lot corner (the traced kerb and the lot do not match to the
        # centimetre) but must not cut through it
        deep = [h.buffer(-1.0) for h in houses]
        self.deep = [d for d in deep if not d.is_empty]
        self.dtree = STRtree(self.deep) if self.deep else None
        self.lots = [g for g in lots if not g.is_empty]
        self.ltree = STRtree(self.lots) if self.lots else None

    def crosses_road(self, geom):
        return self.rtree is not None and len(self.rtree.query(geom, predicate="intersects")) > 0

    def in_house(self, geom):
        return self.htree is not None and len(self.htree.query(geom, predicate="intersects")) > 0

    def through_house(self, geom):
        return self.dtree is not None and len(self.dtree.query(geom, predicate="intersects")) > 0

    def lot_point(self, p, reach=15.0):
        """Nearest point on a property to p (None if none within reach)."""
        if self.ltree is None:
            return None
        from shapely.ops import nearest_points
        q = Point(p); i = int(self.ltree.nearest(q))
        if self.lots[i].distance(q) > reach:
            return None
        return np.array(nearest_points(q, self.lots[i])[1].coords[0])

    def lot_dist(self, p):
        if self.ltree is None:
            return 1e9
        q = Point(p); i = self.ltree.nearest(q)
        return self.lots[int(i)].distance(q)

    def house_hits(self, geom):
        return [self.houses[i] for i in self.htree.query(geom, predicate="intersects")] if self.htree is not None else []


def _end(p, w, back=3.0):
    """End point and outward unit heading of polyline p at end w (0 start, 1 end), from the last `back` metres."""
    q = p if w == 1 else p[::-1]
    e = q[-1]; d = 0.0; k = len(q) - 1
    while k > 0 and d < back:
        d += np.hypot(*(q[k] - q[k - 1])); k -= 1
    v = e - q[k]; n = np.hypot(*v)
    return e, (v / n if n > 1e-9 else np.array([1.0, 0.0]))


def _turn(u, v):
    return float(np.arctan2(u[0] * v[1] - u[1] * v[0], u @ v))


def _arc(t1, ctr, r, d, step=1.0):
    a0 = np.arctan2(*(t1 - ctr)[::-1])
    n = max(2, int(np.ceil(abs(d) * r / step)))
    a = a0 + np.linspace(0, d, n + 1)
    return np.c_[ctr[0] + r * np.cos(a), ctr[1] + r * np.sin(a)]


def _corner(e1, u1, e2, u2, rmax=12.0):
    """Connector from end e1 (heading u1 out of its line) to end e2 (heading u2 out of its line): straight to where the two
    directions cross, round corner there. None if they do not cross ahead of both ends."""
    M = np.array([u1, -u2]).T
    if abs(np.linalg.det(M)) < 1e-6:
        return None
    a, b = np.linalg.solve(M, e2 - e1)
    if a < -0.3 or b < -0.3:
        return None
    pi = e1 + a * u1
    # the connector runs from e1 along u1 to pi, then back out along -u2 to e2: the turn is between u1 and -u2
    v = -u2; d = _turn(u1, v)
    if abs(d) < np.radians(3):
        return np.array([e1, e2])
    T = min(max(a, 0), max(b, 0))
    r = min(rmax, T / np.tan(abs(d) / 2)) if T > 0 else 0
    if r < 0.5:
        return np.array([e1, pi, e2])
    T = r * np.tan(abs(d) / 2)
    t1 = pi - u1 * T; t2 = pi + v * T
    n1 = np.array([-u1[1], u1[0]]) * np.sign(d)
    arc = _arc(t1, t1 + n1 * r, r, d)
    pts = [e1] + list(arc) + [e2]
    out = [pts[0]]
    for q in pts[1:]:
        if np.hypot(*(q - out[-1])) > 0.05:
            out.append(q)
    return np.array(out)


def _assemble(items, links):
    """links: {(item, end): (item2, end2, connector from end to end2, made-up metres)} both ways. Returns chained items."""
    seen = set(); out = []
    for li in range(len(items)):
        if li in seen:
            continue
        cur, w = li, 0; guard = 0
        while (cur, w) in links and guard < 10000:
            nl, nw, _, _ = links[(cur, w)]
            if nl == li:
                break
            cur, w = nl, 1 - nw; guard += 1
        parts = []; fill = 0.0; c, cw = cur, w; first = c
        while c not in seen:
            seen.add(c)
            seg = items[c]["p"] if cw == 0 else items[c]["p"][::-1]
            parts.append(seg); fill += items[c]["filled"]
            nxt = links.get((c, 1 - cw))
            if nxt and nxt[0] == first and nxt[1] == w and len(parts) and c in seen:
                parts.append(nxt[2][1:])  # a closed loop round a block: add the last corner
                fill += nxt[3]
                break
            if not nxt or nxt[0] in seen:
                break
            conn = nxt[2]
            if len(conn) > 2:
                parts.append(conn[1:-1])
            fill += nxt[3]; c, cw = nxt[0], nxt[1]
        p = np.vstack(parts)
        keep = np.r_[True, np.hypot(*np.diff(p, axis=0).T) > 0.05]
        out.append({"p": p[keep], "i": items[first]["i"], "filled": fill})
    return out


def _free_ends(items, links):
    return [(li, w) for li in range(len(items)) for w in (0, 1) if (li, w) not in links and len(items[li]["p"]) >= 2]


MOUTH_CUT = 4.0      # m cut out each side of where a kerb crosses a side street's centreline
MOUTH_ANG = np.radians(30)


def _opening(g, t, world):
    """True when the properties behind kerb g open at distance t (a side street's mouth): a line along the kerb, just behind the
    frontage, is mostly not inside a lot. A centreline that crosses the kerb with houses straight behind it (a lane with a
    driveway crossing, a road on a bridge above) leaves the kerb whole."""
    if world.ltree is None:
        return True
    a = np.array(g.interpolate(max(t - MOUTH_CUT, 0)).coords[0]); b = np.array(g.interpolate(min(t + MOUTH_CUT, g.length)).coords[0])
    d = b - a; n = np.hypot(*d)
    if n < 1:
        return True
    nv = np.array([-d[1], d[0]]) / n
    for sgn in (1, -1):
        m = (a + b) / 2
        ray = LineString([m, m + nv * sgn * 25])
        hs = [world.lots[int(k)].distance(Point(m)) for k in world.ltree.query(ray, predicate="intersects")]
        if not hs or min(hs) > 15:
            continue
        off = nv * sgn * (min(hs) + 3.0)
        back = LineString([a + off, b + off])
        cov = sum(world.lots[int(k)].intersection(back).length for k in world.ltree.query(back, predicate="intersects"))
        if cov > 0.6 * back.length:
            return False
    return True


def mouths(items, world, stats):
    """A kerb running straight across the mouth of a side street (it crosses that street's centreline at an angle) is cut there,
    so the bridge rule can turn each side into the side street with a round corner."""
    if world.rtree is None:
        return items
    out = []
    for it in items:
        p = it["p"]; g = LineString(p)
        if g.length < 2 * MOUTH_CUT + 4:
            out.append(it); continue
        cuts = []
        for r in world.rtree.query(g, predicate="intersects"):
            rd = world.roads[int(r)]; x = g.intersection(rd)
            for q in getattr(x, "geoms", [x]):
                if q.geom_type != "Point":
                    continue
                t = g.project(q)
                if t < MOUTH_CUT + 2 or t > g.length - MOUTH_CUT - 2:
                    continue
                a = np.array(g.interpolate(max(t - 1, 0)).coords[0]); b = np.array(g.interpolate(min(t + 1, g.length)).coords[0])
                tr = rd.project(q); c = np.array(rd.interpolate(max(tr - 1, 0)).coords[0]); d = np.array(rd.interpolate(min(tr + 1, rd.length)).coords[0])
                u, v = b - a, d - c
                ang = abs(_turn(u / max(np.hypot(*u), 1e-9), v / max(np.hypot(*v), 1e-9)))
                ang = min(ang, np.pi - ang)
                if ang >= MOUTH_ANG and _opening(g, t, world):
                    cuts.append(t)
                elif ang >= MOUTH_ANG:
                    stats["mouth_closed"] = stats.get("mouth_closed", 0) + 1
        if not cuts:
            out.append(it); continue
        cuts.sort(); start = 0.0
        for t in cuts + [None]:
            end = g.length if t is None else t - MOUTH_CUT
            if end - start > 1.0:
                q = _cut(_cut(p, end, keep_start=True), start, keep_start=False)
                out.append(dict(it, p=q))
            if t is not None:
                start = t + MOUTH_CUT
                stats["mouth_n"] = stats.get("mouth_n", 0) + 1
    return out


FRAG_LEN = 80.0       # m, pieces shorter than this can belong to a broken cluster
FRAG_NEAR = 60.0      # m between piece middles
FRAG_LAT = (0.8, 8.0) # m sideways: stepping off one kerb line (opposite kerbs of a street are usually further apart)
FRAG_MIN = 3          # pieces in a cluster before it goes


def fragments(items, stats):
    """Broken clusters (CBD tram stops, medians): three or more short near-parallel pieces that step sideways from each other
    instead of lining up. Nobody can use them, so the whole cluster goes (Jacky 5 Nov 2026)."""
    G = [LineString(it["p"]) for it in items]
    tree = STRtree(G)
    info = {}
    for i, g in enumerate(G):
        p = items[i]["p"]; u = p[-1] - p[0]; n = np.hypot(*u)
        if g.length >= FRAG_LEN or n < 1 or n < 0.8 * g.length:  # long kerbs and bent pieces (corners) are kept
            continue
        info[i] = (u / n, np.array(g.interpolate(0.5, normalized=True).coords[0]))
    parent = {i: i for i in info}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, (u, c) in info.items():
        for j in tree.query(G[i].buffer(FRAG_NEAR)):
            j = int(j)
            if j <= i or j not in info:
                continue
            v, cj = info[j]
            if abs(u @ v) < np.cos(np.radians(12)) or np.hypot(*(cj - c)) > FRAG_NEAR:
                continue
            d = cj - c; lat = abs(u[0] * d[1] - u[1] * d[0])
            if FRAG_LAT[0] <= lat <= FRAG_LAT[1]:
                parent[find(i)] = find(j)
    groups = {}
    for i in info:
        groups.setdefault(find(i), []).append(i)
    bad = {i for g in groups.values() if len(g) >= FRAG_MIN for i in g}
    stats["fragment_n"] = len(bad); stats["fragment_m"] = sum(G[i].length for i in bad)
    return [it for i, it in enumerate(items) if i not in bad]


TRACE = None  # set to a list to record why nearby ends were not linked
RUNS = None   # set to a list to record every drawn run: (rule, why, Nx2 points)


def _tr(rule, ea, eb, why):
    if TRACE is not None:
        TRACE.append((rule, ea, eb, why))


def join(items, world, stats):
    """Rule 1 then rule 2, nearest pairs first, each end used once."""
    from scipy.spatial import cKDTree
    links = {}
    lens = [LineString(it["p"]).length if len(it["p"]) > 1 else 0 for it in items]
    for rule in ("join", "bridge"):
        ends = _free_ends(items, links)
        if TRACE is not None:
            TRACE.extend([(rule, _end(items[li]["p"], w)[0], None, "piece shorter than %d m" % LINK_MIN) for li, w in ends if lens[li] < LINK_MIN])
        ends = [e for e in ends if lens[e[0]] >= LINK_MIN]
        if len(ends) < 2:
            break
        E = [_end(items[li]["p"], w) for li, w in ends]
        KG = [LineString(it["p"]) if len(it["p"]) > 1 else None for it in items]
        KT = STRtree([g for g in KG if g is not None]); KI = [i for i, g in enumerate(KG) if g is not None]
        # an end whose line has another kerb between it and the properties (a median, island or parking-lane line nearer
        # the road centre) is never turned round a corner: the corner belongs to the kerb nearest the block
        OUTER = []
        for (li, w) in ends:
            g = KG[li]; outer = False
            for t in (3.0, 8.0):
                if t >= g.length:
                    continue
                p0 = np.array(g.interpolate(t if w == 0 else g.length - t).coords[0]); q = world.lot_point(p0)
                if q is not None and np.hypot(*(q - p0)) > 1.0:
                    probe = LineString([p0, q])
                    if any(KI[int(h)] != li for h in KT.query(probe, predicate="intersects")):
                        outer = True
            OUTER.append(outer)
        tree = cKDTree(np.array([e for e, _ in E]))
        rng = JOIN_MAX if rule == "join" else BRIDGE_MAX
        cand = []
        for a, b in tree.query_pairs(rng):
            (la, wa), (lb, wb) = ends[a], ends[b]
            if la == lb and (rule != "bridge" or lens[la] < 40):
                continue  # a line's own two ends: only a long kerb round a block may close on itself (at its last corner)
            (ea, ua), (eb, ub) = E[a], E[b]
            d = eb - ea; g = np.hypot(*d)
            if g < 0.05:
                cand.append((g, a, b, np.array([ea, eb]), 0.0, 0.0)); continue
            if rule == "bridge" and (OUTER[a] or OUTER[b]):
                _tr(rule, ea, eb, 'one end is a line nearer the road centre (another kerb lies between it and the block)'); continue
            if rule == "join":
                if ua @ (d / g) < np.cos(JOIN_ANG) or ub @ (-d / g) < np.cos(JOIN_ANG):
                    continue
                if abs(ua[0] * d[1] - ua[1] * d[0]) > JOIN_LAT:
                    continue
                conn = np.array([ea, eb])
            else:
                tA = tB = 0.0
                dturn = _turn(ua, -ub)
                conn = None
                if abs(dturn) >= np.radians(30):
                    # a corner: the two kerbs' directions cross near both ends (ahead, or a little behind where an end
                    # overshoots into the side street); cut the overshoot and put a round corner there
                    M = np.array([ua, -ub]).T
                    sa = sb = None
                    if abs(np.linalg.det(M)) > 1e-6:
                        sa, sb = np.linalg.solve(M, eb - ea)
                    if sa is not None and -8 <= sa <= BRIDGE_MAX and -8 <= sb <= BRIDGE_MAX:
                        T = 6.0 * np.tan(abs(dturn) / 2)
                        T = min(T, sa + 0.4 * lens[la], sb + 0.4 * lens[lb])
                        if T >= 0.3:
                            r = T / np.tan(abs(dturn) / 2)
                            pi = ea + sa * ua; t1 = pi - ua * T
                            tA, tB = max(0.0, T - sa), max(0.0, T - sb)
                            n1 = np.array([-ua[1], ua[0]]) * np.sign(dturn)
                            arc = _arc(t1, t1 + n1 * r, r, dturn)
                            # a kerb corner turns around a block: lots inside the turn, road outside (a corner drawn
                            # across a side-street mouth has the road inside). Centrelines are not checked for corners:
                            # in lanes they are often a few metres off and would block real corners.
                            mid = arc[len(arc) // 2]; nin = (t1 + n1 * r) - mid; nin = nin / max(np.hypot(*nin), 1e-9)
                            if world.lot_dist(mid + 3 * nin) >= world.lot_dist(mid - 3 * nin):
                                _tr(rule, ea, eb, 'road inside the corner (would close a side street)'); continue
                            # the corner must be the kerb nearest the block: no other kerb between it and the properties
                            # (else it has turned into a median or island line nearer the road centre)
                            q = world.lot_point(mid)
                            if q is not None:
                                probe = LineString([mid, q])
                                if any(KI[int(h)] not in (la, lb) for h in KT.query(probe, predicate="intersects")):
                                    _tr(rule, ea, eb, 'another kerb lies between this corner and the block'); continue
                            conn = np.array(([ea] if tA == 0 else []) + list(arc) + ([eb] if tB == 0 else []))
                    if conn is None:
                        if g <= CLOSE and ua @ (d / g) > -0.2 and ub @ (-d / g) > -0.2:
                            conn = np.array([ea, eb])  # two ends a few metres apart: just close the gap
                        else:
                            _tr(rule, ea, eb, 'directions do not meet near both ends'); continue
                else:
                    # a parking-bay taper or a small jog: straight diagonal between ends that point at each other
                    if ua @ (d / g) < np.cos(BRIDGE_ANG) or ub @ (-d / g) < np.cos(BRIDGE_ANG):
                        _tr(rule, ea, eb, 'ends do not point at each other'); continue
                    conn = np.array([ea, eb])
                if LineString(conn).length > 1.6 * g + 8:
                    _tr(rule, ea, eb, 'connector too long'); continue
                conn = (conn, tA, tB)
            if isinstance(conn, tuple):
                conn, tA, tB = conn
            else:
                tA = tB = 0.0
            ls = LineString(conn) if len(conn) > 1 and g > 0.05 else None
            corner = rule == "bridge" and (tA > 0 or tB > 0 or len(conn) > 2)
            if ls is not None and not corner and world.crosses_road(ls):
                _tr(rule, ea, eb, 'crosses a road centreline'); continue
            if ls is not None and world.through_house(ls):
                _tr(rule, ea, eb, 'runs through a property'); continue
            cand.append((g, a, b, conn, tA, tB))
        cand.sort(key=lambda c: c[0])
        used = set()
        for g, a, b, conn, tA, tB in cand:
            if a in used or b in used:
                continue
            (la, wa), (lb, wb) = ends[a], ends[b]
            closing = la == lb or _same_chain(links, la, lb)
            if closing and rule != "bridge":
                continue
            if tA > 0 or tB > 0:
                for li_, wi_, t_ in ((la, wa, tA), (lb, wb, tB)):
                    if t_ > 0:
                        pp = items[li_]["p"]; Lp = LineString(pp).length
                        items[li_] = dict(items[li_], p=_cut(pp, Lp - t_, True) if wi_ == 1 else _cut(pp, t_, False))
                        lens[li_] = Lp - t_
                ea2 = _end(items[la]["p"], wa)[0]; eb2 = _end(items[lb]["p"], wb)[0]
                conn = np.vstack([ea2[None], conn, eb2[None]])
            used |= {a, b}
            L = LineString(conn).length if len(conn) > 1 else 0.0
            links[(la, wa)] = (lb, wb, conn, L); links[(lb, wb)] = (la, wa, conn[::-1], L)
            stats[rule + "_n"] = stats.get(rule + "_n", 0) + 1
            stats.setdefault("_conn", []).append((rule, conn))
            stats[rule + "_m"] = stats.get(rule + "_m", 0.0) + L
    return _assemble(items, links)


def _fillet_at(P, din, dout, r):
    """Round corner of radius r at P between a line arriving along din and one leaving along dout: (tangent in, arc, T)."""
    d = _turn(din, dout)
    if abs(d) < np.radians(2):
        return P, np.array([P]), 0.0
    T = r * np.tan(abs(d) / 2)
    t1 = P - din * T
    n1 = np.array([-din[1], din[0]]) * np.sign(d)
    return t1, _arc(t1, t1 + n1 * r, r, d), T


def _round_cap(e, v, ea, ha, eb, hb, A, rmax=6.0):
    """Returns (cap line, metres each side kerb must be cut back so its round starts at its end) or None.
    Clean cap across a dead end (Jacky 6 Nov 2026 "some cap looks a bit fussy"): each side kerb runs on along its OWN
    heading (ha, hb, out of its end) to one cap line square to the road (v) at A m past the road's tip e, and the two corners
    are rounded with the same radius (up to rmax; a half circle when the road is no wider than 2 * rmax). No jogs, no kinks:
    straights and tangent arcs only. None if a side kerb does not run towards the cap line."""
    nrm = np.array([-v[1], v[0]]); C = e + v * A
    P = []
    for p, h in ((ea, ha), (eb, hb)):
        den = h @ v
        if den < 0.5:
            return None
        t = ((C - p) @ v) / den
        if t < -0.5:
            return None
        P.append((p + h * max(t, 0.0), max(t, 0.0)))
    (Pa, ta), (Pb, tb) = P
    W = np.hypot(*(Pb - Pa))
    if W < 1.0:
        return None
    da = (Pb - Pa) / W
    # one radius for both rounds: as asked, but both must fit across the road (a half circle at most)
    ta_ang = np.tan(abs(_turn(ha, da)) / 2); tb_ang = np.tan(abs(_turn(da, -hb)) / 2)
    r = rmax
    if ta_ang + tb_ang > 1e-6:
        r = min(r, (W - 0.01) / (ta_ang + tb_ang))
    t1a, arca, Ta = _fillet_at(Pa, ha, da, r)
    t1b, arcb, Tb = _fillet_at(Pb, da, -hb, r)
    pts = [ea] + list(arca) + list(arcb) + [eb]
    keep = [pts[0]]
    for q in pts[1:]:
        if np.hypot(*(q - keep[-1])) > 0.05:
            keep.append(q)
    return np.array(keep), max(Ta - ta, 0.0), max(Tb - tb, 0.0)


def deadends(items, world, stats):
    """A road that stops (a centreline end that touches no other road) is a dead end: the kerb on its left and the kerb on its
    right are closed across the end of the road with a round cap: a half circle on a narrow road, a straight with round corners
on a wide one (Jacky 6 Nov 2026)."""
    if not world.roads:
        return items
    from scipy.spatial import cKDTree
    tips = []
    for r in world.roads:
        c = np.asarray(r.coords)
        for e, nxt in ((c[0], c[1]), (c[-1], c[-2])):
            tips.append((e, e - nxt))
    T = cKDTree(np.array([t[0] for t in tips]))
    dead = []
    for i, (e, v) in enumerate(tips):
        if len(T.query_ball_point(e, 1.0)) > 1:
            continue  # another road starts here: a junction, not a dead end
        if len(world.rtree.query(Point(e).buffer(1.0), predicate="intersects")) > 1:
            continue  # the end touches another road's middle (a T junction)
        n = np.hypot(*v)
        if n < 1e-6:
            continue
        v = v / n
        # a real dead end runs into properties: a lot straight ahead within 20 m, and no other road just beyond the tip
        # (a centreline that simply stops short of a main road is a junction, not a dead end)
        ahead = LineString([e, e + v * 20])
        if world.ltree is None or not len(world.ltree.query(ahead, predicate="intersects")):
            continue
        if len(world.rtree.query(Point(e + v * 10).buffer(12), predicate="intersects")) > 1:
            continue
        dead.append((e, v))
    links = {}
    lens = [LineString(it["p"]).length if len(it["p"]) > 1 else 0 for it in items]
    ends = [(li, w) for li, w in _free_ends(items, links) if lens[li] >= LINK_MIN]
    if not ends or not dead:
        return items
    E = [_end(items[li]["p"], w) for li, w in ends]
    K = cKDTree(np.array([e for e, _ in E]))
    used = set()
    for e, v in dead:
        nrm = np.array([-v[1], v[0]])
        side = {1: [], -1: []}
        for k in K.query_ball_point(e, DEAD_REACH):
            if k in used:
                continue
            p, u = E[k]; q = p - e
            along, across = q @ v, q @ nrm
            if along < -DEAD_REACH or along > 6 or abs(across) < 1.5 or abs(across) > 15 or u @ v < 0.7:
                continue  # must stop near the road's end, sit to one side of it and run towards the end
            side[int(np.sign(across))].append((abs(along) + abs(across), k))
        if not side[1] or not side[-1]:
            continue
        a = min(side[1])[1]; b = min(side[-1])[1]
        (la, wa), (lb, wb) = ends[a], ends[b]
        if la == lb or (la, wa) in links or (lb, wb) in links:
            continue
        ea, eb = E[a][0], E[b][0]
        if np.hypot(*(eb - ea)) > 30:
            continue
        # the cap line: past the further kerb end, moved on towards the property ahead when the road runs on (the kerb
        # stops a verge short of the property, the verge measured on the two side kerbs), at most 15 m further
        A0 = max((ea - e) @ v, (eb - e) @ v, 0.0)
        A = A0
        hit = world.ltree.query(LineString([e, e + v * 40]), predicate="intersects")
        if len(hit):
            d_ahead = min(world.lots[int(k)].distance(Point(e)) for k in hit)
            verge = min(np.mean([world.lot_dist(ea), world.lot_dist(eb)]), 6.0)
            A = min(max(A0, d_ahead - verge), A0 + 15.0)
        ha, hb = _end(items[la]["p"], wa, 8.0)[1], _end(items[lb]["p"], wb, 8.0)[1]  # heading of the side kerb, not its last wiggle
        own = [r for r in world.rtree.query(Point(e).buffer(0.5)) if world.roads[int(r)].distance(Point(e)) < 0.5]
        pa, pb = items[la]["p"], items[lb]["p"]
        conn = None
        for rmax in (6.0, 3.0, 1.5, 0.0):  # smaller rounds where the full one would reach into a property
            got = _round_cap(e, v, ea, ha, eb, hb, A, rmax) if rmax else None
            qa, qb = pa, pb
            if got is not None:
                c0, ca, cb = got
                # cut a side kerb back where its round has to start before its end (a straight kerb: same line)
                for (li, ww), cut, nm in (((la, wa), ca, "a"), ((lb, wb), cb, "b")):
                    q = pa if nm == "a" else pb
                    L = LineString(q).length
                    if cut > 0.05 and L - cut >= LINK_MIN:
                        q = _cut(q, L - cut, keep_start=True) if ww == 1 else _cut(q, cut, keep_start=False)
                        if nm == "a":
                            qa = q
                        else:
                            qb = q
                ea2, ha2 = _end(qa, wa, 8.0); eb2, hb2 = _end(qb, wb, 8.0)
                got = _round_cap(e, v, ea2, ha2, eb2, hb2, A, rmax)
            if got is None:
                qa, qb = pa, pb
                cand = np.array([ea, eb]) if not rmax else None
            else:
                cand = got[0]
            # the cap may cross its own road's centreline (the centreline often stops short of the turning area), no other
            if cand is not None and not world.through_house(LineString(cand)) and not any(
                    int(r) not in own for r in world.rtree.query(LineString(cand), predicate="intersects")):
                conn = cand
                break
        if conn is None:
            continue
        items[la] = dict(items[la], p=qa)
        if lb != la:
            items[lb] = dict(items[lb], p=qb)
        used |= {a, b}
        L = float(LineString(conn).length)
        links[(la, wa)] = (lb, wb, conn, L); links[(lb, wb)] = (la, wa, conn[::-1], L)
        stats["deadend_n"] = stats.get("deadend_n", 0) + 1
        _tr("deadend", ea, eb, "cap")
        stats.setdefault("_conn", []).append(("deadend", conn))
    return _assemble(items, links)


def _same_chain(links, a, b):
    seen = {a}; stack = [a]
    while stack:
        x = stack.pop()
        if x == b:
            return True
        for w in (0, 1):
            n = links.get((x, w))
            if n and n[0] not in seen:
                seen.add(n[0]); stack.append(n[0])
    return False


def _cut(p, at_len, keep_start=True):
    """Polyline p cut at distance at_len from its start; keep the start part (or the end part)."""
    ls = LineString(p); at_len = min(max(at_len, 0), ls.length)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    k = int(np.searchsorted(d, at_len))
    q = np.array(ls.interpolate(at_len).coords[0])
    if keep_start:
        return np.vstack([p[:k], q[None]]) if k > 0 else np.array([p[0], q])
    return np.vstack([q[None], p[k:]]) if k < len(p) else np.array([q, p[-1]])


def corners(items, world, stats):
    """Rule 3: kerbs crossing near their ends at a junction -> cut at the crossing, round corner; ends over a centreline cut back."""
    geoms = [LineString(it["p"]) for it in items]
    tree = STRtree(geoms)
    done = set(); links = {}
    for i, g in enumerate(geoms):
        if i in done:
            continue
        for j in tree.query(g, predicate="crosses"):
            j = int(j)
            if j == i or j in done:
                continue
            x = g.intersection(geoms[j])
            if x.geom_type != "Point":
                continue
            ti, tj = g.project(x), geoms[j].project(x)
            wi = 0 if ti < CROSS_END else (1 if g.length - ti < CROSS_END else None)
            wj = 0 if tj < CROSS_END else (1 if geoms[j].length - tj < CROSS_END else None)
            if wi is None or wj is None:
                continue
            pi_ = items[i]["p"]; pj = items[j]["p"]
            a = _cut(pi_, ti, keep_start=(wi == 1)); b = _cut(pj, tj, keep_start=(wj == 1))
            if LineString(a).length < 2 or LineString(b).length < 2:
                continue
            # pull both back from the crossing by the tangent length of a round corner, then join them round it
            ea, ua = _end(a, wi); eb, ub = _end(b, wj)
            d = _turn(ua, -ub)
            T = min(CORNER_R * np.tan(abs(d) / 2), 0.45 * LineString(a).length, 0.45 * LineString(b).length) if abs(d) > np.radians(3) else 0
            if T > 0.3:
                la, lb = LineString(a).length, LineString(b).length
                a = _cut(a, la - T, keep_start=True) if wi == 1 else _cut(a, T, keep_start=False)
                b = _cut(b, lb - T, keep_start=True) if wj == 1 else _cut(b, T, keep_start=False)
                ea, ua = _end(a, wi); eb, ub = _end(b, wj)
            conn = _corner(ea, ua, eb, ub, rmax=CORNER_R)
            if conn is None:
                conn = np.array([ea, eb])
            items[i] = dict(items[i], p=a); items[j] = dict(items[j], p=b)
            L = LineString(conn).length
            links[(i, wi)] = (j, wj, conn, L); links[(j, wj)] = (i, wi, conn[::-1], L)
            done |= {i, j}
            stats["corner_n"] = stats.get("corner_n", 0) + 1
            break
    items = _assemble(items, links)
    # ends that run over a road centreline: cut back 1 m before it
    for k, it in enumerate(items):
        g = LineString(it["p"])
        if g.length < 4 or world.rtree is None:
            continue
        hits = [world.roads[int(r)] for r in world.rtree.query(g, predicate="intersects")]
        if not hits:
            continue
        ts = []
        for h in hits:
            x = g.intersection(h)
            for q in getattr(x, "geoms", [x]):
                if q.geom_type == "Point":
                    ts.append(g.project(q))
        p = it["p"]
        head = [t for t in ts if t < CROSS_END]; tail = [t for t in ts if g.length - t < CROSS_END]
        if tail and min(tail) - 1 > max(head + [0]) + 2:
            p = _cut(p, min(tail) - 1.0, keep_start=True); stats["over_road_cut"] = stats.get("over_road_cut", 0) + 1
        if head:
            g2 = LineString(p)
            if max(head) + 1 < g2.length - 2:
                p = _cut(p, max(head) + 1.0, keep_start=False); stats["over_road_cut"] = stats.get("over_road_cut", 0) + 1
        items[k] = dict(it, p=p)
    return items


SAME_ONLY = True      # draw only where the same side's kerb was traced further on: from the kerb across the street the
                      # drawn lines were 32-39 % within 1 m of council kerbs (Mona Vale / Newport), from the same side 50-55 %
FILL_RESERVE = 7.0    # m, narrowest road reserve (property to property) a kerb is drawn in
FILL_MAX = 60.0       # m, longest kerb run drawn from the road layout along one street from a corner
FILL_FRONT = 0.7      # share of a drawn run that must sit beside a property frontage (1-12 m from a lot)


def fill(items, world, stats):
    """Rule 3a (Jacky 6 Nov 2026, "fix it from the root"): at an open block corner where a street has no kerb on the corner's
    side within 30 m of the junction (never traced, or the trace stops far short), the missing kerb is drawn from the road
    layout: this side's property frontage moved out by the verge measured on the traced kerb (the same side's kerb further on,
    else the kerb across the street; the centreline offset when no frontage), from the corner out to where the traced kerb starts again (joined onto it) or to the next junction (at most
    FILL_MAX m). It is kept only when it runs beside property frontages (FILL_FRONT of it within 1.5 m of the traced kerb's verge), does not cut 1 m
    into a house lot and crosses no other kerb or road. Rule 3b (blocks) then rounds the corner onto it."""
    roads = getattr(world, "roads_fh", None)
    if not roads or not items:
        return items
    import kerbaudit as ka
    from shapely.ops import substring
    idx = [i for i, it in enumerate(items) if len(it["p"]) > 1]
    K = ka.Kerbs([items[i]["p"] for i in idx])
    cs = [c for c in ka.block_corners(roads, world.lots, K, area=ka.traced_area(K)) if c["open"] or not c["covered"]]
    made, links, done, used = [], {}, set(), set()
    for c in cs:
        J = c["J"]
        arms = ((c["u1"], c["n1"], c["roads"][0]), (c["u2"], c["n2"], c["roads"][1]))
        for a_i, (u, n, ri) in enumerate(arms):
            key = (ri, round(float(n[0]), 1), round(float(n[1]), 1))
            if key in done or K.offset(J, u, n) is not None:
                continue  # a kerb within 30 m on this side: the corner rules handle it
            ou, on, _ = arms[1 - a_i]
            w_cross = K.offset(J, ou, on, ka.SHORT_REACH)  # the cross street's kerb on this corner
            w_same = K.offset(J, u, n, ka.SHORT_REACH)
            n_ref = n if w_same is not None else -n
            w = w_same if w_same is not None else K.offset(J, u, -n, ka.SHORT_REACH)
            if w is None or w < 2.0 or (SAME_ONLY and w_same is None):
                continue  # the street was not traced: out of scope
            # the verge (kerb to property) measured on the traced kerb, then the missing kerb = this side's property
            # frontage moved out by that verge (the centreline is not always in the middle of the road)
            vs = [world.lot_dist(J + u * t + n_ref * w) for t in np.arange(10, ka.SHORT_REACH, 5.0)]
            vs = [v for v in vs if v < 12]
            verge = float(np.median(vs)) if vs else None
            done.add(key)
            g = roads[ri][0]
            if Point(g.coords[0]).distance(Point(J)) > Point(g.coords[-1]).distance(Point(J)):
                g = LineString(list(g.coords)[::-1])
            # a centreline that runs through property lots (a walkway or unbuilt road between houses) is no street with kerbs
            g60 = substring(g, 0, min(g.length, FILL_MAX))
            inlot = sum(world.lots[int(k)].intersection(g60).length for k in world.ltree.query(g60, predicate="intersects"))
            if inlot > 0.3 * g60.length:
                stats["fill_inlot"] = stats.get("fill_inlot", 0) + 1; continue
            # ... or one squeezed between properties: a reserve under FILL_RESERVE m wide is a lane or footpath, not a kerbed street
            wid = []
            for t in np.arange(2.0, g60.length, 5.0):
                cp = np.asarray(g60.interpolate(t).coords[0])
                d = []
                for sgn in (1, -1):
                    ray = LineString([cp, cp + n * sgn * 20])
                    hs = [world.lots[int(k)].distance(Point(cp)) for k in world.ltree.query(ray, predicate="intersects")]
                    d.append(min(hs) if hs else 20.0)
                wid.append(sum(d))
            if wid and np.median(wid) < FILL_RESERVE:
                stats["fill_lane"] = stats.get("fill_lane", 0) + 1; continue
            # the same side's traced kerb further on: its end facing the corner
            hit = None
            if w_same is not None:
                for k in K.tree.query(LineString([J + u * 20, J + u * ka.SHORT_REACH]).buffer(w + 3)):
                    li = idx[int(k)]
                    for ww in (0, 1):
                        if (li, ww) in used:
                            continue
                        e, h = _end(items[li]["p"], ww)
                        t = g.project(Point(e)); cp = np.asarray(g.interpolate(t).coords[0])
                        if t < 15 or abs(np.hypot(*(e - cp)) - w) > 2.5 or (e - cp) @ n < 0:
                            continue
                        gd = np.asarray(g.interpolate(max(t - 3, 0)).coords[0]) - cp
                        if h @ (gd / max(np.hypot(*gd), 1e-6)) < np.cos(np.radians(30)):
                            continue
                        if hit is None or t < hit[0]:
                            hit = (t, li, ww, e)
            # start past the cross street's kerb line, so the corner rule has room to round onto it
            s0 = (w_cross + 1.0) if w_cross is not None else 6.0
            s1 = hit[0] - 0.5 if hit else min(g.length - 6.0, FILL_MAX)
            if s1 - s0 < LINK_MIN or s1 > ka.SHORT_REACH + 5:
                continue
            seg = substring(g, s0, s1)
            side = 1.0 if (np.asarray(seg.interpolate(min(5.0, seg.length)).coords[0]) - J) @ n >= 0 else -1.0
            # offset_curve: positive = left of the line's direction; the corner side is n
            d = np.asarray(seg.coords[1]) - np.asarray(seg.coords[0]); left = np.array([-d[1], d[0]])
            if verge is not None:
                fr = []
                for t in np.arange(1.0, seg.length, 4.0):
                    cp = np.asarray(seg.interpolate(t).coords[0])
                    ray = LineString([cp, cp + n * 30])
                    hits = [world.lots[int(k)] for k in world.ltree.query(ray, predicate="intersects")]
                    if hits:
                        fr.append(min(h.distance(Point(cp)) for h in hits) - verge)
                if len(fr) >= 3:
                    w = float(np.clip(np.median(fr), 2.0, 15.0))
            run = seg.offset_curve(w if left @ n > 0 else -w)
            if run.is_empty or run.geom_type != "LineString" or run.length < LINK_MIN:
                continue
            p = np.asarray(run.coords)
            if np.hypot(*(p[0] - J)) > np.hypot(*(p[-1] - J)):
                p = p[::-1]  # p[0] is the corner end
            q = [run.interpolate(t) for t in np.arange(0.5, run.length, 2.0)]
            lo, hi = ((verge - 1.5, verge + 1.5) if verge is not None else (1.0, 12.0))
            front = np.mean([lo <= world.lot_dist(np.asarray(x.coords[0])) <= hi for x in q]) if q else 0
            why = None
            if front < FILL_FRONT:
                why = "frontage"
            elif world.through_house(run):
                why = "house"
            elif world.crosses_road(run):
                why = "road"
            elif any(idx[int(k)] != (hit[1] if hit else -1) for k in K.tree.query(run, predicate="intersects")):
                why = "kerb"
            if why:
                stats["fill_" + why] = stats.get("fill_" + why, 0) + 1; _tr("fill", J, None, why); continue
            near = idx[int(K.tree.nearest(run))]  # properties (road type, area) of the nearest traced kerb
            m = len(items) + len(made)
            made.append({"p": p.copy(), "i": items[near]["i"], "filled": float(run.length)})
            if RUNS is not None:
                RUNS.append(("fill", "made", p.copy()))
            if hit:
                conn = np.array([p[-1], hit[3]]); L = float(np.hypot(*(p[-1] - hit[3])))
                links[(m, 1)] = (hit[1], hit[2], conn, L); links[(hit[1], hit[2])] = (m, 1, conn[::-1], L)
                used.add((hit[1], hit[2]))
            _tr("fill", p[0], p[-1], "made")
            stats["fill_n"] = stats.get("fill_n", 0) + 1; stats["fill_m"] = stats.get("fill_m", 0.0) + float(run.length)
    return _assemble(items + made, links) if made else items


EXT_MAX = 150.0      # m, longest run drawn on from one kerb end along its street
EXT_PIECE = 20.0     # m, only kerbs at least this long are carried on (shorter bits are noise more often)
EXT_FRONT = 2.0      # m, the run keeps the end's own verge (kerb to property) within this
EXT_BAD = 8.0        # m of verge change in a row (a bus bay, a widening, a park) and the run stops before it
EXT_MIN = 3.0        # m, shorter runs are not worth a line
EXT_TWIN = 4.5       # m, a run stops where another kerb runs alongside this close (it would double that kerb)


def extend(items, world, stats):
    """Rule 3c (Jacky 6 Nov 2026, "why still so many open ends?"): a kerb that stops in the middle of a street, where the photo
    lost it (trees, shadow, parked cars), is carried on the way a person draws it: along its street at the same distance from the
    centreline, while it keeps the same verge to the property frontage. It ends on the next kerb end of the same line (joined),
    before a side street on its own side (the corner rule rounds it), at a dead end, or where the frontage changes (a bus bay, a
    park). Kept only when it cuts no house lot and crosses no other kerb."""
    roads = [g for g, fh in getattr(world, "roads_fh", []) if fh not in (8, 9, 10, 11)]
    if not roads or not items:
        return items
    from scipy.spatial import cKDTree
    rt = STRtree(roads)
    nodes = {}
    for ri, g in enumerate(roads):
        c = np.asarray(g.coords)
        for w, p in ((0, c[0]), (1, c[-1])):
            nodes.setdefault(tuple(np.round(p / 0.5).astype(int)), []).append((ri, w))

    def tangent(g, t):
        a = np.asarray(g.interpolate(max(t - 1.5, 0)).coords[0]); b = np.asarray(g.interpolate(min(t + 1.5, g.length)).coords[0])
        d = b - a; n = np.hypot(*d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0])

    def leaving(ri, w):
        """Unit heading of road ri leaving its end w."""
        g = roads[ri]
        return tangent(g, 0.0) if w == 0 else -tangent(g, g.length)

    lens = [LineString(it["p"]).length if len(it["p"]) > 1 else 0 for it in items]
    KG = [LineString(it["p"]) if len(it["p"]) > 1 else Point(0, 0) for it in items]
    KT = STRtree(KG)
    ends = [(li, w) for li in range(len(items)) for w in (0, 1)
            if lens[li] >= EXT_PIECE and np.hypot(*(items[li]["p"][0] - items[li]["p"][-1])) > 1.0]
    allends = [(li, w) for li in range(len(items)) for w in (0, 1) if lens[li] > 0]
    ET = cKDTree(np.array([items[li]["p"][0 if w == 0 else -1] for li, w in allends]))
    links, made, used = {}, [], set()
    for li, w in ends:
        if (li, w) in used:
            continue
        e, h = _end(items[li]["p"], w, 8.0)
        # the street this kerb runs along: a centreline 2-20 m to one side, parallel to it
        best = None
        for k in rt.query(Point(e).buffer(20)):
            g = roads[int(k)]; t = g.project(Point(e)); c = np.asarray(g.interpolate(t).coords[0]); tg = tangent(g, t)
            if abs(tg @ h) < np.cos(np.radians(20)) or t <= 0.5 or t >= g.length - 0.5:
                continue
            off = float(tg[0] * (e - c)[1] - tg[1] * (e - c)[0])  # + left of the road's direction
            if 2.0 <= abs(off) <= 20.0 and (best is None or abs(off) < abs(best[2])):
                best = (int(k), t, off, 1.0 if tg @ h > 0 else -1.0)
        if best is None:
            continue
        v0 = world.lot_dist(e)
        if v0 > 10.0:
            continue  # no property frontage beside it: nothing to keep the line honest
        # only the kerb nearest the block is carried on (not a median or island line)
        q = world.lot_point(e)
        if q is not None and np.hypot(*(q - e)) > 1.0:
            if any(int(k) != li for k in KT.query(LineString([e, q]), predicate="intersects")):
                continue
        ri, t, off, sd = best
        # the kerb's offset from the centreline measured along its last 20 m (one traced point at the very end can hook)
        g = roads[ri]; pg = KG[li]; offs = []
        for s_ in np.arange(1.0, min(20.0, pg.length), 2.0):
            q_ = np.asarray(pg.interpolate(s_ if w == 0 else pg.length - s_).coords[0]); tq = g.project(Point(q_))
            cq = np.asarray(g.interpolate(tq).coords[0]); tgq = tangent(g, tq)
            offs.append(float(tgq[0] * (q_ - cq)[1] - tgq[1] * (q_ - cq)[0]))
        if offs:
            om = float(np.median(offs))
            if abs(om - off) > 1.5 or np.sign(om) != np.sign(off):
                stats["extend_hook"] = stats.get("extend_hook", 0) + 1
                continue  # the end bends away from its own line: not a kerb to carry on
            off = om
        path, good, bad, dist, why, target = [], 0, 0.0, 0.0, "max", None
        while dist < EXT_MAX:
            t2 = t + sd * 1.0
            if t2 < 0 or t2 > g.length:
                # at the end of this centreline: a side street on this kerb's side stops it, else carry on along the street
                node = np.asarray(g.coords[0 if t2 < 0 else -1])
                here = [(r2, w2) for r2, w2 in nodes.get(tuple(np.round(node / 0.5).astype(int)), []) if r2 != ri]
                here += [(int(k), None) for k in rt.query(Point(node).buffer(0.8)) if int(k) != ri and roads[int(k)].distance(Point(node)) < 0.8
                         and all(int(k) != r2 for r2, _ in here)]
                dvec = sd * tangent(g, min(max(t, 0), g.length)); side = np.array([-dvec[1], dvec[0]]) * np.sign(off * sd)
                nxt, stop, ahead = None, False, 0
                for r2, w2 in here:
                    g2 = roads[r2]
                    if w2 is None:  # our road ends on another's middle: a T, the kerb turns
                        stop = True; break
                    u = leaving(r2, w2)
                    if u @ side > 0.3:
                        stop = True
                    elif u @ dvec > np.cos(np.radians(15)):
                        ahead += 1
                        if nxt is None or u @ dvec > nxt[2]:
                            nxt = (r2, w2, u @ dvec)
                if ahead > 1:
                    nxt = None  # a fork: two roads ahead, the kerb does not know which to follow
                if stop or nxt is None:
                    why = "junction" if stop else "deadend"
                    # leave room for the corner: back off by this kerb's offset from the node
                    back = abs(off) + 0.5
                    keep = max(len(path) - int(np.ceil(back)), 0)
                    path = path[:keep]; good = min(good, keep)
                    break
                ri, g = nxt[0], roads[nxt[0]]
                sd2 = 1.0 if nxt[1] == 0 else -1.0
                off = off * sd * sd2  # the same side of travel on the next centreline
                sd = sd2
                t2 = 0.0 if nxt[1] == 0 else g.length
            t = t2
            tg = tangent(g, t); c = np.asarray(g.interpolate(t).coords[0])
            P = c + np.array([-tg[1], tg[0]]) * off
            dist += 1.0
            prev = path[-1] if path else e
            if any(int(k) != ri and roads[int(k)].distance(Point(c)) > 0.5 for k in rt.query(LineString([prev, P]), predicate="intersects")):
                # a side street on this kerb's side that the centrelines do not split at: stop short of its mouth
                why = "junction"
                keep = max(len(path) - int(np.ceil(abs(off) + 0.5)), 0)
                path = path[:keep]; good = min(good, keep)
                break
            # another kerb here: join onto it if it is a free end of the same line, else stop short of it
            # another kerb running alongside within EXT_TWIN m: this run would double it (a second line in the road). Join it
            # when it is the next piece of the same line (its free end faces us), else stop here (checker round 1, 6 Nov 2026)
            near = []
            for k in KT.query(Point(P).buffer(EXT_TWIN)):
                k = int(k)
                if k == li or KG[k].distance(Point(P)) > EXT_TWIN:
                    continue
                gk = KG[k]; tk = gk.project(Point(P))
                a_ = np.asarray(gk.interpolate(max(tk - 1.5, 0)).coords[0]); b_ = np.asarray(gk.interpolate(min(tk + 1.5, gk.length)).coords[0])
                dk = b_ - a_; nk = np.hypot(*dk)
                if nk < 0.5 or abs(dk @ tg) / nk > np.cos(np.radians(25)) or gk.distance(Point(P)) <= 1.2:
                    near.append(k)
            if near:
                # the next piece of this kerb, also where it steps sideways (a bus bay, a kerb build-out): joined with a taper
                cands = []
                for k in ET.query_ball_point(P, 15.0):
                    l2, w2 = allends[k]
                    if l2 in near and (l2, w2) not in used and l2 != li:
                        e2, h2 = _end(items[l2]["p"], w2, 3.0)
                        lat = abs((e2 - P) @ np.array([-tg[1], tg[0]])); along = (e2 - P) @ (sd * tg)
                        if h2 @ (sd * tg) < -0.8 and lat < EXT_TWIN and along > -1.0:
                            cands.append((np.hypot(*(e2 - P)), l2, w2, e2))
                if cands:
                    _, l2, w2, e2 = min(cands, key=lambda c: c[0])
                    target = (l2, w2, e2)
                why = "kerb" if target else "twin"
                break
            if world.in_house(Point(P)):
                why = "house"; break
            d = world.lot_dist(P)
            if abs(d - v0) > EXT_FRONT:
                bad += 1.0
                if bad > EXT_BAD:
                    why = "frontage"; path.append(P); break
            else:
                bad = 0.0; good = len(path) + 1
            path.append(P)
        if why == "frontage" or (why == "max" and bad > 0):
            path = path[:good]
        if target is None and why in ("kerb", "twin"):
            path = path[:max(len(path) - 2, 0)]
        if target is not None:
            path = path[:max(len(path) - 6, 0)]  # a gentle taper onto the next piece, not a step
        if not path:
            continue
        if target is None and why not in ("junction",):
            # a run that closes nothing (it stops where the frontage changes, at a house, beside another kerb or after
            # EXT_MAX) only moves the open end and was the least accurate drawn line (checker rounds 1-2): not drawn
            stats["extend_open_" + why] = stats.get("extend_open_" + why, 0) + 1
            continue
        run = np.vstack([e[None], np.array(path)] + ([target[2][None]] if target else []))
        L = LineString(run)
        if L.length < EXT_MIN:
            continue
        others = [int(k) for k in KT.query(L, predicate="intersects") if int(k) not in (li, target[0] if target else -1)]
        if others or world.through_house(L) or world.crosses_road(LineString(run[1:-1]) if len(run) > 3 else L.interpolate(0.5, normalized=True)):
            stats["extend_reject"] = stats.get("extend_reject", 0) + 1
            continue
        if RUNS is not None:
            RUNS.append(("extend", "join" if target else why, run.copy()))
        if target:
            links[(li, w)] = (target[0], target[1], run, L.length); links[(target[0], target[1])] = (li, w, run[::-1], L.length)
            used |= {(li, w), (target[0], target[1])}
            stats["extend_join"] = stats.get("extend_join", 0) + 1
        else:
            m = len(items) + len(made)
            made.append({"p": run.copy(), "i": items[li]["i"], "filled": float(L.length)})
            links[(li, w)] = (m, 0, np.array([e, e]), 0.0); links[(m, 0)] = (li, w, np.array([e, e]), 0.0)
            used.add((li, w))
            stats["extend_" + why] = stats.get("extend_" + why, 0) + 1
        stats["extend_n"] = stats.get("extend_n", 0) + 1
        stats["extend_m"] = stats.get("extend_m", 0.0) + L.length
    return _assemble(items + made, links)


TURN_RUN = 20.0      # m drawn along the side street past a turned corner (extend then carries it on)


def turn(items, world, stats):
    """Rule 3d (Jacky 6 Nov 2026: council kerbs are clean, closed curves): a kerb that stops at the mouth of a side street on its
    own side turns the corner into that side street, as the council lines do. The side street's kerb on this corner is its traced
    kerb when there is one (its end facing the corner is joined), else drawn from the side street's own property frontage moved
    out by this kerb's verge. The corner is round by road type (6 / 9 / 12 m); kept only with properties inside the turn, no house
    lot cut, no other kerb or centreline crossed."""
    import kerbaudit as ka
    roads = [(g, fh) for g, fh in getattr(world, "roads_fh", []) if fh not in ka.SKIP_FH]
    if not roads or not items:
        return items
    geoms = [g for g, _ in roads]
    rt = STRtree(geoms)
    nodes = {}
    for ri, g in enumerate(geoms):
        c = np.asarray(g.coords)
        for w, p in ((0, c[0]), (1, c[-1])):
            nodes.setdefault(tuple(np.round(p / 0.5).astype(int)), []).append((ri, w))

    def tangent(g, t):
        a = np.asarray(g.interpolate(max(t - 1.5, 0)).coords[0]); b = np.asarray(g.interpolate(min(t + 1.5, g.length)).coords[0])
        d = b - a; n = np.hypot(*d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0])

    def leaving(ri, w):
        g = geoms[ri]
        a = np.asarray(g.coords[0 if w == 0 else -1]); b = np.asarray(g.interpolate(min(15.0, g.length) if w == 0 else max(g.length - 15.0, 0)).coords[0])
        d = b - a; n = np.hypot(*d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0])

    lens = [LineString(it["p"]).length if len(it["p"]) > 1 else 0 for it in items]
    KG = [LineString(it["p"]) if len(it["p"]) > 1 else Point(0, 0) for it in items]
    KT = STRtree(KG)
    ends = [(li, w) for li in range(len(items)) for w in (0, 1)
            if lens[li] >= LINK_MIN and np.hypot(*(items[li]["p"][0] - items[li]["p"][-1])) > 1.0]
    from scipy.spatial import cKDTree
    ET = cKDTree(np.array([_end(items[li]["p"], w)[0] for li, w in ends])) if ends else None
    links, made, used = {}, [], set()
    pend = None  # a kerb cut back for a corner that was then not made: given its end back
    for li in ends + [None]:
        if pend is not None:
            items[pend[0]], lens[pend[0]] = pend[1], pend[2]; pend = None
        if li is None:
            break
        li, w = li
        if (li, w) in used:
            continue
        e, h = _end(items[li]["p"], w, 8.0)
        best = None
        for k in rt.query(Point(e).buffer(20)):
            g = geoms[int(k)]; t = g.project(Point(e)); c = np.asarray(g.interpolate(t).coords[0]); tg = tangent(g, t)
            if abs(tg @ h) < np.cos(np.radians(25)):
                continue
            off = float(tg[0] * (e - c)[1] - tg[1] * (e - c)[0])
            if 2.0 <= abs(off) <= 20.0 and (best is None or abs(off) < abs(best[2])):
                best = (int(k), t, off, 1.0 if tg @ h > 0 else -1.0)
        if best is None:
            continue
        ri, t, off, sd = best
        g = geoms[ri]
        rem = (g.length - t) if sd > 0 else t
        if rem > abs(off) + 12.0:
            continue  # not at a junction
        if rem < abs(off) + 1.0:
            # the kerb runs on into the junction (past the side street's kerb line): cut it back to where the corner starts
            cut = abs(off) + 1.0 - rem
            if lens[li] - cut < LINK_MIN:
                continue
            p_ = items[li]["p"]; pend = (li, items[li], lens[li])
            p_ = _cut(p_, lens[li] - cut, keep_start=True) if w == 1 else _cut(p_, cut, keep_start=False)
            items[li] = dict(items[li], p=p_); lens[li] -= cut
            e, h = _end(p_, w, 8.0)
            t = g.project(Point(e)); rem = (g.length - t) if sd > 0 else t
            stats["turn_cutback"] = stats.get("turn_cutback", 0) + 1
        J = np.asarray(g.coords[-1 if sd > 0 else 0])
        dvec = sd * tangent(g, min(max(t, 0), g.length))
        side = (e - (J - dvec * rem)); side = side - (side @ dvec) * dvec; side = side / max(np.hypot(*side), 1e-9)
        here = [(r2, w2) for r2, w2 in nodes.get(tuple(np.round(J / 0.5).astype(int)), []) if r2 != ri]
        if any(geoms[int(k)].distance(Point(J)) < 0.8 and all(int(k) != r2 for r2, _ in here) and int(k) != ri
               for k in rt.query(Point(J).buffer(0.8))):
            continue  # our road ends on another's middle: a T, handled by the corner rules
        sides = [(leaving(r2, w2) @ side, r2, w2) for r2, w2 in here if leaving(r2, w2) @ side > 0.5]
        if not sides:
            continue
        _, r2, w2 = max(sides)
        u2 = leaving(r2, w2); g2 = geoms[r2]
        n2 = np.array([-u2[1], u2[0]])
        if n2 @ (-dvec) < 0:
            n2 = -n2  # normal of the side street pointing to this corner
        if g2.length < 15:
            continue
        rank = min(ka.road_rank(roads[ri][1]), ka.road_rank(roads[r2][1]))
        # the side street's kerb on this corner: traced (a free end facing the corner) or from its frontage
        target = None
        w_tr = None
        for k in ET.query_ball_point(J, 45.0):
            l2, ww2 = ends[k]
            if l2 == li or (l2, ww2) in used:
                continue
            e2, h2 = _end(items[l2]["p"], ww2, 6.0)
            along, lat = (e2 - J) @ u2, (e2 - J) @ n2
            if along < 2 or along > 45 or lat < 2 or lat > 20 or h2 @ (-u2) < np.cos(np.radians(25)):
                continue
            if target is None or along < target[0]:
                target = (along, l2, ww2, e2, h2)
        v0 = world.lot_dist(e)
        if target is None:
            if v0 > 10:
                continue
            fr = []
            for s_ in np.arange(8.0, min(40.0, g2.length), 4.0):
                cp = J + u2 * s_
                ray = LineString([cp, cp + n2 * 30])
                hs = [world.lots[int(k)].distance(Point(cp)) for k in world.ltree.query(ray, predicate="intersects")]
                if hs:
                    fr.append(min(hs) - v0)
            if len(fr) < 3:
                continue
            w_side = float(np.median(fr))
            if w_side < 2.0 or w_side > 15.0:
                continue
            # a lane or walkway between houses is no street with kerbs
            wid = []
            for s_ in np.arange(8.0, min(40.0, g2.length), 6.0):
                cp = J + u2 * s_; d_ = []
                for sg in (1, -1):
                    ray = LineString([cp, cp + n2 * sg * 20])
                    hs = [world.lots[int(k)].distance(Point(cp)) for k in world.ltree.query(ray, predicate="intersects")]
                    d_.append(min(hs) if hs else 20.0)
                wid.append(sum(d_))
            if wid and np.median(wid) < FILL_RESERVE:
                continue
            e2 = J + n2 * w_side + u2 * TURN_RUN; h2 = -u2
        else:
            e2, h2 = target[3], target[4]
        R = BLOCK_R[rank]
        conn = None
        for r in (R, R / 2, 3.0):
            c_ = _corner(e, h, e2, h2, rmax=r)
            if c_ is None or len(c_) < 3:
                continue
            gc = LineString(c_)
            mid = c_[len(c_) // 2]
            ctr = np.mean(c_, axis=0)
            # properties inside the turn (towards the block), the road outside
            nin = (e + e2) / 2 - mid; nn = np.hypot(*nin)
            if nn > 0.5 and world.lot_dist(mid + 3 * nin / nn) >= world.lot_dist(mid - 3 * nin / nn):
                continue
            inner = LineString(c_[1:-1]) if len(c_) > 3 else gc.interpolate(0.5, normalized=True)
            if world.through_house(gc) or world.crosses_road(inner):
                continue
            if any(int(k) not in (li, target[1] if target else -1) for k in KT.query(inner, predicate="intersects")):
                continue
            if target is None:
                # a drawn side-street kerb must not double a kerb already there, nor sit inside a house lot
                q_ = [gc.interpolate(f, normalized=True) for f in np.linspace(0.3, 1.0, 12)]
                dbl = np.mean([any(int(k) != li and KG[int(k)].distance(x) <= EXT_TWIN for k in KT.query(x.buffer(EXT_TWIN))) for x in q_])
                if dbl > 0.25 or any(world.in_house(x) for x in q_):
                    continue
            conn = c_; break
        if conn is None:
            stats["turn_reject"] = stats.get("turn_reject", 0) + 1
            continue
        pend = None  # corner made: the cut stays
        L = float(LineString(conn).length)
        if RUNS is not None:
            RUNS.append(("turn", "join" if target else "drawn", conn.copy()))
        if target:
            links[(li, w)] = (target[1], target[2], conn, L); links[(target[1], target[2])] = (li, w, conn[::-1], L)
            used |= {(li, w), (target[1], target[2])}
            stats["turn_join"] = stats.get("turn_join", 0) + 1
        else:
            m = len(items) + len(made)
            made.append({"p": conn.copy(), "i": items[li]["i"], "filled": L})
            links[(li, w)] = (m, 0, np.array([e, e]), 0.0); links[(m, 0)] = (li, w, np.array([e, e]), 0.0)
            used.add((li, w))
            stats["turn_drawn"] = stats.get("turn_drawn", 0) + 1
        stats["turn_n"] = stats.get("turn_n", 0) + 1
        stats["turn_m"] = stats.get("turn_m", 0.0) + L
    return _assemble(items + made, links)


WELD = 1.5            # m, two kerb ends this close that carry on each other's line are one kerb


STUB_LEN = 30.0       # m, a piece shorter than this that runs mostly beside another kerb is a leftover double


def stubs(items, stats):
    """Short pieces that mostly double another kerb (1-4.5 m alongside) are leftovers of a stopped run or a lane line: dropped."""
    G = [LineString(it["p"]) if len(it["p"]) > 1 else None for it in items]
    T = STRtree([g for g in G if g is not None]); I = [i for i, g in enumerate(G) if g is not None]
    keep = []
    for i, it in enumerate(items):
        g = G[i]
        if g is None or g.length >= STUB_LEN:
            keep.append(it); continue
        q = [g.interpolate(f, normalized=True) for f in np.linspace(0.05, 0.95, 8)]
        dbl = np.mean([any(I[int(k)] != i and 1.0 <= G[I[int(k)]].distance(x) <= EXT_TWIN for k in T.query(x.buffer(EXT_TWIN)))
                       for x in q])
        if dbl > 0.5:
            stats["stub_n"] = stats.get("stub_n", 0) + 1; continue
        keep.append(it)
    return keep


def weld(items, stats):
    """Last rule: two kerb ends that touch and run on the same line are one kerb (no break in the drawing)."""
    from scipy.spatial import cKDTree
    ends = [(li, w) for li in range(len(items)) for w in (0, 1) if len(items[li]["p"]) > 1
            and np.hypot(*(items[li]["p"][0] - items[li]["p"][-1])) > 1.0]
    if len(ends) < 2:
        return items
    E = [_end(items[li]["p"], w, 3.0) for li, w in ends]
    T = cKDTree(np.array([e for e, _ in E]))
    cand = []
    for a, b in T.query_pairs(WELD):
        (la, wa), (lb, wb) = ends[a], ends[b]
        if la == lb:
            continue
        if E[a][1] @ E[b][1] < -np.cos(np.radians(30)):
            cand.append((np.hypot(*(E[a][0] - E[b][0])), a, b))
    cand.sort(); links = {}; used = set()
    for g, a, b in cand:
        if a in used or b in used:
            continue
        (la, wa), (lb, wb) = ends[a], ends[b]
        if _same_chain(links, la, lb):
            continue
        conn = np.array([E[a][0], E[b][0]])
        links[(la, wa)] = (lb, wb, conn, g); links[(lb, wb)] = (la, wa, conn[::-1], g)
        used |= {a, b}
        stats["weld_n"] = stats.get("weld_n", 0) + 1
    return _assemble(items, links)


BLOCK_R = {1: 12.0, 2: 9.0, 3: 6.0}  # m, round corner radius by road rank (main, collector, local)
BLOCK_LAT = 2.5       # m, a kerb end this close sideways to the road's measured kerb line belongs to that line
BLOCK_EXT = 40.0      # m, longest straight run a kerb end is extended to reach its corner


def blocks(items, world, stats):
    """Rule 3b, the root fix for open corners (Jacky 6 Nov 2026): corners come from the street layout, not from the photo.
    kerbaudit.py finds every block corner from the road centrelines and properties and where the kerb lines of its two roads
    cross. Where that corner is open, the kerb end of each road on the corner's side is extended to the crossing and the two are
    joined with a round corner sized by road type (local 6 m, collector 9 m, main 12 m; smaller if the ends are close). Kept only
    when it stays on the corner's side of both roads, crosses no centreline or other kerb and does not cut 1 m into a house lot."""
    roads = getattr(world, "roads_fh", None)
    if not roads or not items:
        return items
    import kerbaudit as ka
    K = ka.Kerbs([it["p"] for it in items])
    idx = [i for i, it in enumerate(items) if len(it["p"]) > 1]  # K.g[k] is items[idx[k]]
    cs = [c for c in ka.block_corners(roads, world.lots, K, area=ka.traced_area(K)) if c["open"]]
    links = {}
    stats["block_open"] = len(cs)

    def end_for(c, u, n, w):
        best = None
        J = c["J"]
        for k in K.tree.query(LineString([J - u * 5, J + u * ka.SHORT_REACH]).buffer(w + BLOCK_LAT + 2)):
            li = idx[int(k)]
            for ww in (0, 1):
                if (li, ww) in links:
                    continue
                e, h = _end(items[li]["p"], ww)
                along, lat = (e - J) @ u, (e - J) @ n
                if along < -2 or along > ka.SHORT_REACH or abs(lat - w) > BLOCK_LAT or h @ -u < np.cos(np.radians(25)):
                    continue
                if best is None or along < best[0]:
                    best = (along, li, ww, e, h)
        return best

    for c in cs:
        a = end_for(c, c["u1"], c["n1"], c["w1"]); b = end_for(c, c["u2"], c["n2"], c["w2"])
        if a is None or b is None or (a[1], a[2]) == (b[1], b[2]):
            stats["block_noend"] = stats.get("block_noend", 0) + 1
            _tr("block", c["P"], None, "no kerb end on one road"); continue
        # a kerb that runs on almost to the crossing is cut back so the corner can be round: the full radius when the
        # piece is long enough, else what fits
        R = BLOCK_R[c["rank"]]
        M = np.array([a[4], -b[4]]).T
        if abs(np.linalg.det(M)) < 1e-6:
            stats["block_nocross"] = stats.get("block_nocross", 0) + 1; continue
        ta, tb = np.linalg.solve(M, b[3] - a[3])
        if max(ta, tb) > BLOCK_EXT:
            stats["block_far"] = stats.get("block_far", 0) + 1; _tr("block", c["P"], None, "far"); continue
        J = c["J"]
        why = None
        for r in (R, R / 2, 3.0, 1.0):  # a smaller round where the full one would cut into a house lot
            need = r * np.tan(abs(_turn(a[4], -b[4])) / 2)
            ends = []
            for (along, li, ww, e, h), t in ((a, ta), (b, tb)):
                p = ends[0][4] if ends and ends[0][0] == li else items[li]["p"]  # a block's own loop: both ends on one piece
                L = LineString(p).length
                back = min(max(need - t, 0.0), max(L - LINK_MIN, 0.0))
                if back > 0.3:
                    p = _cut(p, L - back, keep_start=True) if ww == 1 else _cut(p, back, keep_start=False)
                    e, h = _end(p, ww)
                ends.append((li, ww, e, h, p))
            conn = _corner(ends[0][2], ends[0][3], ends[1][2], ends[1][3], rmax=r)
            if conn is None or len(conn) < 2:
                why = "nocross"; continue
            g = LineString(conn)
            side = np.minimum((conn - J) @ c["n1"], (conn - J) @ c["n2"])
            if side.min() < -1.0:
                why = "side"; continue
            if world.crosses_road(g):
                why = "road"; break
            inner = LineString(conn[1:-1]) if len(conn) > 3 else None
            if inner is not None and any(idx[int(k)] not in (a[1], b[1]) for k in K.tree.query(inner, predicate="intersects")):
                why = "kerb"; break
            if world.through_house(g):
                why = "house"; continue
            why = None; break
        if why:
            stats["block_" + why] = stats.get("block_" + why, 0) + 1; _tr("block", c["P"], None, why); continue
        L = float(g.length)
        for li, ww, e, h, p in ends:
            items[li] = dict(items[li], p=p)  # the second end of one piece carries both cuts
        links[(a[1], a[2])] = (b[1], b[2], conn, L); links[(b[1], b[2])] = (a[1], a[2], conn[::-1], L)
        stats["block_n"] = stats.get("block_n", 0) + 1
        stats["block_m"] = stats.get("block_m", 0.0) + L
    return _assemble(items, links)


def caps(items, world, stats):
    """Rule 4: a kerb end inside a house lot is cut back to where it enters the lot."""
    for k, it in enumerate(items):
        p = it["p"]; g = LineString(p)
        if g.length < 2:
            continue
        for w in (0, 1):
            g = LineString(p)
            q = p if w == 0 else p[::-1]
            e = Point(q[0])
            hs = [h for h in world.house_hits(e) if h.contains(e)]
            if not hs:
                continue
            gq = LineString(q)
            inside = gq.intersection(unary_union(hs))
            first = None
            for part in getattr(inside, "geoms", [inside]):
                if part.geom_type == "LineString" and gq.project(Point(part.coords[0])) < 0.01:
                    first = part.length
            if first is None or first > CAP_MAX or first > 0.6 * gq.length:
                continue
            q = _cut(q, first, keep_start=False)
            p = q if w == 0 else q[::-1]
            stats["cap_n"] = stats.get("cap_n", 0) + 1; stats["cap_m"] = stats.get("cap_m", 0.0) + first
        items[k] = dict(it, p=p)
    return items


def drop(items, stats):
    keep = []
    for it in items:
        L = LineString(it["p"]).length if len(it["p"]) > 1 else 0
        if L < DROP_LEN:
            stats["drop_n"] = stats.get("drop_n", 0) + 1; stats["drop_m"] = stats.get("drop_m", 0.0) + L
            continue
        keep.append(it)
    return keep


def draft(items, world, stats, rules=("mouths", "join", "corners", "fill", "extend", "turn", "blocks", "caps", "fragments", "drop", "weld")):
    if "mouths" in rules:
        items = mouths(items, world, stats)
    if "join" in rules:
        items = join(items, world, stats)
        items = deadends(items, world, stats)
    if "corners" in rules:
        items = corners(items, world, stats)
    if "fill" in rules:
        items = fill(items, world, stats)
    if "extend" in rules:
        items = extend(items, world, stats)
    if "turn" in rules:
        items = turn(items, world, stats)
        items = extend(items, world, stats)  # carry the turned kerbs on along their side streets
    if "blocks" in rules:
        items = blocks(items, world, stats)
    if "caps" in rules:
        items = caps(items, world, stats)
    if "fragments" in rules:
        items = fragments(items, stats)
    if "drop" in rules:
        items = drop(items, stats)
    if "weld" in rules:
        items = stubs(items, stats)
        items = weld(items, stats)
    stats.pop("_conn", None) if not stats.get("_keep") else None
    for k in list(stats):
        if k.endswith("_m"):
            stats[k] = round(stats[k] / 1000, 2)  # km
    return items
