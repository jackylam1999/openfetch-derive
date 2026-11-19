"""Does every side of a drafted ring face a street it can be the kerb of? (KN5 round 2, 19 Nov 2026, lead G2 on 40 outer-suburb rings:
5 odd, 1 unsure.) Three whole-ring tests on finished rings (a ring is kept or blank, never cut):
  a  face:  from every ring point (2 m apart) look out to the nearest street centreline that lies outside the ring. The strip
            between them must be road reserve in the cadastre (road corridor or a street lot). A run of FACE_RUN m or more where
            the strip crosses a lot, plaza, mall or open land, or no street lies within FACE_MAX m, is not a kerb.
  b  mouth: a ring that turns into the mouth of an unnamed access road, car-park entry or lane (a notch pushed in from the ring
            into the street reserve): see mouths().
  c  wide:  where the ring sits more than WIDE_EXTRA m beyond the carriageway edge the street's lane count implies (half of
            LANE_W per lane plus PARK_W for parking and gutter), for a run of WIDE_RUN m, the side was placed from a trace or a
            borrowed width that put it on the verge or in the roadway.
    check(ring_xy, ctx) -> {"face": m, "wide": m, "mouth": n}  (longest bad runs, metres / count)
    python3 kerbface.py rings.geojson lots_dir roads_dir(with lanecount) cad_dir out.json [--drop kept.geojson]   (rings lon/lat, whole rings kept or dropped)
    python3 kerbface.py --selftest
ring_xy is a list of (x, y) metres (MGA 56). ctx = context(streets, cad, lots, zones): streets = [(LineString, lanecount, fh)].
"""
import sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

STEP = 2.0
FACE_MAX = 30.0     # m: no street centreline this close (outside the ring) = faces no street
FACE_RUN = 10.0     # m of ring whose look-out strip is not road reserve
LANE_W, PARK_W = 3.3, 3.0
WIDE_EXTRA, WIDE_RUN = 3.0, 4.0
NOTCH_R, NOTCH_A = 8.0, 16.0   # m, m2: closing the ring by NOTCH_R fills a pocket of this area or more = a hook into a mouth


def context(streets, cad, lots, zones):
    return {"streets": streets, "st_t": STRtree([g for g, _, _ in streets]), "cad": cad, "lots": lots, "lot_t": STRtree(lots), "zones": zones,
            "zone_t": STRtree(zones) if zones else None}


