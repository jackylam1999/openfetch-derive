"""State-road sides beside council kerbs (kerb scenario 12, 21 Nov 2026). Councils such as Parramatta draw kerb lines on their own
streets and stop at the state road: Victoria Rd, the Great Western Hwy, Church St and James Ruse Dr are 2-15 % kerbed while the side
streets are. KN6 (P-0207) outlined council pavement shapes wherever no council kerb was near and failed review 13 of 28 (car-park
aisles, planter loops, chords across paved corners, lines across mouths and roundabouts): the outline was never tied to where a
real kerb starts and stops. Here it is:
  anchors  council kerb free ends within ANCHOR_R m of a main road (functionhierarchy 2-4), each beside a council surface outline
           (footpath shapes: the road is outside them; pavement shapes: the road is inside them) within V_MAX m
  side     drawn only between two consecutive anchors on the same outline (driveway gaps under 2*CLOSE m closed), following the
           outline (smoothed over SMOOTH m, so footpath steps are not kerb steps), set off into the road by the verge measured
           at the two anchors (linear between them; when they differ by more than VERGE_DIFF the change must sit round a corner)
  refused  not beside a main road, a turn over TURN_MAX deg in the middle (round the block), a street centreline crossed, a
           council kerb alongside or crossed, a loop, a sharp kink, both ends on one council kerb, shorter than MIN_LEN m
Both ends are council kerb ends, so no line ends free. Known answer (--known): council kerb sides are cut in the middle, rebuilt
from the two cut ends with the same rules, and compared with the hidden piece (Parramatta: see the case file).
    python3 kerbstate.py kerbs.geojson surface.geojson roads.geojson out.geojson [--pavement] [--all-streets] [--why why.json]
        [--tram railways.geojson (NSW Railway layer; classsubtype 2 light rail: a side with light rail alongside is left blank, the
        street was rebuilt after the council surveyed it, e.g. Church St Parramatta for the 2024 light rail)]
        [--ground dir (kerbpcw 0.5 m LiDAR ground grids <x km>_<y km>.npz: a side whose kerb step lies mostly over 3 m from it is refused)]
    python3 kerbstate.py --known kerbs.geojson surface.geojson roads.geojson report.json [--pavement]
    python3 kerbstate.py --selftest
Inputs in EPSG:7856 metres (GDA2020 MGA 56); a council served in GDA94 is moved to GDA2020 before this (kerbstate_fetch.py).
Output lon/lat GDA2020 (EPSG:7844) lines with id (from the place), len, v0, v1, road.
"""
import collections, json, sys
import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.strtree import STRtree

ANCHOR_R, END_TOUCH, V_MAX, CLOSE = 30.0, 0.5, 4.0, 4.0
MAX_LEN, END_ZONE, TURN_MAX, STEP_TURN, KINK = 400.0, 12.0, 45.0, 35.0, 100.0
TURN_ABS, FACE_SHARE, TRAM_D, WANDER, WANDER_RUN = 60.0, 0.8, 15.0, 2.0, 10.0
MAIN_D, MAIN_SHARE, DUP_D, DUP_RUN, CROSS_ZONE = 25.0, 0.7, 1.0, 3.0, 3.0
VERGE_DIFF, SMOOTH, RAMP, CORNER_TURN = 2.0, 6.0, 14.0, 45.0
# within SMOOTH m of a pinned council end the smoothing window shrinks to nothing, so a side shorter than 4*SMOOTH has no smoothed
# middle and copies the outline's corner notches (pack1 s12-15: an 11 m piece hooking from a slip-lane island kerb to the main kerb)
MIN_LEN = 4 * SMOOTH
# LiDAR kerb rise (--ground, kerbpcw 0.5 m ground grids; kerb card S12 H9, after the canopy card's H5): walking out from the street
# centreline, the first rise of GSTEP m over about 1.5 m is the kerb (a rise that falls back within 1.5-2.5 m is an island or median and is
# skipped). Where fewer than GSHARE of the judged samples in a GWIN m window lie within GOFF m of the line, that stretch is cut (not the
# side). Intensity is NOT used: red bus lanes and concrete slabs read as "not road" (pack1 03 17 40). Labels: pack-2 moved-4.5 m controls
# 5/5 cut, OK lines 0/32; pack-1 OK 1/33. GSTEP from 10 cm: 6-9 cm rises inside the carriageway (resurfacing
# joints, vehicle edges) stopped the walk on pack-1 OK 03 and 11. Uncovered or unjudged stretches are kept as drawn.
GSTEP, GOFF, GSHARE, GWIN, GMERGE = (0.10, 0.35), 3.0, 0.5, 40.0, 10.0
HIDE_MIN, HIDE_FROM, HIDE_TO = 60.0, 0.3, 0.7


