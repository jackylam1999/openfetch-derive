"""Grid kerbs (Jacky 15 Nov 2026: "many of the box look like a grid ... just continue down"). For a street block with NO gap kerb
drawn yet: the block face between ground street centrelines, minus each street's band (centreline +- the kerb distance measured
from the traced kerbs on that same side), corners rounded. Kept whole or left blank. Lessons kept from the 6-7 Nov centreline
loops (kerbnet.py): never replace a drawn kerb (only blank blocks), lanes and tunnels/bridges never shape a block, no open ends.

    python3 kerbgrid.py lots_dir roads_dir raw.json drawn_dir out.json --box x0 y0 x1 y1 --buildings footprints.json(lon/lat) [--why why.json] [--official o.json] [--road intensity_grid_dir] [--class-width]

Road surface (KN13, 20 Nov 2026, case P-0220): a block's street bands are the width measured from traced kerbs on that side, or, with none,
the road-class width (HALF_W). Class-width rings put Lidcombe kerbs 2-3 m inside the roadway (version 2026-11-18: 26 of 30 reviewed refused
lines odd). Now a ring is judged on the LiDAR road surface (kerbroad.judge_ring) wherever --road has a grid for it; a ring with any side
at an assumed class width and no road-surface data is refused ("class width, no road surface") unless --class-width is given.
"""
import glob, json, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka
import kerbnet as kn
import kerbregular as kr
import kerbroad as krd

HALF_W = {1: 9.0, 2: 8.0, 3: 7.0, 4: 6.5, 5: 5.5, 6: 4.5, 7: 3.0, 8: 4.0}
LANE_FH = 7
ROUND = 4.0          # m corner radius
LOT_IN, LOT_RUN = 5.0, 3.0   # lot lines sit up to 5 m off the aerial in the CBD (lessons), so lots only catch gross errors
BLD_IN, BLD_RUN = 1.5, 3.0   # the ring may not run more than 1.5 m inside a building footprint for over 3 m
MALL_FH, MALL_LOTS = (8, 9, 10, 11), 0.3   # a path with buildings on both sides (Pitt St Mall, Martin Place) splits blocks like a street
AGREE_NEAR, AGREE_D, AGREE_MIN = 6.0, 2.5, 0.7   # where a traced kerb lies within 6 m, it must be within 2.5 m on 70 % of it
OPEN_W, OPEN_A = 4.5, 40.0   # an open area (no lot) over 9 m wide inside the ring: plaza, mall or a street missing from the map
LOT_SHARE = 0.5
DRAWN_D = 3.0
SAME_DIR = 12.0
COVERED = 0.5    # a street line more than half under building footprints runs beneath a building: not a street on the ground
STUB_MAX = 80.0  # m: dead-end streets inside a block shorter than this (CBD lanes mapped as local roads) are lane mouths, not edges
NARROW = 6.0     # m: a longer dead-end street whose buildings stand within this of its line is a lane between buildings, not a street
SHELTER_D, SHELTER_A = 3.0, 120.0  # a SMALL footprint (< 120 m2) this close to a street centreline is a shelter or canopy on the street;
# a house or building on a mapped street that is not on the ground (paper road, path) must stay (15 Nov 2026: 23 of 337 odd blocks)
BLD = []
EDGE_MIN = 5.0   # m of a street along the face edge; a lane that only meets the edge at its mouth does not notch the ring
ROAD_OUT, ROAD_RUN = 3.5, 10   # 3.5 m outside the ring is road or paving: inside a building for over 10 m, there is no street there
MIN_A, MAX_A = 300.0, 60000.0
STEP_LEN, STEP_TURN = 15.0, 20.0   # a jog: a stretch under 15 m between two opposite turns of over 20 degrees
SLIVER = 7.0     # m: a block narrower than 14 m is a sliver between two street lines, not a block
NEAR_D, NEAR_RUN = 6.0, 20   # a drawn kerb under 6 m outside the ring for 20 m: no street between the two blocks
HULL_MIN = 0.85  # area over convex hull: below it the ring is an L, a neck or a wrap round another block
EVID_D, EVID_RUN = 16.0, int(os.environ.get("KG_EVRUN", 40))   # across the street (16 m out) a seen or drawn kerb shows the street is real
NECK, NOTCH, SHAPE_A = 5.0, 6.0, 9.0   # a neck under 10 m wide or a notch or bump under 12 m across, over 15 m2: an odd shape


