"""Rings across lane mouths (19 Nov 2026, kerb lead, thread "Fill NSW top suburb kerbs, round 4"). A drafted ring whose block has a named
lane (NSW Transport road segment, functionhierarchy 7, operational) running through it and crossing the ring draws the kerb straight
across the lane mouths; drawn kerbs on the ground turn into the lane. On the lead's close-up labels (Chatswood and Redfern, 29 rings):
rejects all 11 odd rings (62-194 m of lane inside, 1-4 crossings) and none of the 16 OK ones; on Marrickville (40) it also rejects 6 of
20 OK rings and misses the 4 rear lanes that have no mapped centreline. Kept anyway: blank beats odd (lead, 19 Nov 2026).
    mouths(ring, lanes) -> (metres of lane inside the ring, number of crossings); bad(...) when 20 m and 1 crossing or more
    python3 kerblane.py rings.geojson roads_dir      lists ring ids that fail (rings.geojson is lon/lat, properties.id)
"""
import glob, json, sys
from shapely.geometry import LineString, Polygon, shape

MIN_IN, MIN_CROSS = 20.0, 1


def mouths(ring, lanes):
    poly = Polygon(ring)
    inside, cross = 0.0, 0
    for g in lanes:
        if not g.intersects(poly):
            continue
        inside += g.intersection(poly).length
        x = g.intersection(ring)
        cross += 0 if x.is_empty else len(getattr(x, "geoms", [x]))
    return inside, cross


def bad(ring, lanes):
    inside, cross = mouths(ring, lanes)
    return inside >= MIN_IN and cross >= MIN_CROSS


def load_lanes(roads_dir):
    out, seen = [], set()
    for fn in glob.glob(roads_dir + "/*.json"):
        for f in json.load(open(fn))["features"]:
            p = f["properties"]
            oid = p.get("OBJECTID", p.get("objectid"))
            if oid in seen or p.get("functionhierarchy") != 7 or p.get("operationalstatus") != 1:
                continue
            seen.add(oid)
            g = shape(f["geometry"])
            out += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
    return out


def selftest():
    ring = LineString([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    lane = LineString([(-10, 50), (110, 50)])
    assert bad(ring, [lane]) and not bad(ring, [LineString([(200, 50), (300, 50)])])
    assert not bad(ring, [LineString([(10, 50), (30, 50)])])   # a lane inside that never reaches the ring
    print("kerblane selftest pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest(); sys.exit(0)
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    lanes = load_lanes(sys.argv[2])
    for f in json.load(open(sys.argv[1]))["features"]:
        r = LineString([to(*c[:2]) for c in f["geometry"]["coordinates"]])
        i, c = mouths(r, lanes)
        if i >= MIN_IN and c >= MIN_CROSS:
            print(f["properties"].get("id"), round(i), c)