def parts(g):
    return list(g.geoms) if g.geom_type.startswith("Multi") or g.geom_type == "GeometryCollection" else [g]


def read(fn):
    return [f for f in json.load(open(fn))["features"] if f.get("geometry")]


def ring_sub(ring, a, b):
    L = ring.length
    if b < a:
        b += L
    return [ring.interpolate(d % L).coords[0][:2] for d in np.arange(a, b, 0.5).tolist() + [b]]


def turning(pts):
    p = np.asarray(pts, float); v = np.diff(p, axis=0); n = np.hypot(v[:, 0], v[:, 1]); v = v[n > 1e-6] / n[n > 1e-6, None]
    if len(v) < 2:
        return 0.0, 0.0, 0.0
    a = np.arctan2(v[1:, 1], v[1:, 0]) - np.arctan2(v[:-1, 1], v[:-1, 0]); a = (a + np.pi) % (2 * np.pi) - np.pi
    return float(np.degrees(abs(a.sum()))), float(np.degrees(np.abs(a).max())), float(np.degrees(np.abs(a).sum()))


class World:
    def __init__(self, kerbs, surface, roads, pavement=False, all_streets=False, tram=(), ground=None):
        self.ground = ground
        self.tram = list(tram); self.TT = STRtree(self.tram) if self.tram else None
        self.KL = [p for g in kerbs for p in parts(g) if p.length > 0.5]; self.KT = STRtree(self.KL)
        U = shapely.unary_union([g.buffer(0) for g in surface])
        self.Uc = U.buffer(CLOSE, join_style="mitre").buffer(-CLOSE, join_style="mitre"); shapely.prepare(self.Uc)
        self.rings = [r for p in parts(self.Uc) if p.geom_type == "Polygon" for r in [p.exterior] + list(p.interiors) if r.length > MIN_LEN]
        self.RGT = STRtree(self.rings) if self.rings else None
        self.road_out = -1.0 if pavement else 1.0
        st = [(p, g) for p, g in roads if int(p.get("roadontype", 1)) == 1]
        self.RL = [g for p, g in st]; self.RT = STRtree(self.RL)
        # the kerb-rise walk starts from a street (functionhierarchy 1-7), never a track, path or cycleway (8-11 sit on footpaths)
        self.WL = [p2 for p, g in st if int(p.get("functionhierarchy", 9)) <= 7 for p2 in parts(g)]; self.WT = STRtree(self.WL) if self.WL else None
        lo = 1 if all_streets else 2
        hi = 6 if all_streets else 4
        self.main = [g for p, g in st if lo <= int(p.get("functionhierarchy", 9)) <= hi]; self.MT = STRtree(self.main) if self.main else None

    def end_dir(self, li, e):
        l = self.KL[li]; c0 = np.asarray(l.coords[0][:2])
        inner = l.interpolate(min(1.5, l.length)) if np.hypot(*(c0 - e)) < 1e-6 else l.interpolate(max(l.length - 1.5, 0))
        d = e - np.asarray(inner.coords[0][:2]); return d / max(np.hypot(*d), 1e-9)

    def anchors(self, why):
        A = collections.defaultdict(list)
        if self.MT is None or self.RGT is None:
            return A
        for li, l in enumerate(self.KL):
            for e in (np.asarray(l.coords[0][:2]), np.asarray(l.coords[-1][:2])):
                P = Point(e)
                if any(j != li and self.KL[j].distance(P) < END_TOUCH for j in self.KT.query(P.buffer(END_TOUCH))):
                    continue
                if not any(self.main[i].distance(P) < ANCHOR_R for i in self.MT.query(P.buffer(ANCHOR_R))):
                    continue
                best = None
                for ri in self.RGT.query(P.buffer(V_MAX)):
                    d = self.rings[ri].distance(P)
                    if d <= V_MAX and (best is None or d < best[1]):
                        best = (ri, d)
                if best is None:
                    why["end with no surface outline within 4 m"] += 1; continue
                if self.Uc.contains(P) == (self.road_out > 0):
                    why["end on the wrong side of the outline"] += 1; continue
                A[best[0]].append((self.rings[best[0]].project(P), best[1], e, li))
        return A

    def judge(self, ring, a, b):
        s1, v1, e1, l1 = a; s2, v2, e2, l2 = b
        L = (s2 - s1) % ring.length
        if L < MIN_LEN:
            return "short"
        if L > MAX_LEN:
            return "long"
        if l1 == l2:
            return "both ends on one council kerb"
        G0 = LineString(ring_sub(ring, s1, s2)); n = max(3, int(G0.length) + 1); S = np.linspace(0, G0.length, n)
        P = np.array([G0.interpolate(x).coords[0][:2] for x in S]); Q = P.copy()
        for i in range(1, n - 1):
            h = min(SMOOTH, S[i], S[-1] - S[i]); m = (S >= S[i] - h) & (S <= S[i] + h); Q[i] = P[m].mean(0)
        tan = np.gradient(Q, axis=0); tan /= np.maximum(np.hypot(tan[:, 0], tan[:, 1]), 1e-9)[:, None]
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1); k = n // 2
        if self.Uc.contains(Point(Q[k] + nrm[k] * 0.3)) == (self.road_out > 0):
            nrm = -nrm
        # the road is on the side the line is set off to (never the back edge of a footpath strip, along the lots)
        idx = range(0, n, 5); face = 0
        for i in idx:
            Pi = Point(Q[i]); near = [self.main[j] for j in self.MT.query(Pi.buffer(MAIN_D))]
            if near:
                g = min(near, key=lambda x: x.distance(Pi)); c = np.asarray(shapely.ops.nearest_points(g, Pi)[0].coords[0][:2])
                face += (c - Q[i]) @ nrm[i] > 0
        if face < FACE_SHARE * len(idx):
            return "set off away from the road"
        if abs(v1 - v2) <= VERGE_DIFF:
            vv = v1 + (v2 - v1) * S / S[-1]
        else:
            lo = v1 < v2; seg = Q[S >= S[-1] - RAMP] if lo else Q[S <= RAMP]
            if len(seg) < 3 or turning(seg)[0] < CORNER_TURN:
                return "verge differs at the two corners"
            vm, vo = (v1, v2) if lo else (v2, v1)
            vv = np.where(S < S[-1] - RAMP, vm, vm + (vo - vm) * (S - (S[-1] - RAMP)) / RAMP) if lo else np.where(S > RAMP, vm, vo + (vm - vo) * S / RAMP)
        off = Q + nrm * vv[:, None]
        G = LineString([tuple(e1)] + [tuple(p) for p in off[1:-1]] + [tuple(e2)]).simplify(0.05); line = [tuple(p) for p in G.coords]
        return self.check(G, line, l1, l2)

    def check(self, G, line, l1, l2):
        if G.length > MAX_LEN:
            return "long"
        samp = [G.interpolate(x, normalized=True) for x in np.linspace(0.05, 0.95, 19)]
        near = sum(any(self.main[i].distance(p) < MAIN_D for i in self.MT.query(p.buffer(MAIN_D))) for p in samp)
        if near / len(samp) < MAIN_SHARE:
            return "not beside a main road"
        if self.TT is not None and sum(any(self.tram[i].distance(p) < TRAM_D for i in self.TT.query(p.buffer(TRAM_D))) for p in samp) > 0.2 * len(samp):
            return "light rail alongside (street rebuilt after the council data)"
        cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(line), axis=0).T))])
        inner = [p for p, c in zip(line, cum) if END_ZONE < c < G.length - END_ZONE]
        if len(inner) > 2:
            tot, mx, ab = turning(LineString(inner).simplify(0.25).coords)
            if tot > TURN_MAX or mx > STEP_TURN or ab > TURN_ABS:
                return "turns round a corner in the middle"
        # the kerb runs with the road: its distance from the main-road centreline stays on the straight line between the two ends'
        # distances; a footpath that wanders off through a wide verge (Parramatta pack s12-04, 3-8 m behind a bus-lane kerb) does not
        ss = np.arange(END_ZONE, G.length - END_ZONE, 2.0)
        if len(ss) >= 3:
            def dmain(p):
                return min(self.main[i].distance(p) for i in self.MT.query(p.buffer(MAIN_D * 2))) if len(self.MT.query(p.buffer(MAIN_D * 2))) else np.nan
            d = np.array([dmain(G.interpolate(x)) for x in ss])
            if not np.isnan(d).any():
                lin = d[0] + (d[-1] - d[0]) * (ss - ss[0]) / max(ss[-1] - ss[0], 1e-9); off = np.abs(d - lin) > WANDER; run = best = 0
                for o in off:
                    run = run + 2.0 if o else 0; best = max(best, run)
                if best >= WANDER_RUN:
                    return "wanders off the road line"
        if turning(line)[1] > KINK:
            return "sharp kink"
        core = shapely.ops.substring(G, CROSS_ZONE, G.length - CROSS_ZONE) if G.length > 2 * CROSS_ZONE + 1 else G
        if any(self.RL[i].intersects(core) for i in self.RT.query(core)):
            return "crosses a street"
        for j in self.KT.query(G.buffer(DUP_D)):
            if self.KL[j].buffer(DUP_D).intersection(G).length > DUP_RUN + (1.5 if j in (l1, l2) else 0):
                return "runs along a council kerb"
            if j not in (l1, l2) and self.KL[j].intersects(core):
                return "crosses a council kerb"
        if not G.is_simple:
            return "loops"
        return line

    def rise_offsets(self, G, step=2.0):
        """(along, how far the line lies behind the first kerb rise walking out from the nearest street centreline) every step m; nan
        where the walk is not square to the line (another street), the ground is not covered, or no rise is found"""
        DT = 0.25; out = []
        for s in np.arange(1.0, G.length - 0.99, step):
            Q = np.asarray(G.interpolate(s).coords[0][:2]); near = self.WT.query(Point(Q).buffer(25)) if self.WT is not None else []
            if not len(near):
                out.append((s, np.nan)); continue
            k = min(near, key=lambda i: self.WL[i].distance(Point(Q))); C = np.asarray(self.WL[k].interpolate(self.WL[k].project(Point(Q))).coords[0][:2])
            v = Q - C; dq = np.hypot(*v); a = np.asarray(G.interpolate(max(s - 1, 0)).coords[0][:2]); b = np.asarray(G.interpolate(min(s + 1, G.length)).coords[0][:2])
            tv = (b - a) / max(np.hypot(*(b - a)), 1e-9)
            if dq < 1.5 or abs((v / dq) @ tv) > 0.5:
                out.append((s, np.nan)); continue
            u = v / dq; tt = np.arange(0, dq + 6, DT); H = self.ground.height(C[0] + u[0] * tt, C[1] + u[1] * tt); e = np.nan
            if np.isfinite(H).mean() < 0.3:
                out.append((s, np.nan)); continue
            for i in range(int(2.0 / DT), len(H) - 10):
                lo, hi = H[i - 4:i], H[i + 2:i + 6]
                if np.isfinite(lo).sum() >= 2 and np.isfinite(hi).sum() >= 2 and GSTEP[0] <= np.nanmedian(hi) - np.nanmedian(lo) <= GSTEP[1]:
                    back = H[i + 6:i + 10]
                    if np.isfinite(back).sum() >= 2 and np.nanmedian(back) - np.nanmedian(hi) <= -0.06:
                        continue
                    e = tt[i] + 0.25; break
            out.append((s, dq - e))
        return np.array(out).reshape(-1, 2)

    def cut(self, line):
        """the line's pieces after cutting every stretch the LiDAR kerb rise puts more than GOFF m off (pieces under MIN_LEN dropped)"""
        G = LineString(line); o = self.rise_offsets(G)
        if not len(o):
            return [line], 0.0
        s, v = o[:, 0], o[:, 1]; bad = np.zeros(len(s), bool)
        for a in np.arange(0, max(G.length - GWIN, 0) + 0.1, 2.0):
            m = (s >= a) & (s < a + GWIN); x = v[m][np.isfinite(v[m])]
            if len(x) >= max(5, m.sum() / 2) and (np.abs(x) <= GOFF).mean() < GSHARE:
                bad |= m & np.isfinite(v) & (np.abs(np.nan_to_num(v)) > GOFF)
        if not bad.any():
            return [line], 0.0
        idx = np.where(bad)[0]; runs = [[s[idx[0]], s[idx[0]]]]
        for i in idx[1:]:
            if s[i] - runs[-1][1] <= GMERGE:
                runs[-1][1] = s[i]
            else:
                runs.append([s[i], s[i]])
        keep, at = [], 0.0
        for a, b in runs:
            keep.append((at, max(a - 1.0, at))); at = min(b + 1.0, G.length)
        keep.append((at, G.length)); cut_len = G.length - sum(y - x for x, y in keep)
        return [[tuple(c[:2]) for c in shapely.ops.substring(G, x, y).coords] for x, y in keep if y - x >= MIN_LEN], cut_len

    def sides(self):
        why = collections.Counter(); out = []
        for ri, A in self.anchors(why).items():
            A.sort(key=lambda x: x[0])
            if len(A) < 2:
                why["single end on its outline"] += 1; continue
            for k in range(len(A)):
                r = self.judge(self.rings[ri], A[k], A[(k + 1) % len(A)])
                if isinstance(r, str):
                    why[r] += 1
                else:
                    why["drawn"] += 1; pieces = [r]
                    if self.ground is not None:
                        pieces, cl = self.cut(r)
                        if cl > 0:
                            why["sides cut where the LiDAR kerb rise is over 3 m off"] += 1; why["m cut"] += round(cl)
                    out += [(p, A[k][1], A[(k + 1) % len(A)][1]) for p in pieces]
        return out, why


