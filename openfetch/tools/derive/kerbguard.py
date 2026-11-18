"""Roof and lane guards for a whole kerb version (Jacky 18 Nov 2026: "make sure we don't make the same mistake"; case P-0165).
About 450 inner-Sydney street-grid rings ran over roofs or along rear lanes; reviewers caught them, but nothing in the version
gate would have. This measures every line of a version against fresh cadastre lots and building footprints so
tools/mirror/kerbs-check.py can refuse the version:
  roof: a line more than BLD_IN m inside a building footprint of BLD_A m2 or more, for over BLD_RUN m;
  lane: a line inside a rear lane or walkway (a reserve strip between lots narrower than LANE_W with no street centreline along
        it) for over LANE_RUN m. A kerb crossing a lane mouth or turning a few metres into it is not a run along it.
Every 1 km square a line touches must have lots, roads and footprints, or the guard fails (no input = not checked).

    python3 kerbguard.py kerbs.geojson[.gz] lots_dir roads_dir buildings_dir out.json [--drop kept.geojson.gz]
    python3 kerbguard.py --selftest
buildings_dir holds kerbgrid-run/bldall.py files <x>_<y>.json (km square numbers, lon/lat footprints).
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
    print("kerbguard selftest pass")
    return 0


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
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    pt = lambda i: [round(v, 6) for v in back(*G[i].interpolate(0.5, normalized=True).coords[0])]
    res = {"check": "openfetch-derive kerbguard.py", "file": os.path.basename(a[0]), "lines": len(G), "cells": len(cells),
           "missing_cells": missing, "roof": len(roof), "lane": len(lane),
           "roof_at": [[pt(i), v] for i, v in sorted(roof.items())][:200], "lane_at": [[pt(i), v] for i, v in sorted(lane.items())][:200],
           "result": "pass" if not (missing or roof or lane) else "fail"}
    json.dump(res, open(a[4], "w"), indent=1)
    print(res["result"], json.dumps({k: res[k] for k in ("lines", "cells", "roof", "lane")}), "missing", len(missing))
    if "--drop" in a:
        bad = set(roof) | set(lane)
        json.dump({"type": "FeatureCollection", "features": [f for i, f in enumerate(F) if i not in bad]}, gzip.open(a[a.index("--drop") + 1], "wt"))
        print("dropped", len(bad), "km", round(sum(G[i].length for i in bad) / 1000, 2))
    return 0 if res["result"] == "pass" else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
