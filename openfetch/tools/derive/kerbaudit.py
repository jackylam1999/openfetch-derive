"""Kerb completeness audit: finds every street corner that should have a kerb and checks it is closed, so nobody has to look at
every line by eye (Jacky 6 Nov 2026: "I can't proof check every single line when we scale it up").

Rule: at every road junction (3 or more centrelines meet), each gap between two neighbouring roads that has a property on the
bisector within 40 m is a block corner. If kerbs were traced along both roads near the junction, a closed corner must cross the
bisector between the junction and the property. When nothing crosses it, the corner is open.

    python3 kerbaudit.py kerbs.json(lon/lat GeoJSON) lots_dir roads_dir out.json [--epsg 7856]

out.json: {"corners", "covered", "open", "open_pct", "points": [[x, y], ...] (open corners, in the projected CRS)}.
"""
import json
import sys

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

import kerbregular as kr

LOT_REACH = 40.0   # m, a property this close along the bisector makes the gap a block corner
ARM_REACH = 30.0   # m, both roads must have a kerb this close to the junction on the corner's side (else not traced here)


def junctions(roads, snap=0.5):
    ends = {}
    for g in roads:
        c = np.asarray(g.coords)
        if len(c) < 2:
            continue
        for p, q in ((c[0], c[1:]), (c[-1], c[-2::-1])):
            k = tuple(np.round(p / snap).astype(int))
            # heading out of the junction, from the first 15 m of the road
            L = LineString(np.r_[[p], q]); t = np.asarray(L.interpolate(min(15.0, L.length)).coords[0]) - p
            n = np.hypot(*t)
            if n > 1e-6:
                ends.setdefault(k, []).append((p, t / n))
    return [(v[0][0], [u for _, u in v]) for v in ends.values() if len(v) >= 3]


def audit(kerbs, lots, roads):
    K = [LineString(k) for k in kerbs if len(k) > 1]
    kt = STRtree(K)
    lt = STRtree(lots)
    corners = covered = 0
    opened = []
    for J, arms in junctions(roads):
        ang = sorted(np.arctan2(u[1], u[0]) for u in arms)
        for a1, a2 in zip(ang, ang[1:] + [ang[0] + 2 * np.pi]):
            gap = a2 - a1
            if gap < np.radians(30) or gap > np.radians(170):
                continue
            b = (a1 + a2) / 2; bv = np.array([np.cos(b), np.sin(b)])
            ray = LineString([J, J + bv * LOT_REACH])
            hit = [lots[i] for i in lt.query(ray, predicate="intersects")]
            if not hit:
                continue
            d_lot = min(h.distance(Point(J)) for h in hit)
            corners += 1
            # both roads traced here: a kerb within ARM_REACH on the corner's side of each road
            ok = True
            for a in (a1, a2):
                u = np.array([np.cos(a), np.sin(a)])
                probe = LineString([J + u * 8 + bv * 2, J + u * ARM_REACH + bv * 2]).buffer(10, cap_style=2)
                if not len(kt.query(probe, predicate="intersects")):
                    ok = False
                    break
            if not ok:
                continue
            covered += 1
            seg = LineString([J, J + bv * (d_lot + 1.0)])
            if not len(kt.query(seg, predicate="intersects")):
                opened.append([round(float(J[0] + bv[0] * d_lot * 0.7), 1), round(float(J[1] + bv[1] * d_lot * 0.7), 1)])
    return {"corners": corners, "covered": covered, "open": len(opened),
            "open_pct": round(100.0 * len(opened) / max(covered, 1), 1), "points": opened}


def main(a):
    epsg = int(a[a.index("--epsg") + 1]) if "--epsg" in a else 7856
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    kerbs = []
    for f in json.load(open(a[0]))["features"]:
        g = f["geometry"]
        for c in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            x, y = tr.transform(*np.asarray(c).T)
            kerbs.append(np.c_[x, y])
    lots = [g for g in kr.load_faces(a[1]) if g.geom_type == "Polygon"]
    roads = [g for g in kr.load_faces(a[2]) if g.geom_type == "LineString"]
    r = audit(kerbs, lots, roads)
    json.dump(r, open(a[3], "w"))
    print(json.dumps({k: v for k, v in r.items() if k != "points"}))


if __name__ == "__main__":
    main(sys.argv[1:])