def samples(g, step=1.0):
    n = max(2, int(g.length / step))
    return shapely.line_interpolate_point(g, np.linspace(0, g.length, n, endpoint=False))


def side_dist(c, face, raw):
    """Median centreline-to-traced-kerb distance on this face's side of street c, or None."""
    r_g, r_t = raw
    inner = face.buffer(-0.5)
    P = samples(c, 2.0); d = []
    for k in r_t.query(c.buffer(12)):
        seg = r_g[int(k)].intersection(inner)
        if seg.is_empty:
            continue
        dd = shapely.distance(P, seg); d += list(dd[(dd > 1.5) & (dd < 12)])
    return float(np.median(d)) if len(d) >= 5 else None


def bearing(g):
    c = np.asarray(g.coords) if g.geom_type == "LineString" else np.asarray(max(g.geoms, key=lambda p: p.length).coords)
    d = c[-1] - c[0]
    return np.degrees(np.arctan2(d[1], d[0])) % 180


def stub(g, face, streets):
    """True when g belongs to a dead-end tree of streets inside the face whose total length is under STUB_MAX."""
    s_g, s_fh, s_t = streets
    inside = [s_g[int(k)] for k in s_t.query(face) if s_g[int(k)].intersection(face.exterior.buffer(0.5)).length < EDGE_MIN
              and s_g[int(k)].intersects(face.buffer(-1))]
    comp, grew = [g], True
    while grew:
        grew = False
        for h in inside:
            if not any(h.equals(c) for c in comp) and any(h.distance(c) < 0.5 for c in comp):
                comp.append(h); grew = True
    if sum(c.length for c in comp) < STUB_MAX:
        return True
    if not BLD:
        return False
    b_g, b_t = BLD[0]
    d = []
    for c in comp:
        P = samples(c, 2.0)
        dd = np.full(len(P), np.inf)
        for k in b_t.query(c.buffer(NARROW)):
            dd = np.minimum(dd, shapely.distance(P, b_g[int(k)]))
        d += list(dd)
    return float(np.median(d)) < NARROW


def ring_for(face, streets, raw):
    """One street side = one kerb distance: segments on the face's edge that run the same way (within SAME_DIR degrees) and are
    the same class share the median measured distance, so a straight side never steps where the street line is split."""
    s_g, s_fh, s_t = streets
    edge = face.exterior.buffer(0.5)
    segs = []
    for k in s_t.query(face):
        part = s_g[int(k)].intersection(edge)
        on_edge = part.length >= EDGE_MIN
        if not on_edge and (s_fh[int(k)] == LANE_FH or not s_g[int(k)].intersects(face) or stub(s_g[int(k)], face, streets)):
            continue
        fh = s_fh[int(k)]
        segs.append([s_g[int(k)], fh, side_dist(s_g[int(k)], face, raw), bearing(part if on_edge else s_g[int(k)])])
    if not segs:
        return [], 0
    for s in segs:
        if True:
            peers = [t[2] for t in segs if t[2] is not None
                     and min(abs(t[3] - s[3]), 180 - abs(t[3] - s[3])) <= SAME_DIR and t[0].distance(s[0]) < 1.0]
            s.append(float(np.median(peers)) if peers else HALF_W.get(s[1], 5.0))
    bands = [g.buffer(hw, cap_style=1) for g, fh, m, b, hw in segs]
    q = face.difference(unary_union(bands)).buffer(-ROUND).buffer(ROUND)
    ps = [p for p in getattr(q, "geoms", [q]) if p.geom_type == "Polygon" and p.area >= MIN_A]
    return ps, sum(s[2] is not None for s in segs) / len(segs)