def to_feats(sides, road_name=None):
    from pyproj import Transformer
    t = Transformer.from_crs(7856, 7844, always_xy=True); F = []
    for line, v0, v1 in sides:
        ll = [t.transform(x, y) for x, y in line]; m = LineString(line).interpolate(0.5, normalized=True)
        F.append({"type": "Feature", "properties": {"id": "s12-%d-%d" % (round(m.x), round(m.y)), "len": round(LineString(line).length, 1),
                  "v0": round(float(v0), 2), "v1": round(float(v1), 2)},
                  "geometry": {"type": "LineString", "coordinates": [[round(x, 8), round(y, 8)] for x, y in ll]}})
    F.sort(key=lambda f: f["properties"]["id"])
    return F


def hide(kerbs):
    """cut the middle (HIDE_FROM-HIDE_TO) out of every council kerb part longer than HIDE_MIN m; returns kept parts and hidden pieces"""
    kept, hidden = [], []
    for g in kerbs:
        for p in parts(g):
            if p.length < HIDE_MIN:
                kept.append(p); continue
            a, b = p.length * HIDE_FROM, p.length * HIDE_TO
            kept += [shapely.ops.substring(p, 0, a), shapely.ops.substring(p, b, p.length)]; hidden.append(shapely.ops.substring(p, a, b))
    return kept, hidden


