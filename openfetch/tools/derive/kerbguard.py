"""Roof and lane guards for a whole kerb version (Jacky 18 Nov 2026: "make sure we don't make the same mistake"; case P-0165).
About 450 inner-Sydney street-grid rings ran over roofs or along rear lanes; reviewers caught them, but nothing in the version
gate would have. This measures every line of a version against fresh cadastre lots and building footprints so
tools/mirror/kerbs-check.py can refuse the version:
  roof: a line more than BLD_IN m inside a building footprint of BLD_A m2 or more, for over BLD_RUN m;
  lane: a line inside a rear lane or walkway (a reserve strip between lots narrower than LANE_W with no street centreline along
        it) for over LANE_RUN m. A kerb crossing a lane mouth or turning a few metres into it is not a run along it.
Every 1 km square a line touches must have lots, roads and footprints, or the guard fails (no input = not checked).

    python3 kerbguard.py kerbs.geojson[.gz] lots_dir roads_dir buildings_dir out.json --official a.json[,b.json] [--zones zone_dir] [--drop kept.geojson.gz]
    python3 kerbguard.py --selftest
buildings_dir holds kerbgrid-run/bldall.py files <x>_<y>.json (km square numbers, lon/lat footprints).
official: a line runs within OFF_D m of an official council kerb line for OFF_RUN m or more (it doubles the council kerb; 19 Nov
        2026, 102 lines doubled the City of Parramatta kerbs). --official names every council kerb file (lon/lat GeoJSON) for the
        version's area; "--official none" records that no council has kerbs there. kerbs-check.py refuses a guard without this check.
--zones <dir> (or "none" for a place with no NSW zoning, e.g. Victoria; recorded in guards.json) adds the land-use and private-land guards of kerbland.py (zoning cells <x>_<y>.json; kerbs-check refuses a guard without them).
--drop writes the version without the failing lines (whole lines only: a line is kept whole or left out, never cut).
"""
import glob, gzip, json, os, sys
import numpy as np
from shapely.geometry import LineString, Polygon, box, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union

BLD_IN, BLD_RUN, BLD_A = 3.0, 3.0, 120.0
LANE_W, LANE_RUN, CLOSE, LANE_FH = 7.5, 6.0, 0.4, 7
SKIP_FH = {8, 9, 10, 11}
OFF_D, OFF_RUN = 2.5, 25.0
COUNTS = {}   # council kerb lines read from each --official file (guards.json official_lines; kerbs-check refuses a 0)


def is_street(pr):
    """A street centreline: not a path or track, and not a lane unless it is named a street (Kepos St is mapped lane-class)."""
    fh = pr.get("functionhierarchy")
    return fh not in SKIP_FH and (fh != LANE_FH or pr.get("roadnametype") not in (None, "LANE"))


def longest(part):
    if part.is_empty:
        return 0.0
    return max(p.length for p in getattr(part, "geoms", [part]) if hasattr(p, "length"))


def lane_strips(lots, streets, frame):
    """Rear lanes and walkways: reserve strips under LANE_W m wide between lots, with no street centreline along them."""
    land = unary_union([l.buffer(CLOSE) for l in lots]).buffer(-CLOSE)
    res = frame.difference(land)
    narrow = res.difference(res.buffer(-LANE_W / 2).buffer(LANE_W / 2).buffer(0.05)).buffer(-0.1).buffer(0.1)
    out = []
    for p in getattr(narrow, "geoms", [narrow]):
        if p.area <= 5 or p.geom_type != "Polygon":
            continue
        r = np.asarray(p.minimum_rotated_rectangle.exterior.coords)
        ls = max(np.hypot(*(r[1] - r[0])), np.hypot(*(r[2] - r[1])))
        along = sum(g.intersection(p).length for g in streets if g.intersects(p))
        if not (ls > 15 and along > 0.5 * ls):
            out.append(p)
    return out