def jog(q):
    c = np.asarray(q.exterior.simplify(0.75).coords)[:-1]
    n = len(c)
    if n < 4:
        return False
    d = np.roll(c, -1, axis=0) - c
    L = np.hypot(d[:, 0], d[:, 1]); ang = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    turn = (np.roll(ang, -1) - ang + 180) % 360 - 180   # turn at the end of segment i
    for i in range(n):
        if L[i] < STEP_LEN and abs(turn[i - 1]) > STEP_TURN and abs(turn[i]) > STEP_TURN and np.sign(turn[i - 1]) != np.sign(turn[i]):
            return True
    return False


def judge(q, ctx):
    if not (MIN_A <= q.area <= MAX_A):
        return "size"
    if not q.exterior.is_simple:   # a ring that touches itself (pinch between two buffers): kerbreview "self" (18 Nov 2026: 9 of 1,140)
        return "self"
    for alt in (q.buffer(-NECK).buffer(NECK), q.buffer(NOTCH).buffer(-NOTCH)):
        dd = q.symmetric_difference(alt)
        if any(p.area > SHAPE_A for p in getattr(dd, "geoms", [dd])):
            return "shape"
    core = q.buffer(-SLIVER)
    if core.is_empty or core.area < 0.15 * q.area:
        return "sliver"
    if jog(q):
        return "step"
    if q.area / q.convex_hull.area < HULL_MIN:
        return "L shape"
    ring = LineString(q.exterior.coords)
    for k in ctx["drawn"][1].query(q.buffer(DRAWN_D)):
        if ctx["drawn"][0][int(k)].distance(ring) < DRAWN_D or q.contains(ctx["drawn"][0][int(k)]):
            return "drawn"
    for k in ctx["all_st"][1].query(ring):
        g = ctx["all_st"][0][int(k)]
        if g.intersects(ring) and ctx["all_st_fh"][int(k)] != LANE_FH and not (g.length < STUB_MAX and g.difference(q).length < 12):
            return "cross"
    lots, l_t = ctx["lots"]
    near = [lots[int(k)] for k in l_t.query(q)]
    lu = unary_union([g for g in near if g.intersects(q)]) if near else Polygon()
    if lu.is_empty or lu.intersection(q).area / q.area < LOT_SHARE:
        return "few lots"
    P = samples(ring, 1.0)
    deep = np.zeros(len(P), bool)
    for g in near:
        deep |= shapely.contains(g.buffer(-LOT_IN), P)
    run = best = 0
    for v in deep:
        run = run + 1 if v else 0; best = max(best, run)
    if best > LOT_RUN:
        return "lot"
    b_g, b_t = ctx["bld"]
    inb = np.zeros(len(P), bool)
    for k in b_t.query(ring.buffer(BLD_IN + 1)):
        inb |= shapely.contains(b_g[int(k)].buffer(-BLD_IN), P)
    run = best = 0
    for v in np.r_[inb, inb]:
        run = run + 1 if v else 0; best = max(best, run)
    if best > BLD_RUN:
        return "building"
    Po = samples(q.buffer(ROAD_OUT, join_style=2).exterior, 1.0)
    inl = np.zeros(len(Po), bool)
    for k in b_t.query(q.buffer(ROAD_OUT + 1)):
        inl |= shapely.contains(b_g[int(k)], Po)
    run = best = 0
    for v in np.r_[inl, inl]:
        run = run + 1 if v else 0; best = max(best, run)
    if best > ROAD_RUN:
        return "no road"
    op = q.difference(lu).buffer(-OPEN_W)
    if op.area > OPEN_A:
        return "open area"
    r_g, r_t = ctx["raw"]
    dn = np.full(len(P), np.inf)
    for k in r_t.query(q.buffer(AGREE_NEAR)):
        dn = np.minimum(dn, shapely.distance(P, r_g[int(k)]))
    m = dn < AGREE_NEAR
    if m.sum() >= 10 and (dn[m] < AGREE_D).mean() < AGREE_MIN:
        return "disagree"
    nb = np.zeros(len(P), bool)
    d_g, d_t = ctx["drawn"]
    near_out = q.buffer(NEAR_D).difference(q.buffer(0.5))
    for k in d_t.query(near_out):
        part = d_g[int(k)].intersection(near_out)
        if not part.is_empty:
            nb |= shapely.distance(P, part) < NEAR_D
    run = best = 0
    for v in np.r_[nb, nb]:
        run = run + 1 if v else 0; best = max(best, run)
    if best > NEAR_RUN:
        return "no street between"
    ev = np.zeros(len(P), bool)
    ring_out = q.buffer(EVID_D).difference(q.buffer(1.0))
    for src in ("raw", "drawn"):
        g_, t_ = ctx[src]
        for k in t_.query(ring_out):
            part = g_[int(k)].intersection(ring_out)
            if not part.is_empty:
                ev |= shapely.distance(P, part) < EVID_D
    run = best = 0
    for v in np.r_[~ev, ~ev]:
        run = run + 1 if v else 0; best = max(best, run)
    if best > EVID_RUN:
        return "no evidence"
    if ctx["off"] is not None:
        for k in ctx["off"][1].query(q.buffer(6)):
            if ctx["off"][0][int(k)].distance(ring) < 6:
                return "official"
    return None