def known(kerbs, surface, roads, pavement=False):
    kept, hidden = hide(kerbs)
    w = World(kept, surface, roads, pavement, all_streets=True); got, why = w.sides()
    HT = STRtree(hidden); err = []; n_hid = 0
    for line, v0, v1 in got:
        G = LineString(line); h = [hidden[i] for i in HT.query(G.buffer(3)) if hidden[i].distance(G) < 3]
        if not h:
            err.append(None); continue
        H = min(h, key=lambda x: x.hausdorff_distance(G)); n_hid += 1
        d = [H.distance(G.interpolate(s)) for s in np.arange(0, G.length, 1.0)]
        err.append(d)
    flat = np.array([x for d in err if d for x in d])
    rep = {"hidden pieces": len(hidden), "rebuilt": len(got), "matched to a hidden piece": n_hid,
           "rebuilt with no hidden piece within 3 m": sum(d is None for d in err), "why": dict(why)}
    if len(flat):
        rep.update({"within 1 m": round(float(np.mean(flat <= 1)), 4), "within 3 m": round(float(np.mean(flat <= 3)), 4),
                    "sides with a point over 3 m": sum(1 for d in err if d and max(d) > 3)})
    return rep


def selftest():
    # one main road along y=0, carriageway 10 m, footpath strip from y=11 to 13 on the north side, two side streets x=0 and x=100
    roads = [({"functionhierarchy": 3, "roadontype": 1}, LineString([(-60, 0), (160, 0)])),
             ({"functionhierarchy": 6, "roadontype": 1}, LineString([(0, 0), (0, 80)])), ({"functionhierarchy": 6, "roadontype": 1}, LineString([(100, 0), (100, 80)]))]
    foot = [Polygon([(8, 11), (92, 11), (92, 80), (90, 80), (90, 13), (10, 13), (10, 80), (8, 80)])]
    # council kerbs come down the side streets and stop at the corner, tangent to the main road (verge 1 m)
    k1 = LineString([(5, 60), (5, 15), (6.5, 11.5), (10, 10), (12, 10)]); k2 = LineString([(95, 60), (95, 15), (93.5, 11.5), (90, 10), (88, 10)])
    w = World([k1, k2], foot, roads); got, why = w.sides()
    assert len(got) == 1, why
    G = LineString(got[0][0]); mid = G.interpolate(0.5, normalized=True)
    assert abs(mid.y - 10) < 0.2 and sorted([G.coords[0][0], G.coords[-1][0]]) == [12.0, 88.0], list(G.coords)[:3]
    # a lane centreline into the block between the two corners: the side would cross its mouth, so it is refused
    lane = ({"functionhierarchy": 7, "roadontype": 1}, LineString([(50, 0), (50, 40)]))
    got2, why2 = World([k1, k2], foot, roads + [lane]).sides()
    assert not got2 and why2["crosses a street"] >= 1, why2
    # a council kerb already along the middle of the side: only the two gaps either side of it are drawn, never over it
    mk = LineString([(42, 10), (58, 10)]); got3, why3 = World([k1, k2, mk], foot, roads).sides()
    assert len(got3) == 2 and all(mk.buffer(0.5).intersection(LineString(g[0])).length < 0.6 for g in got3), why3
    # local street only (no main road): nothing unless --all-streets
    loc = [({"functionhierarchy": 6, "roadontype": 1}, roads[0][1])] + roads[1:]
    assert not World([k1, k2], foot, loc).sides()[0] and World([k1, k2], foot, loc, all_streets=True).sides()[0]
    # footpath that turns away round the block in the middle (no frontage): refused
    foot4 = [Polygon([(8, 11), (40, 11), (40, 20), (60, 20), (60, 11), (92, 11), (92, 80), (8, 80)])]
    assert not World([k1, k2], foot4, roads).sides()[0]
    # hide-and-rebuild finds the hidden middle of a long council kerb along the footpath
    long_k = LineString([(-50, 10), (5, 10), (95, 10), (150, 10)])
    foot5 = [Polygon([(-60, 11), (160, 11), (160, 13), (-60, 13)])]
    rep = known([long_k], foot5, roads[:1])
    assert rep["rebuilt"] == 1 and rep["within 1 m"] == 1.0, rep
    # a footpath that bows 4 m away from the road mid-block: the line would wander into the verge, refused
    foot6 = [Polygon([(8, 11), (30, 11), (50, 15), (70, 11), (92, 11), (92, 80), (8, 80)])]
    assert not World([k1, k2], foot6, roads).sides()[0], "wander"
    tram = LineString([(0, 6), (100, 6)])
    assert not World([k1, k2], foot, roads, tram=[tram]).sides()[0], "light rail alongside"
    # a corner gap shorter than MIN_LEN: refused, never a hook
    k3 = LineString([(5, 60), (5, 15), (6.5, 11.5), (10, 10), (30, 10)]); k4 = LineString([(42, 10), (60, 10), (88, 10)])
    assert not [g for g in World([k3, k4], foot, roads).sides()[0] if LineString(g[0]).length < MIN_LEN], "short side"
    # LiDAR ground: kerb step at the line keeps the side, a kerb step 6 m into the road refuses it, no ground cover changes nothing
    import kerbpcw
    def grid(ky):
        g = kerbpcw.Ground("/nonexistent"); n = int(1000 / kerbpcw.RES); yy = (np.arange(n) + 0.5) * kerbpcw.RES
        z = np.where(yy >= ky, 0.15, 0.0).astype(np.float32)[:, None].repeat(n, 1)
        g.mem.update({(-1, 0): z, (0, 0): z, (-1, -1): np.zeros((n, n), np.float32), (0, -1): np.zeros((n, n), np.float32)}); return g
    g10 = World([k1, k2], foot, roads, ground=grid(10)).sides()[0]
    assert len(g10) == 1 and LineString(g10[0][0]).length > 70, "LiDAR kerb rise at the line: kept whole"
    assert not World([k1, k2], foot, roads, ground=grid(4)).sides()[0], "LiDAR kerb rise 6 m into the road: cut away"
    assert len(World([k1, k2], foot, roads, ground=kerbpcw.Ground("/nonexistent")).sides()[0]) == 1, "no LiDAR cover: kept"
    half = grid(10); n = int(1000 / kerbpcw.RES); yy = (np.arange(n) + 0.5) * kerbpcw.RES
    zw = np.where(yy >= 4, 0.15, 0.0).astype(np.float32)[:, None].repeat(n, 1); zw[:, int(50 / kerbpcw.RES):] = half.mem[(0, 0)][:, int(50 / kerbpcw.RES):]
    half.mem[(0, 0)] = zw; gh = World([k1, k2], foot, roads, ground=half).sides()[0]
    assert len(gh) == 1 and min(x for x, y in gh[0][0]) > 40, ("west half 6 m off: cut, east half kept", gh)
    print("kerbstate selftest pass")
    return 0


