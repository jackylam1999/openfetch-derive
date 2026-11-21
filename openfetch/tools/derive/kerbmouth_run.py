"""Cut refused kerb rings at their lane mouths and judge each street side (KN21, 20 Nov 2026, kerb lead 4, case P-0240).
A ring that crossed a mapped rear lane was dropped whole (P-0233); Jacky 20 Nov 15:30Z: cut, do not drop. Each ring goes through
kerbmouth.cut_ring (cut at every lane mouth, a quarter-circle kerb return into the lane at each cut end); each side then passes
  face    kerbface: the strip out to the nearest street is road reserve for all but FACE_RUN m
  wide    kerbface: not more than WIDE_RUN m sits WIDE_EXTRA m beyond the carriageway the street's lane count implies
  notch   kerbface: no hook into a street mouth beside it
  road    kerbroad, only where a LiDAR intensity grid exists: road edge seen, within 3 m (the 20 Nov 2D bar) of the kerb
and afterwards kerbguard.py (roof, lane, land use, private lot, council doubling) on the kept sides, as for any version.
    python3 kerbmouth_run.py rings.geojson in_dir out.geojson [--grids dir] [--wide-loose] [--funnel funnel.json] [--lanes flush-lanes.geojson (kerblot --flush-lanes)]
rings.geojson: lon/lat closed rings, properties.id; in_dir: roads/ lots/ cad/ (the cells kerbguard.py also reads).
out.geojson: every side as a LineString (lon/lat) with properties ring, side, ring_m, why ([] = kept), road ("no grid" where none).
"""
import collections, glob, json, sys
import shapely
import numpy as np
from shapely.geometry import LineString, Polygon, shape
from pyproj import Transformer

import kerbaudit as ka, kerbcad as kc, kerbface as kf, kerblot as kl, kerbmouth as km, kerbnet as kn, kerbregular as kr, kerbroad as krd

AGREE_2D = 3.0      # m: the 20 Nov bar (up to about 3 m off is fine); parked-car rows and a line just behind the verge are not refused
WIDE_LOOSE = 8.0    # m beyond the carriageway edge: with --wide-loose a side is 'wide' only past this AND with no road reserve between it and the street (lead, 20 Nov)
INROAD_OFF = 1.01   # the in-the-roadway share test is off for the same reason; a side 3 m or more inside the road still fails AGREE_2D


def load_roads(roads_dir):
    lanes, streets, allroads, over, seen = [], [], [], [], set()
    for fn in sorted(glob.glob(roads_dir + "/*.json")):
        for f in json.load(open(fn))["features"]:
            p = f["properties"]
            oid = p.get("OBJECTID", p.get("objectid"))
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if p.get("roadontype") in (2, 3):
                over += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
            if oid in seen:
                continue
            seen.add(oid)
            for q in getattr(g, "geoms", [g]):
                if q.geom_type != "LineString" or not q.length:
                    continue
                fh = p.get("functionhierarchy")
                allroads.append((q, fh))
                if p.get("operationalstatus") != 1:
                    continue
                if fh == 7:
                    lanes.append((q, p.get("lanecount")))
                elif fh not in ka.SKIP_FH:
                    streets.append((q, p.get("lanecount"), fh))
    return lanes, streets, allroads, over


def face_flags(ring_xy, ctx):
    """(distance along ring, face bad, wide) per 2 m sample, and the polygon (kerbface.check's per-sample tests)."""
    poly, pts = kf.samples(ring_xy)
    inner, line, out = poly.buffer(-0.8), LineString(ring_xy), []
    for p, nrm in pts:
        best = None
        for j in ctx["st_t"].query(p.buffer(kf.FACE_MAX)):
            g, lc, fh = ctx["streets"][int(j)]
            q = g.interpolate(g.project(p)); d = p.distance(q)
            if best is not None and d >= best[0]:
                continue
            seg = LineString([(p.x, p.y), (q.x, q.y)])
            if d > 0.5 and inner.intersects(seg):
                continue
            best = (d, q, lc, seg)
        if best is None:
            out.append((line.project(p), True, False, False)); continue
        d, q, lc, seg = best
        n = max(2, int(d))
        P = np.array([seg.interpolate(i / n, normalized=True).coords[0] for i in range(1, n)]) if d > 2 else np.zeros((0, 2))
        bad = bool(len(P) and (ctx["cad"].label(P) != "road").sum() > max(2, 0.2 * len(P)))
        half = max(1, lc or 2) * kf.LANE_W / 2
        out.append((line.project(p), bad, d > half + kf.PARK_W + kf.WIDE_EXTRA, d > half + WIDE_LOOSE and bad))
    return poly, out


