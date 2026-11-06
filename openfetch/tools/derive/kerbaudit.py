"""Kerb completeness audit: finds every street corner that should have a kerb and checks it is closed, and every kerb end that
nothing explains, so nobody has to look at every line by eye (Jacky 6 Nov 2026: "I can't proof check every single line when we
scale it up").

Block corners. At every road junction (3 or more centrelines meet; tracks and paths left out), each gap of 30-170 deg between two
neighbouring roads with a property on the bisector within 40 m is a block corner, unless
  - the bisector crosses another road centreline before the property (a median or the other carriageway of a divided road), or
  - a road next to the corner has a second centreline running alongside it within 15 m (slip lanes, divided roads: the
    junction's own centrelines do not show where the kerb is).
Where both roads have a traced kerb on the corner's side (within 30 m of the junction), the corner is "covered": the kerb offset
of each road is measured on those pieces and the corner point P is where the two kerb lines, extended, cross. A closed corner has
a kerb crossing the line from the junction through P to the property; otherwise it is open and P is the marker (on the kerb, not mid-road).

Unexplained ends. A kerb end is explained when it is within 2 m of another kerb, at a side-street mouth (a road centreline within
25 m straight ahead), stops at a property (within 3 m ahead), or sits at the edge of the traced area. Any other end is a missing
corner or a gap.

    python3 kerbaudit.py kerbs.json(lon/lat GeoJSON) lots_dir roads_dir out.json [--epsg 7856]

out.json: {"corners", "covered", "open", "open_pct", "ends", "ends_unexplained", "points": [[x, y, gap_m, rank], ...] (open
corners, projected CRS, gap_m = distance from P to the nearest kerb, rank = road rank 1 main .. 3 local), "end_points": [[x, y]],
"kinks" (sharp kinks or wobbles anywhere), "caps_fussy" (those within 25 m of a dead end) with their points}.

Fussy shapes. Every kerb is walked every 1 m: a heading change of more than 45 deg within 1 m is a kink (round corners of 1.3 m or more
turn less), and turning back and forth more than 60 deg beyond the net turn within 10 m is a jog or wobble.
"""
import glob
import json
import os
import sys

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union

LOT_REACH = 40.0   # m, a property this close along the bisector makes the gap a block corner
ARM_REACH = 30.0   # m, both roads must have a kerb this close to the junction on the corner's side (else not traced here)
SHORT_REACH = 80.0  # m, kerbs on both roads within this but not ARM_REACH: the corner is covered (and surely open)
TWIN = 15.0        # m, a second centreline this close and parallel to an arm: slip lane or divided road, skip
SKIP_FH = {8, 9, 10, 11}  # functionhierarchy: proposed, tracks, walking tracks, paths: not streets with kerbs
END_NEAR = 2.0     # m, an end this close to another kerb is joined to it
MOUTH_AHEAD = 25.0  # m, a road centreline this far straight ahead: the kerb stops at a side street
EDGE = 60.0        # m, ends this close to the edge of the traced area are where tracing stopped


def road_rank(fh):
    """1 main (motorway, primary, arterial), 2 collector (sub-arterial, distributor), 3 local."""
    return 1 if fh in (1, 2, 3) else (2 if fh in (4, 5) else 3)