def check(lines, lots, streets, blds):
    """Indexes of lines over a roof and along a lane, with the run lengths."""
    B = [b for b in blds if b.area >= BLD_A]
    BI = [b.buffer(-BLD_IN) for b in B]
    BT = STRtree(BI)
    roof, lane = [], []
    for i, g in enumerate(lines):
        run = max([longest(g.intersection(BI[int(k)])) for k in BT.query(g)] or [0.0])
        if run > BLD_RUN:
            roof.append((i, round(run, 1)))
    frame = unary_union([g.envelope for g in lines]).buffer(60) if lines else Polygon()
    L = lane_strips(lots, streets, frame.envelope) if lines else []
    LI = [p.buffer(-0.3) for p in L]
    LT = STRtree(LI)
    for i, g in enumerate(lines):
        run = max([longest(g.intersection(LI[int(k)])) for k in LT.query(g)] or [0.0])
        if run > LANE_RUN:
            lane.append((i, round(run, 1)))
    return roof, lane


def selftest():
    """Two blocks with a 5 m rear lane between them and a 20 m street to the south; a roof on the north block."""
    lots = [box(0, 20, 100, 60), box(0, 65, 100, 105), box(0, -60, 100, 0)]
    streets = [LineString([(-50, 10), (150, 10)])]
    blds = [box(10, 30, 40, 58)]
    good = LineString([(-3, 17), (103, 17)])                    # street kerb 3 m off the lot front
    mouth = LineString([(-3, 17), (5, 17), (5, 21), (2, 23)])   # turns a few metres into a lane mouth: allowed
    over = LineString([(5, 40), (50, 40)])                      # across a house
    along = LineString([(5, 62.5), (95, 62.5)])                 # down the rear lane
    roof, lane = check([good, mouth, over, along], lots, streets, blds)
    assert [i for i, _ in roof] == [2], roof
    assert [i for i, _ in lane] == [3], lane
    import tempfile
    fn = os.path.join(tempfile.mkdtemp(), "council.json")
    json.dump({"features": [{"geometry": {"type": "LineString", "coordinates": [[-3, 18.5], [103, 18.5]]}}]}, open(fn, "w"))
    off, names = doubled([good, mouth, over], fn, lambda x, y: (x, y))   # good runs 1.5 m beside the council kerb: doubled
    assert list(off) == [0] and names == ["council.json"], off
    json.dump({"features": []}, open(fn, "w"))
    try:
        doubled([good], fn, lambda x, y: (x, y)); raise AssertionError("empty council file passed")
    except SystemExit:
        pass
    assert doubled([good], None, None) == ({}, None) and doubled([good], "none", None) == ({}, [])
    print("kerbguard selftest pass")
    return 0


def doubled(G, files, to):
    """Lines running OFF_RUN m or more within OFF_D m of an official council kerb: {line index: metres}; (None) when not asked."""
    if files is None:
        return {}, None
    names = [] if files == "none" else files.split(",")
    O = []; empty = []
    for fn in names:
        n0 = len(O)
        for f in json.load(open(fn))["features"]:
            g = f.get("geometry") or {}
            for c in ([g.get("coordinates")] if g.get("type") == "LineString" else g.get("coordinates") or [] if g.get("type") == "MultiLineString" else []):
                if c and len(c) > 1:
                    O.append(LineString([to(*p[:2]) for p in c]))
        COUNTS[os.path.basename(fn)] = len(O) - n0
        if len(O) == n0:
            empty.append(os.path.basename(fn))
    if empty:
        raise SystemExit("official council kerb file has no lines (a failed fetch is not 'no kerbs'; use --official none only for a place with no council kerbs): " + ", ".join(empty))
    if not O:
        return {}, [os.path.basename(n) for n in names]
    OT = STRtree(O); out = {}
    for i, g in enumerate(G):
        near = OT.query(g.buffer(OFF_D))
        if len(near):
            run = g.intersection(unary_union([O[int(k)].buffer(OFF_D) for k in near])).length
            if run >= OFF_RUN:
                out[i] = round(run, 1)
    return out, [os.path.basename(n) for n in names]


def landuse(G, zdir, lots, cells):
    """Land-use and private-land guards (kerbland.py, case P-0197): zdir holds <x>_<y>.json zoning cells next to the lots and roads cells.
    A cell with no zoning file fails the version (no input is not 'nothing there')."""
    import kerbland
    seen, polys, absent = set(), [], []
    for (x, y) in sorted(cells):
        fn = os.path.join(zdir, f"{x * 1000}_{y * 1000}.json")
        if not os.path.exists(fn):
            absent.append(fn); continue
        for f in json.load(open(fn))["features"]:
            oid = (f.get("properties") or {}).get("OBJECTID")
            if oid in seen or not f.get("geometry") or not kerbland.zone_blocks(f["properties"]):
                continue
            seen.add(oid)
            g = shape(f["geometry"])
            polys += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]
    if absent:
        raise SystemExit("no zoning file for: " + ", ".join(absent[:5]))
    return kerbland.land_bad(G, polys), kerbland.lot_bad(G, lots)