def read_drawn(d, tr):
    out = []
    for fn in glob.glob(os.path.join(d, "[0-9]*_[0-9]*.json")):
        if fn.endswith("why.json"):
            continue
        for f in json.load(open(fn))["features"]:
            out.append(LineString([tr(*c[:2]) for c in f["geometry"]["coordinates"]]))
    return out


REVIEW = {"SHAPE_A": 40.0, "STEP_TURN": 45.0, "HULL_MIN": 0.6, "LOT_RUN": 1e9, "EVID_RUN": 10 ** 9, "LOT_SHARE": 0.2,
          "AGREE_MIN": 0.4, "SLIVER": 5.0, "OPEN_A": 400.0, "ROAD_RUN": 25, "NEAR_D": 4.0}
# --review (Jacky 15 Nov 2026 chose "double-review every block"): soft gates loosened so more blocks are drafted; every drafted
# block then goes to two independent visual reviewers and only blocks both pass are published. Hard gates stay: drawn, cross,
# building, no road, open area, no street between, official, size.


def road_gate(q, road, sides_measured, class_width_ok=False):
    """Reason a drafted ring fails the road-surface rule, or None. With road-surface data under the ring the surface decides
    (kerbroad.judge_ring); without it every side must be measured from traced kerbs: a class width is a guess."""
    xy = list(q.exterior.coords)
    if road is not None and road.covers(np.asarray(xy)):
        r = krd.judge_ring(road, xy)
        return ("road surface: " + r) if r else None
    if sides_measured < 1.0 and not class_width_ok:
        return "class width, no road surface"
    return None