def main(a):
    if a == ["--selftest"]:
        return selftest()
    pav = "--pavement" in a; alls = "--all-streets" in a
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and not (i and a[i - 1] in ("--why", "--tram", "--ground"))]
    rd = lambda fn: [shape(f["geometry"]) for f in read(fn)]
    roads = [(f["properties"], shape(f["geometry"])) for f in read(pos[2])]
    if a[0] == "--known":
        rep = known(rd(pos[0]), rd(pos[1]), roads, pav); json.dump(rep, open(pos[3], "w"), indent=1); print(json.dumps(rep)); return 0
    tram = [shape(f["geometry"]) for f in read(a[a.index("--tram") + 1]) if int(f["properties"].get("classsubtype", 0)) == 2] if "--tram" in a else []
    gr = None
    if "--ground" in a:
        import kerbpcw
        gr = kerbpcw.Ground(a[a.index("--ground") + 1])
    w = World(rd(pos[0]), rd(pos[1]), roads, pav, alls, tram, gr); got, why = w.sides()
    F = to_feats(got); json.dump({"type": "FeatureCollection", "features": F}, open(pos[3], "w"))
    if "--why" in a:
        json.dump(dict(why), open(a[a.index("--why") + 1], "w"), indent=1)
    print(dict(why), "sides", len(F), "km %.2f" % (sum(f["properties"]["len"] for f in F) / 1000)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if sys.argv[1:] else print(__doc__))
