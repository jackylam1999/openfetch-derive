"""Grid kerbs (Jacky 15 Nov 2026: "many of the box look like a grid ... just continue down"). For a street block with NO gap kerb
drawn yet: the block face between ground street centrelines, minus each street's band (centreline +- the kerb distance measured
from the traced kerbs on that same side), corners rounded. Kept whole or left blank. Lessons kept from the 6-7 Nov centreline
loops (kerbnet.py): never replace a drawn kerb (only blank blocks), lanes and tunnels/bridges never shape a block, no open ends.

TRIED 15 Nov 2026 on the CBD (333-335 x 6249-6252), NOT PUBLISHED: where both exist the street-offset ring sat within 1 m of our
measured kerb 85 % of the time, but on the blocks still blank an independent reviewer found 11 odd of 39 (round 1) and 11 odd of 26
(round 2, with shape and no-road gates): blocks left blank are mostly where the street map does not match the ground (centrelines
along rail, freeway ramps, private ways, lots misaligned), so the street grid there is not a safe guide.

    python3 kerbgrid.py lots_dir roads_dir raw.json drawn_dir out.json --box x0 y0 x1 y1 [--why why.json] [--official o.json]
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

HALF_W = {1: 9.0, 2: 8.0, 3: 7.0, 4: 6.5, 5: 5.5, 6: 4.5, 7: 3.0}
LANE_FH = 7
ROUND = 4.0          # m corner radius
LOT_IN, LOT_RUN = 2.0, float(os.environ.get("KG_LOTRUN", 3.0))
AGREE_NEAR, AGREE_D, AGREE_MIN = 6.0, 2.5, 0.7   # where a traced kerb lies within 6 m, it must be within 2.5 m on 70 % of it
OPEN_W, OPEN_A = 4.5, 40.0   # an open area (no lot) over 9 m wide inside the ring: plaza, mall or a street missing from the map
LOT_SHARE = 0.5
DRAWN_D = 3.0
SAME_DIR = 12.0
ROAD_OUT, ROAD_RUN = 3.5, 15   # 3.5 m outside the ring is road: inside a lot for over 15 m, the "street" there is not a road
MIN_A, MAX_A = 300.0, 60000.0
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


def ring_for(face, streets, raw):
    """One street side = one kerb distance: segments on the face's edge that run the same way (within SAME_DIR degrees) and are
    the same class share the median measured distance, so a straight side never steps where the street line is split."""
    s_g, s_fh, s_t = streets
    edge = face.exterior.buffer(0.5)
    segs = []
    for k in s_t.query(face):
        part = s_g[int(k)].intersection(edge)
        on_edge = part.length >= 1
        if not on_edge and (s_fh[int(k)] == LANE_FH or not s_g[int(k)].intersects(face)):
            continue
        fh = s_fh[int(k)]
        segs.append([s_g[int(k)], fh, side_dist(s_g[int(k)], face, raw), bearing(part if on_edge else s_g[int(k)])])
    if not segs:
        return [], 0
    for s in segs:
        if s[2] is not None:
            s.append(s[2])
        else:
            peers = [t[2] for t in segs if t[2] is not None and HALF_W.get(t[1]) == HALF_W.get(s[1])
                     and min(abs(t[3] - s[3]), 180 - abs(t[3] - s[3])) <= SAME_DIR and t[0].distance(s[0]) < 1.0]
            s.append(float(np.median(peers)) if peers else HALF_W.get(s[1], 5.0))
    bands = [g.buffer(hw, cap_style=1) for g, fh, m, b, hw in segs]
    q = face.difference(unary_union(bands)).buffer(-ROUND).buffer(ROUND)
    ps = [p for p in getattr(q, "geoms", [q]) if p.geom_type == "Polygon" and p.area >= MIN_A]
    return ps, sum(s[2] is not None for s in segs) / len(segs)


def judge(q, ctx):
    if not (MIN_A <= q.area <= MAX_A):
        return "size"
    for alt in (q.buffer(-NECK).buffer(NECK), q.buffer(NOTCH).buffer(-NOTCH)):
        dd = q.symmetric_difference(alt)
        if any(p.area > SHAPE_A for p in getattr(dd, "geoms", [dd])):
            return "shape"
    ring = LineString(q.exterior.coords)
    for k in ctx["drawn"][1].query(q.buffer(DRAWN_D)):
        if ctx["drawn"][0][int(k)].distance(ring) < DRAWN_D or q.contains(ctx["drawn"][0][int(k)]):
            return "drawn"
    for k in ctx["all_st"][1].query(ring):
        if ctx["all_st"][0][int(k)].intersects(ring) and ctx["all_st_fh"][int(k)] != LANE_FH:
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
    Po = samples(q.buffer(ROAD_OUT, join_style=2).exterior, 1.0)
    inl = np.zeros(len(Po), bool)
    for k in l_t.query(q.buffer(ROAD_OUT + 1)):
        inl |= shapely.contains(lots[int(k)], Po)
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


def main(a):
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
    ground = [(g, fh) for g, fh in kn.on_ground(roads, over) if fh not in ka.SKIP_FH]
    st = ground
    R = [LineString(t) for t in ka.read_kerbs(a[2]) if len(t) > 1]
    R = [g for g in R if g.intersects(area.buffer(300))]
    D = [g for g in read_drawn(a[3], to) if g.intersects(area.buffer(300))]
    ctx = {"raw": (R, STRtree(R)), "drawn": (D, STRtree(D)), "lots": (lots, STRtree(lots)),
           "all_st": ([g for g, _ in ground], STRtree([g for g, _ in ground])), "all_st_fh": [fh for _, fh in ground], "off": None}
    if "--official" in a:
        O = [LineString([to(*c[:2]) for c in f["geometry"]["coordinates"]]) for f in json.load(open(a[a.index("--official") + 1]))["features"] if f["geometry"]["type"] == "LineString"]
        ctx["off"] = (O, STRtree(O))
    streets = ([g for g, _ in st], [fh for _, fh in st], STRtree([g for g, _ in st]))
    faces = [f for f in polygonize(unary_union([g for g, _ in st])) if area.contains(f.representative_point())]
    keep, why, cnt = [], [], {}
    for f in faces:
        qs, seen_sides = ring_for(f, streets, ctx["raw"])
        if not qs:
            cnt["no ring"] = cnt.get("no ring", 0) + 1
        for q in qs:
            w = judge(q, ctx)
            cnt[w or "kept"] = cnt.get(w or "kept", 0) + 1
            (why.append((w, q)) if w else keep.append((q, seen_sides)))
    fc = lambda items, pr: {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": pr(it), "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(*p)] for p in it[1].exterior.coords]}} for it in items]}
    json.dump(fc([(s, q) for q, s in keep], lambda it: {"source": "grid", "sides_measured": round(it[0], 2)}), open(a[4], "w"))
    if "--why" in a:
        json.dump(fc(why, lambda it: {"why": it[0]}), open(a[a.index("--why") + 1], "w"))
    print("RESULT", json.dumps({"faces": len(faces), "count": cnt, "km": round(sum(q.exterior.length for q, _ in keep) / 1000, 2)}))


if __name__ == "__main__":
    main(sys.argv[1:])