def main(a):
    if "--review" in a:
        globals().update(REVIEW)
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    i = a.index("--box"); area = box(*map(float, a[i + 1:i + 5]))
    lots = [g for g in kr.load_faces(a[0]) if g.geom_type == "Polygon" and g.intersects(area.buffer(200))]
    roads = [(g, fh) for g, fh in ka.load_roads(a[1]) if g.intersects(area.buffer(400))]
    over = []
    for fn in sorted(glob.glob(os.path.join(a[1], "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            if pr.get("roadontype") in (2, 3) and f.get("geometry"):
                over += [q for q in getattr(shape(f["geometry"]), "geoms", [shape(f["geometry"])]) if q.geom_type == "LineString"]
    ongr = kn.on_ground(roads, over)
    ground = [(g, fh) for g, fh in ongr if fh not in ka.SKIP_FH]
    R = [LineString(t) for t in ka.read_kerbs(a[2]) if len(t) > 1]
    R = [g for g in R if g.intersects(area.buffer(300))]
    D = [g for g in read_drawn(a[3], to) if g.intersects(area.buffer(300))]
    B = []
    for f in json.load(open(a[a.index("--buildings") + 1]))["features"]:
        g = shape(f["geometry"])
        g = Polygon([to(*c[:2]) for c in g.exterior.coords]).buffer(0)
        if g.area > 10 and g.intersects(area.buffer(300)):
            B.append(g)
    ab = STRtree(B)
    for g, fh in ongr:
        if fh in MALL_FH and g.length >= 20:
            zone = g.buffer(20).difference(g.buffer(3))
            sides = [zone.intersection(g.buffer(20, single_sided=True)), zone.intersection(g.buffer(-20, single_sided=True))]
            ok = all(sd.area > 0 and unary_union([B[int(k)] for k in ab.query(sd)] or [Polygon()]).intersection(sd).area / sd.area >= MALL_LOTS for sd in sides)
            if ok:
                ground.append((g, MALL_FH[0]))
    bt = STRtree(B)
    def covered(g):
        u = unary_union([B[int(k)] for k in bt.query(g)] or [Polygon()])
        return g.intersection(u).length > COVERED * g.length
    ground = [(g, fh) for g, fh in ground if not covered(g)]
    st = ground
    gt = STRtree([g for g, fh in ground if fh != LANE_FH])
    B = [b for b in B if b.area >= SHELTER_A or not len(gt.query(b, predicate="dwithin", distance=SHELTER_D))]   # tram stops, canopies
    bt = STRtree(B)
    BLD[:] = [(B, bt)]
    ctx = {"bld": (B, bt), "raw": (R, STRtree(R)), "drawn": (D, STRtree(D)), "lots": (lots, STRtree(lots)),
           "all_st": ([g for g, _ in ground], STRtree([g for g, _ in ground])), "all_st_fh": [fh for _, fh in ground], "off": None}
    if "--official" in a:
        O = [LineString([to(*c[:2]) for c in f["geometry"]["coordinates"]]) for f in json.load(open(a[a.index("--official") + 1]))["features"] if f["geometry"]["type"] == "LineString"]
        ctx["off"] = (O, STRtree(O))
    streets = ([g for g, _ in st], [fh for _, fh in st], STRtree([g for g, _ in st]))
    faces = [f for f in polygonize(unary_union([g for g, _ in st])) if area.contains(f.representative_point())]
    ROAD = krd.Road(a[a.index("--road") + 1], [g for g, fh in ground if fh != LANE_FH]) if "--road" in a else None
    keep, why, cnt = [], [], {}
    for f in faces:
        qs, seen_sides = ring_for(f, streets, ctx["raw"])
        if not qs:
            cnt["no ring"] = cnt.get("no ring", 0) + 1
        for q in qs:
            w = judge(q, ctx) or road_gate(q, ROAD, seen_sides, "--class-width" in a)
            cnt[w or "kept"] = cnt.get(w or "kept", 0) + 1
            (why.append((w, q)) if w else keep.append((q, seen_sides)))
    fc = lambda items, pr: {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": pr(it), "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(*p)] for p in it[1].exterior.coords]}} for it in items]}
    json.dump(fc([(s, q) for q, s in keep], lambda it: {"source": "grid", "sides_measured": round(it[0], 2)}), open(a[4], "w"))
    if "--why" in a:
        json.dump(fc(why, lambda it: {"why": it[0]}), open(a[a.index("--why") + 1], "w"))
    print("RESULT", json.dumps({"faces": len(faces), "count": cnt, "km": round(sum(q.exterior.length for q, _ in keep) / 1000, 2)}))


def selftest():
    f = krd._Fake()
    blk = lambda d: Polygon([(-d, -d), (100 + d, -d), (100 + d, 60 + d), (-d, 60 + d)])
    assert road_gate(blk(0.0), f, 0.0) is None                                   # road surface says the kerb is on the edge: kept, measured or not
    assert road_gate(blk(-3.0), f, 1.0) == "road surface: side behind the verge"  # band 3 m back from the road
    assert road_gate(blk(0.0), None, 0.5) == "class width, no road surface"      # a side at an assumed class width, no road data: refused
    assert road_gate(blk(0.0), None, 1.0) is None                                # every side measured from traced kerbs: kept
    assert road_gate(blk(0.0), None, 0.0, class_width_ok=True) is None           # explicit --class-width
    print("kerbgrid selftest pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main(sys.argv[1:])