def load_roads(roads_dir):
    """Road centrelines with their functionhierarchy, each feature once (cells overlap)."""
    out, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(roads_dir, "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            if not f.get("geometry"):
                continue
            pr = f.get("properties") or {}
            key = pr.get("OBJECTID", pr.get("objectid", f.get("id")))
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            g = shape(f["geometry"])
            for p in (g.geoms if g.geom_type.startswith("Multi") else [g]):
                if p.geom_type == "LineString" and p.length > 0:
                    out.append((p, pr.get("functionhierarchy")))
    return out


def junctions(roads, snap=0.5):
    """[(J, [(unit heading out of J, rank, road index), ...])] where 3+ street centrelines meet."""
    ends = {}
    for ri, (g, fh) in enumerate(roads):
        if fh in SKIP_FH:
            continue
        c = np.asarray(g.coords)
        if len(c) < 2:
            continue
        for p, q in ((c[0], c[1:]), (c[-1], c[-2::-1])):
            k = tuple(np.round(p / snap).astype(int))
            L = LineString(np.r_[[p], q]); t = np.asarray(L.interpolate(min(15.0, L.length)).coords[0]) - p
            n = np.hypot(*t)
            if n > 1e-6:
                ends.setdefault(k, []).append((p, t / n, road_rank(fh), ri))
    return [(v[0][0], [(u, rk, ri) for _, u, rk, ri in v]) for v in ends.values() if len(v) >= 3]


class Kerbs:
    def __init__(self, kerbs):
        self.p = [np.asarray(k) for k in kerbs if len(k) > 1]
        self.g = [LineString(k) for k in self.p]
        self.tree = STRtree(self.g)

    def offset(self, J, u, n, reach=ARM_REACH):
        """Offset of the kerb along road heading u on side n (unit normal), measured 8-reach m from J; None if no kerb.
        The kerb nearest the properties wins (medians and lane lines sit nearer the centreline)."""
        best = None
        probe = LineString([J + u * 8 + n * 1.0, J + u * reach + n * 1.0, J + u * reach + n * 16, J + u * 8 + n * 16]).convex_hull
        for i in self.tree.query(probe, predicate="intersects"):
            seg = self.g[int(i)].intersection(probe)
            if seg.is_empty or seg.length < 3:
                continue
            c = np.asarray(seg.coords) if seg.geom_type == "LineString" else np.vstack([np.asarray(s.coords) for s in seg.geoms if s.geom_type == "LineString"])
            if len(c) < 2:
                continue
            d = c[-1] - c[0]
            if np.hypot(*d) < 2 or abs(d @ u) / np.hypot(*d) < np.cos(np.radians(20)):
                continue  # must run along the road
            off = float(np.median((c - J) @ n))
            if best is None or off > best:
                best = off
        return best


def corner_point(J, u1, n1, w1, u2, n2, w2):
    """Where the two kerb lines (road i: J + n_i * w_i + t * u_i) cross."""
    M = np.array([u1, -u2]).T
    if abs(np.linalg.det(M)) < 1e-6:
        return None
    a, b = np.linalg.solve(M, (J + n2 * w2) - (J + n1 * w1))
    return J + n1 * w1 + a * u1


def block_corners(roads, lots, K, rtree=None, area=None):
    """Every block corner inside the traced area: dicts {J, P, u1, u2, n1, n2, w1, w2, rank, bv, d_lot, covered, open}."""
    geoms = [g for g, _ in roads]
    rtree = rtree or STRtree(geoms)
    lt = STRtree(lots)
    out = []
    from shapely.prepared import prep
    inside = prep(area) if area is not None else None
    for J, arms in junctions(roads):
        if inside is not None and not inside.contains(Point(J)):
            continue
        own = {ri for _, _, ri in arms}
        # a slip lane / divided road: another street centreline alongside an arm, within TWIN m
        twin = False
        for u, rk, ri in arms:
            m = Point(J + u * 20)
            for k in rtree.query(m.buffer(TWIN), predicate="intersects"):
                k = int(k)
                if k in own or roads[k][1] in SKIP_FH:
                    continue
                g = geoms[k]; t = g.project(m)
                a = np.asarray(g.interpolate(max(t - 3, 0)).coords[0]); b = np.asarray(g.interpolate(min(t + 3, g.length)).coords[0])
                d = b - a; nd = np.hypot(*d)
                if nd > 1 and abs(d @ u) / nd > np.cos(np.radians(20)):
                    twin = True; break
            if twin:
                break
        if twin:
            continue
        arms = sorted(arms, key=lambda x: np.arctan2(x[0][1], x[0][0]))
        ang = [np.arctan2(u[1], u[0]) for u, _, _ in arms]
        for i in range(len(arms)):
            j = (i + 1) % len(arms)
            a1, a2 = ang[i], ang[j] + (2 * np.pi if j == 0 else 0)
            gap = a2 - a1
            if gap < np.radians(30) or gap > np.radians(170):
                continue
            b = (a1 + a2) / 2; bv = np.array([np.cos(b), np.sin(b)])
            ray = LineString([J, J + bv * LOT_REACH])
            hit = [lots[int(k)] for k in lt.query(ray, predicate="intersects")]
            if not hit:
                continue
            d_lot = min(h.distance(Point(J)) for h in hit)
            # a median or the other carriageway between the junction and the property: not a block corner
            seg = LineString([J + bv * 1.5, J + bv * d_lot])
            if any(int(k) not in own and roads[int(k)][1] not in SKIP_FH for k in rtree.query(seg, predicate="intersects")):
                continue
            u1, u2 = arms[i][0], arms[j][0]
            n1 = np.array([-u1[1], u1[0]]); n2 = np.array([u2[1], -u2[0]])  # normals pointing into the gap
            c = dict(J=J, u1=u1, u2=u2, n1=n1, n2=n2, bv=bv, d_lot=d_lot, rank=min(arms[i][1], arms[j][1]),
                     roads=(arms[i][2], arms[j][2]), covered=False, open=False, P=J + bv * d_lot * 0.7)
            out.append(c)
            w1, w2 = K.offset(J, u1, n1), K.offset(J, u2, n2)
            if w1 is None or w2 is None:
                # kerbs on both roads that stop more than SHORT_REACH m before the corner leave it open too
                w1, w2 = K.offset(J, u1, n1, SHORT_REACH), K.offset(J, u2, n2, SHORT_REACH)
                if w1 is None or w2 is None:
                    continue
                c["short"] = True
            P = corner_point(J, u1, n1, w1, u2, n2, w2)
            if P is None or np.hypot(*(P - J)) > LOT_REACH + 10:
                continue
            c.update(covered=True, w1=w1, w2=w2, P=P)
            dP = np.hypot(*(P - J)); dv = (P - J) / max(dP, 1e-6)
            # a round corner lies on the block side of P (up to r * (1 / sin(half angle) - 1) further), never past the property
            test = LineString([J, J + dv * max(dP + 3.0, d_lot + 1.0)])
            if not len(K.tree.query(test, predicate="intersects")):
                c["open"] = True
                c["gap"] = float(min(K.g[int(k)].distance(Point(P)) for k in K.tree.query(Point(P).buffer(60))) if len(K.tree.query(Point(P).buffer(60))) else 60.0)
    return out


def _end(p, w, back=3.0):
    q = p if w == 1 else p[::-1]
    e = q[-1]; d = 0.0; k = len(q) - 1
    while k > 0 and d < back:
        d += np.hypot(*(q[k] - q[k - 1])); k -= 1
    v = e - q[k]; n = np.hypot(*v)
    return e, (v / n if n > 1e-9 else np.array([1.0, 0.0]))


def traced_area(K):
    """Where kerbs were traced: every kerb grown by EDGE m, shrunk back by half (fills blocks, not the land beyond)."""
    if getattr(K, "_area", None) is None:
        K._area = unary_union([g.buffer(EDGE, quad_segs=4) for g in K.g]).buffer(-EDGE / 2, quad_segs=4)
    return K._area


def loose_ends(K, roads, lots, rtree=None):
    """Kerb ends nothing explains (see module text): [[x, y], ...] and the number of ends looked at."""
    geoms = [g for g, _ in roads]
    rtree = rtree or STRtree(geoms)
    lt = STRtree(lots)
    edge = traced_area(K).boundary
    loose, n = [], 0
    for i, p in enumerate(K.p):
        for w in (0, 1):
            e, v = _end(p, w); n += 1
            pe = Point(e)
            if any(int(k) != i and K.g[int(k)].distance(pe) <= END_NEAR for k in K.tree.query(pe.buffer(END_NEAR))):
                continue
            ahead = LineString([e, e + v * MOUTH_AHEAD])
            if any(roads[int(k)][1] not in SKIP_FH for k in rtree.query(ahead, predicate="intersects")):
                continue
            if len(lt.query(LineString([e, e + v * 3.0]), predicate="intersects")):
                continue
            if edge.distance(pe) < EDGE:
                continue
            loose.append([round(float(e[0]), 1), round(float(e[1]), 1)])
    return loose, n


KINK_TURN = np.radians(45)   # heading change within 1 m: a sharp kink (round corners of 1.3 m+ turn less, half circles
                             # across narrow lanes included)
WIGGLE = np.radians(60)      # turning back and forth within 10 m beyond the net turn: a jog or wobble
DEAD_NEAR = 25.0             # m, kinks this close to where a dead-end road stops are fussy caps


def kinks(K):
    """Sharp kinks and wobbles along every kerb, so fussy shapes are found without looking: [[x, y, kind], ...]."""
    out = []
    for p in K.p:
        g = LineString(p)
        if g.length < 3:
            continue
        s = np.arange(0, g.length, 1.0)
        q = np.array([g.interpolate(t).coords[0] for t in s])
        if len(q) < 5:
            continue
        h = np.unwrap(np.arctan2(*np.diff(q, axis=0).T[::-1]))
        last = -1e9
        for i in range(2, len(h) - 2):
            if max(abs(h[i] - h[i - 1]), abs(h[i + 1] - h[i])) > KINK_TURN and s[i] - last > 3:
                out.append([round(float(q[i][0]), 1), round(float(q[i][1]), 1), "kink"]); last = s[i]
        d = np.abs(np.diff(h)); W = 10
        if len(d) > W:
            c = np.r_[0, np.cumsum(d)]
            for i in range(0, len(d) - W, W // 2):
                if c[i + W] - c[i] - abs(h[i + W] - h[i]) > WIGGLE and s[i] - last > 3:
                    out.append([round(float(q[i + W // 2][0]), 1), round(float(q[i + W // 2][1]), 1), "wobble"]); last = s[i]
    return out


def dead_tips(roads, lots, rtree=None):
    """Where a street centreline stops with a property straight ahead (a dead end)."""
    from scipy.spatial import cKDTree
    geoms = [g for g, _ in roads]
    rtree = rtree or STRtree(geoms)
    lt = STRtree(lots)
    tips = []
    for g, fh in roads:
        if fh in SKIP_FH:
            continue
        c = np.asarray(g.coords)
        for e, nx in ((c[0], c[1]), (c[-1], c[-2])):
            tips.append((e, e - nx))
    T = cKDTree(np.array([t[0] for t in tips]))
    out = []
    for e, v in tips:
        if len(T.query_ball_point(e, 1.0)) > 1 or len(rtree.query(Point(e).buffer(1.0), predicate="intersects")) > 1:
            continue
        n = np.hypot(*v)
        if n < 1e-6:
            continue
        v = v / n
        if len(lt.query(LineString([e, e + v * 20]), predicate="intersects")):
            out.append(e)
    return out


def audit(kerbs, lots, roads):
    K = Kerbs(kerbs)
    rtree = STRtree([g for g, _ in roads])
    cs = block_corners(roads, lots, K, rtree, traced_area(K))
    cov = [c for c in cs if c["covered"]]
    op = [c for c in cov if c["open"]]
    loose, n = loose_ends(K, roads, lots, rtree)
    kk = kinks(K)
    fussy = []
    if kk:
        from scipy.spatial import cKDTree
        tips = dead_tips(roads, lots, rtree)
        if tips:
            TT = cKDTree(np.array(tips))
            fussy = [k for k in kk if TT.query(k[:2])[0] < DEAD_NEAR]
    km = sum(g.length for g in K.g) / 1000
    return {"corners": len(cs), "covered": len(cov), "open": len(op),
            "open_pct": round(100.0 * len(op) / max(len(cov), 1), 2),
            "short": sum(1 for c in op if c.get("short")), "ends": n, "ends_unexplained": len(loose),
            "points": [[round(float(c["P"][0]), 1), round(float(c["P"][1]), 1), round(c["gap"], 1), c["rank"]] for c in op],
            "end_points": loose, "km": round(km, 1), "kinks": len(kk), "kinks_per_km": round(len(kk) / max(km, 1e-6), 2),
            "caps_fussy": len(fussy), "kink_points": kk, "fussy_points": fussy}


def read_kerbs(path, epsg=7856):
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    kerbs = []
    for f in json.load(open(path))["features"]:
        g = f["geometry"]
        for c in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            x, y = tr.transform(*np.asarray(c)[:, :2].T)
            kerbs.append(np.c_[x, y])
    return kerbs


def main(a):
    import kerbregular as kr
    epsg = int(a[a.index("--epsg") + 1]) if "--epsg" in a else 7856
    kerbs = read_kerbs(a[0], epsg)
    lots = [g for g in kr.load_faces(a[1]) if g.geom_type == "Polygon"]
    roads = load_roads(a[2])
    r = audit(kerbs, lots, roads)
    json.dump(r, open(a[3], "w"))
    print(json.dumps({k: v for k, v in r.items() if not k.endswith("points")}))


if __name__ == "__main__":
    main(sys.argv[1:])