def judge_sides(ring_xy, cut, ctx, road, loose=False):
    """cut = kerbmouth.cut_ring result; returns [dict(side, ring_m, xy, why, road)] with why [] for a kept side."""
    ring = LineString(ring_xy)
    poly, flags = face_flags(ring_xy, ctx)
    pockets = poly.buffer(kf.NOTCH_R, join_style=1).buffer(-kf.NOTCH_R, join_style=1).difference(poly)
    pockets = [q for q in getattr(pockets, "geoms", [pockets]) if q.area >= kf.NOTCH_A]
    sign = 1 if Polygon(ring_xy).exterior.is_ccw else -1
    res = []
    for si, sd in enumerate(cut["sides"]):
        lo, hi = sd["lo"] % ring.length, sd["hi"] % ring.length
        inside = (lambda s: lo <= s <= hi) if lo <= hi else (lambda s: s >= lo or s <= hi)
        fl = [(f, w[1] if loose else w[0]) for s, f, *w in flags if inside(s)]
        why = []
        if kf.run_len([f for f, w in fl]) >= kf.FACE_RUN: why.append("face")
        if kf.run_len([w for f, w in fl]) >= kf.WIDE_RUN: why.append("wide")
        piece = LineString(sd["ring"])
        if max([q.area for q in pockets if q.distance(piece) < 1.5] or [0]) >= kf.NOTCH_A: why.append("notch")
        P = np.asarray(sd["ring"], float)
        rd = None
        if road is not None and road.covers(P):
            rd = krd.judge_ring(road, P, area_sign=sign, agree=AGREE_2D, inroad=INROAD_OFF)
            if rd: why.append("road: " + rd)
        res.append(dict(side=si, ring_m=round(sd["ring_m"], 1), xy=sd["xy"], why=why, road=rd if road is not None and road.covers(P) else "no grid"))
    return res


def side_cuts(feats, out, funnel, to, back):
    """kerblot H7_CUT: an unmeasured side whose cuts both land on a real end is left out of every piece of its ring."""
    Z = {}
    for f in feats:
        dd = f["properties"].get("d") or {}
        dd = json.loads(dd) if isinstance(dd, str) else dd
        if dd.get("_cut"):
            Z[f["properties"].get("id")] = shapely.union_all([Polygon(c) for c in dd["_cut"]])
    res = []
    for o in out:
        z = Z.get(o["properties"]["ring"])
        if z is None or o["properties"]["why"]:
            res.append(o); continue
        g = LineString([to(*c[:2]) for c in o["geometry"]["coordinates"]]).difference(z)
        funnel["pieces side-cut"] += 1
        for i, q in enumerate(q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString" and q.length >= km.MIN_SIDE):
            p = dict(o["properties"], side=f'{o["properties"]["side"]}c{i}', ring_m=round(q.length, 1))
            res.append({"type": "Feature", "properties": p, "geometry": {"type": "LineString", "coordinates": [list(back(*c)) for c in q.coords]}})
    return res


def main(a):
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    d = a[1]
    lanes, streets, allroads, over = load_roads(d + "/roads")
    if "--lanes" in a:   # narrow streets kerblot --flush-lanes handled as lanes (scenario 16): cut at their mouths too, not streets
        extra = [LineString([to(*c[:2]) for c in f["geometry"]["coordinates"]]) for f in json.load(open(a[a.index("--lanes") + 1]))["features"]]
        lanes += [(g, 1) for g in extra]
        streets = [s for s in streets if not any(s[0].equals_exact(g, 0.01) for g in extra)]
    lots = [g for g in kr.load_faces(d + "/lots") if g.geom_type == "Polygon"]
    lots, road_lots = kl.drop_road_lots(lots, [g for g, _, _ in streets])
    ctx = kf.context(streets, kc.Cad(d + "/cad", road_lots), lots, [])
    road = None
    if "--grids" in a:
        ground = [(g, fh) for g, fh in kn.on_ground(allroads, over) if fh not in ka.SKIP_FH]
        road = krd.Road(a[a.index("--grids") + 1], [g for g, fh in ground if fh != 7])
    feats, out, funnel = json.load(open(a[0]))["features"], [], collections.Counter()
    for f in feats:
        xy = [to(*c[:2]) for c in f["geometry"]["coordinates"]]
        cut = km.cut_ring(xy, lanes)
        funnel["rings"] += 1
        if cut.get("whole"):
            funnel["whole rings (no lane crossing)"] += 1
            out.append({"type": "Feature", "properties": {"ring": f["properties"].get("id"), "side": "whole", "ring_m": round(LineString(xy).length, 1), "why": [], "road": "kept as drawn"},
                        "geometry": f["geometry"]}); continue
        if not cut["sides"]:
            funnel["ring: " + (cut["why"][0] if cut["why"] else "no sides")] += 1; continue
        for s in judge_sides(xy, cut, ctx, road, "--wide-loose" in a):
            funnel["sides"] += 1; funnel["m_all"] += s["ring_m"]
            k = "kept" if not s["why"] else "refused: " + " + ".join(w.split(":")[0] for w in s["why"])
            funnel[k] += 1; funnel["m " + k] += s["ring_m"]
            out.append({"type": "Feature", "properties": {"ring": f["properties"].get("id"), "side": s["side"], "ring_m": s["ring_m"], "why": s["why"], "road": s["road"]},
                        "geometry": {"type": "LineString", "coordinates": [list(back(*p)) for p in s["xy"]]}})
    out = side_cuts(feats, out, funnel, to, back)
    json.dump({"type": "FeatureCollection", "features": out}, open(a[2], "w"))
    if "--funnel" in a: json.dump(dict(funnel), open(a[a.index("--funnel") + 1], "w"), indent=1)
    print(json.dumps(dict(funnel)))


if __name__ == "__main__":
    main(sys.argv[1:])
