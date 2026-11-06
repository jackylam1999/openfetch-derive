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
  4. cap    a kerb end that runs into a property (house lot, not a road lot) stops at the lot edge
  5. drop   short pieces still on their own after 1-4 (broken bits nobody can use, e.g. tram stops and medians in the CBD)

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
                if ang >= MOUTH_ANG:
                    cuts.append(t)
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
        tree = cKDTree(np.array([e for e, _ in E]))
        rng = JOIN_MAX if rule == "join" else BRIDGE_MAX
        cand = []
        for a, b in tree.query_pairs(rng):
            (la, wa), (lb, wb) = ends[a], ends[b]
            if la == lb:
                continue
            (ea, ua), (eb, ub) = E[a], E[b]
            d = eb - ea; g = np.hypot(*d)
            if g < 0.05:
                cand.append((g, a, b, np.array([ea, eb]), 0.0, 0.0)); continue
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
            if tA > 0 or tB > 0:
                if _same_chain(links, la, lb):
                    continue
                for li_, wi_, t_ in ((la, wa, tA), (lb, wb, tB)):
                    if t_ > 0:
                        pp = items[li_]["p"]; Lp = LineString(pp).length
                        items[li_] = dict(items[li_], p=_cut(pp, Lp - t_, True) if wi_ == 1 else _cut(pp, t_, False))
                        lens[li_] = Lp - t_
                ea2 = _end(items[la]["p"], wa)[0]; eb2 = _end(items[lb]["p"], wb)[0]
                conn = np.vstack([ea2[None], conn, eb2[None]])
            # never close a chain onto itself through these links
            if _same_chain(links, la, lb):
                continue
            used |= {a, b}
            L = LineString(conn).length if len(conn) > 1 else 0.0
            links[(la, wa)] = (lb, wb, conn, L); links[(lb, wb)] = (la, wa, conn[::-1], L)
            stats[rule + "_n"] = stats.get(rule + "_n", 0) + 1
            stats.setdefault("_conn", []).append((rule, conn))
            stats[rule + "_m"] = stats.get(rule + "_m", 0.0) + L
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


def draft(items, world, stats, rules=("mouths", "join", "corners", "caps", "fragments", "drop")):
    if "mouths" in rules:
        items = mouths(items, world, stats)
    if "join" in rules:
        items = join(items, world, stats)
    if "corners" in rules:
        items = corners(items, world, stats)
    if "caps" in rules:
        items = caps(items, world, stats)
    if "fragments" in rules:
        items = fragments(items, stats)
    if "drop" in rules:
        items = drop(items, stats)
    stats.pop("_conn", None) if not stats.get("_keep") else None
    for k in list(stats):
        if k.endswith("_m"):
            stats[k] = round(stats[k] / 1000, 2)  # km
    return items