def main(a):
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    op = gzip.open if a[0].endswith(".gz") else open
    F = json.load(op(a[0], "rt"))["features"]
    G = [LineString([to(*c[:2]) for c in f["geometry"]["coordinates"]]) for f in F]
    cells = {}
    for i, g in enumerate(G):
        x0, y0, x1, y1 = g.bounds
        for x in range(int(x0 // 1000), int(x1 // 1000) + 1):
            for y in range(int(y0 // 1000), int(y1 // 1000) + 1):
                cells.setdefault((x, y), []).append(i)
    missing, roof, lane = [], {}, {}
    alllots = {}
    for (x, y), idx in sorted(cells.items()):
        n = f"{x * 1000}_{y * 1000}"
        paths = [os.path.join(a[1], n + ".json"), os.path.join(a[2], n + ".json"), os.path.join(a[3], f"{x}_{y}.json")]
        if not all(os.path.exists(p) for p in paths):
            missing.append(n); continue
        cell = box(x * 1000, y * 1000, x * 1000 + 1000, y * 1000 + 1000)
        lots = [shape(f["geometry"]) for f in json.load(open(paths[0]))["features"] if f.get("geometry")]
        lots = [q for g in lots for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]
        st = [shape(f["geometry"]) for f in json.load(open(paths[1]))["features"] if f.get("geometry") and is_street(f.get("properties") or {})]
        st = [q for g in st for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
        for q in lots:
            alllots[q.wkb] = q
        bl = []
        for f in json.load(open(paths[2]))["features"]:
            p = Polygon([to(*c[:2]) for c in f["geometry"]["coordinates"][0]]).buffer(0)
            if p.area >= BLD_A:
                bl.append(p)
        parts = [G[i].intersection(cell) for i in idx]
        r, l = check(parts, lots, st, bl)
        for k, run in r:
            roof[idx[k]] = max(run, roof.get(idx[k], 0))
        for k, run in l:
            lane[idx[k]] = max(run, lane.get(idx[k], 0))
    land, lotin, zdir = {}, {}, a[a.index("--zones") + 1] if "--zones" in a else None
    if zdir and zdir != "none":
        land, lotin = landuse(G, zdir, list(alllots.values()), cells)
    off, offn = doubled(G, a[a.index("--official") + 1] if "--official" in a else None, to)
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    pt = lambda i: [round(v, 6) for v in back(*G[i].interpolate(0.5, normalized=True).coords[0])]
    res = {"check": "openfetch-derive kerbguard.py", "file": os.path.basename(a[0]), "lines": len(G), "cells": len(cells),
           "missing_cells": missing, "roof": len(roof), "lane": len(lane),
           "roof_at": [[pt(i), v] for i, v in sorted(roof.items())][:200], "lane_at": [[pt(i), v] for i, v in sorted(lane.items())][:200],
           "zones": zdir, "land": len(land) if zdir else None, "lot": len(lotin) if zdir else None,
           "land_at": [[pt(i), v] for i, v in sorted(land.items())][:200], "lot_at": [[pt(i), v] for i, v in sorted(lotin.items())][:200],
           "official_files": offn, "official_lines": COUNTS, "official": len(off) if offn is not None else None,
           "official_at": [[pt(i), v] for i, v in sorted(off.items())][:200],
           "result": "pass" if not (missing or roof or lane or off or offn is None or land or lotin or not zdir) else "fail"}
    json.dump(res, open(a[4], "w"), indent=1)
    print(res["result"], json.dumps({k: res[k] for k in ("lines", "cells", "roof", "lane", "official", "land", "lot")}), "missing", len(missing))
    if "--drop" in a:
        bad = set(roof) | set(lane) | set(off) | set(land) | set(lotin)
        json.dump({"type": "FeatureCollection", "features": [f for i, f in enumerate(F) if i not in bad]}, gzip.open(a[a.index("--drop") + 1], "wt"))
        print("dropped", len(bad), "km", round(sum(G[i].length for i in bad) / 1000, 2))
    return 0 if res["result"] == "pass" else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