def samples(ring):
    line = LineString(ring)
    poly = Polygon(ring)
    n = max(2, int(line.length // STEP))
    out = []
    for k in range(n):
        d = k * line.length / n
        p, q = line.interpolate(d), line.interpolate(min(line.length, d + 0.5))
        t = np.array([q.x - p.x, q.y - p.y])
        if not t.any():
            continue
        t /= np.linalg.norm(t)
        nrm = np.array([-t[1], t[0]])
        if poly.contains(Point(p.x + nrm[0], p.y + nrm[1])):
            nrm = -nrm
        out.append((p, nrm))
    return poly, out


def run_len(flags):
    best = cur = 0
    for f in flags:
        cur = cur + STEP if f else 0
        best = max(best, cur)
    return best


def check(ring, ctx):
    poly, pts = samples(ring)
    inner = poly.buffer(-0.8)
    cad = ctx["cad"]
    face, wide = [], []
    for p, nrm in pts:
        best = None
        for j in ctx["st_t"].query(p.buffer(FACE_MAX)):
            g, lanes, fh = ctx["streets"][int(j)]
            q = g.interpolate(g.project(p))
            d = p.distance(q)
            if best is not None and d >= best[0]:
                continue
            seg = LineString([(p.x, p.y), (q.x, q.y)])
            if d > 0.5 and inner.intersects(seg):
                continue
            best = (d, q, lanes, seg)
        if best is None:
            face.append(True); wide.append(False)
            continue
        d, q, lanes, seg = best
        n = max(2, int(d))
        P = np.array([seg.interpolate(i / n, normalized=True).coords[0] for i in range(1, n)]) if d > 2 else np.zeros((0, 2))
        bad = False
        if len(P):
            lab = cad.label(P)
            bad = (lab != "road").sum() > max(2, 0.2 * len(P))
        face.append(bool(bad))
        want = max(1, lanes or 2) * LANE_W / 2 + PARK_W
        wide.append(d > want + WIDE_EXTRA)
    fr, wr = run_len(face), run_len(wide)
    return {"face": fr, "wide": wr, "notch": round(notch(poly), 1)}


def notch(poly):
    """m2 of pockets narrower than 2 x NOTCH_R pushed into the ring (a hook into an access road, car-park entry or lane mouth)."""
    return poly.buffer(NOTCH_R, join_style=1).buffer(-NOTCH_R, join_style=1).difference(poly).area


def bad(res):
    return res["face"] >= FACE_RUN or res["wide"] >= WIDE_RUN or res["notch"] >= NOTCH_A


def selftest():
    class Cad:
        def label(self, P):
            return np.array(["road" if (p[1] < 10 or p[1] > 31 or p[0] < -1 or p[0] > 101) else "other" for p in P], dtype=object)
    ctx = context([(LineString([(-100, 0), (200, 0)]), 2, 5), (LineString([(-100, 41), (200, 41)]), 2, 5),
                   (LineString([(-6, -50), (-6, 90)]), 2, 5), (LineString([(106, -50), (106, 90)]), 2, 5)], Cad(), [], [])
    ok = [(0, 9), (100, 9), (100, 32), (0, 32), (0, 9)]
    r = check(ok, ctx)
    assert r["face"] < FACE_RUN and r["wide"] < WIDE_RUN, r
    far = [(0, 14), (100, 14), (100, 27), (0, 27), (0, 14)]
    ctx2 = context([(LineString([(-100, 0), (200, 0)]), 2, 5), (LineString([(-100, 41), (200, 41)]), 2, 5)], Cad(), [], [])
    assert check(far, ctx2)["wide"] >= WIDE_RUN
    blind = [(0, 12), (100, 12), (100, 30), (0, 30), (0, 12)]

    class Cad2(Cad):
        def label(self, P):
            return np.array(["other"] * len(P), dtype=object)
    assert check(blind, context([(LineString([(-100, 0), (200, 0)]), 2, 5), (LineString([(-100, 41), (200, 41)]), 2, 5)], Cad2(), [], []))["face"] >= FACE_RUN
    hook = [(0, 9), (50, 9), (50, 20), (52, 20), (52, 9), (100, 9), (100, 32), (0, 32), (0, 9)]
    assert notch(Polygon(hook)) >= NOTCH_A and notch(Polygon(ok)) < 1
    print("kerbface selftest pass")


def main(a):
    import glob, json
    from shapely.geometry import shape
    from pyproj import Transformer
    import kerbaudit as ka, kerbcad as kc, kerblot as kl, kerbregular as kr
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    lots = [g for g in kr.load_faces(a[1]) if g.geom_type == "Polygon"]
    streets, seen = [], set()
    for fn in sorted(glob.glob(a[2] + "/*.json")):
        for f in json.load(open(fn))["features"]:
            p = f["properties"]
            o = p.get("OBJECTID", p.get("objectid"))
            fh = p.get("functionhierarchy")
            if o in seen or not f.get("geometry") or fh in ka.SKIP_FH or fh == 7 or p.get("operationalstatus") != 1:
                continue
            seen.add(o)
            g = shape(f["geometry"])
            streets += [(q, p.get("lanecount"), fh) for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString" and q.length > 0]
    lots, road_lots = kl.drop_road_lots(lots, [g for g, _, _ in streets])
    ctx = context(streets, kc.Cad(a[3], road_lots), lots, [])
    feats = json.load(open(a[0]))["features"]
    res = {f["properties"]["id"]: check([to(*c) for c in f["geometry"]["coordinates"]], ctx) for f in feats}
    json.dump(res, open(a[4], "w"))
    failed = [b for b, r in res.items() if bad(r)]
    print("rings", len(res), "fail", len(failed))
    if "--drop" in a:
        json.dump({"type": "FeatureCollection", "features": [f for f in feats if f["properties"]["id"] not in set(failed)]}, open(a[a.index("--drop") + 1], "w"))


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main(sys.argv[1:])
