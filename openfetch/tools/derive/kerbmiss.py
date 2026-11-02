#!/usr/bin/env python3
"""Where are the kerbs the model still misses? (2 Nov 2026: the hidden-kerb fill added almost nothing, so the misses are not short
gaps along lot frontages.) For each box, council kerb samples (every 0.5 m) with no drawn line within 1 m are sorted by:
  road   type of the nearest official centreline (main 1-3, collector 4-5, local 6, lane 7+)
  where  'frontage' (a lot within 12 m: the kerb along the property side) or 'median/island' (no lot near: medians,
         roundabouts, traffic islands, kerbs along parks)
  run    length of the missed stretch along the council line: <10 m, 10-40 m, >40 m (whole kerbs not drawn)

Usage: python3 kerbmiss.py kp_dir thresh box [box ...]   (reads <box>_derived_<thresh>.geojson, _kerbs, _lots, _roads, _meta)
"""
import sys, json
import numpy as np
import shapely
from shapely.geometry import shape, box as sbox
from shapely.strtree import STRtree


def flat(path, kind):
    try:
        fs = json.load(open(path))["features"]
    except FileNotFoundError:
        return [], []
    gs, ps = [], []
    for f in fs:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        for p in getattr(g, "geoms", [g]):
            if p.geom_type == kind and not p.is_empty:
                gs.append(p); ps.append(f.get("properties") or {})
    return gs, ps


def one(kp, th, nm):
    b = sbox(*json.load(open(f"{kp}/{nm}_meta.json"))["box"])
    D = flat(f"{kp}/{nm}_derived_{th}.geojson", "LineString")[0]
    R = [g for g in (r.intersection(b) for r in flat(f"{kp}/{nm}_kerbs.geojson", "LineString")[0]) if not g.is_empty]
    R = [p for g in R for p in getattr(g, "geoms", [g]) if p.geom_type == "LineString"]
    lots = flat(f"{kp}/{nm}_lots.geojson", "Polygon")[0]
    roads, rp = flat(f"{kp}/{nm}_roads.geojson", "LineString")
    dt, lt, rt = STRtree(D), STRtree(lots), STRtree(roads) if roads else None
    cnt = {}
    tot = 0
    for l in R:
        P = shapely.points([l.interpolate(t).coords[0] for t in np.arange(0.25, l.length, 0.5)])
        if not len(P):
            continue
        tot += len(P)
        miss = shapely.distance(P, np.asarray(D, object)[dt.nearest(P)]) > 1.0 if D else np.ones(len(P), bool)
        if not miss.any():
            continue
        lotd = shapely.distance(P, np.asarray(lots, object)[lt.nearest(P)]) if lots else np.full(len(P), 99.0)
        if rt is not None:
            h = np.array([rp[i].get("functionhierarchy") or 9 for i in rt.nearest(P)])
            road = np.where(h <= 3, "main", np.where(h <= 5, "collector", np.where(h == 6, "local", "lane")))
        else:
            road = np.full(len(P), "?")
        i = 0
        while i < len(P):
            if not miss[i]:
                i += 1; continue
            j = i
            while j + 1 < len(P) and miss[j + 1]:
                j += 1
            L = (j - i + 1) * 0.5; run = "<10 m" if L < 10 else "10-40 m" if L <= 40 else ">40 m"
            for k in range(i, j + 1):
                key = (road[k], "frontage" if lotd[k] <= 12 else "median/island", run)
                cnt[key] = cnt.get(key, 0) + 1
            i = j + 1
    return cnt, tot


if __name__ == "__main__":
    kp, th, boxes = sys.argv[1], sys.argv[2], sys.argv[3:]
    allc, allt = {}, 0
    for nm in boxes:
        c, t = one(kp, th, nm); allt += t
        for k, v in c.items():
            allc[k] = allc.get(k, 0) + v
        m = sum(c.values())
        print(f"{nm}: missed {m * 0.5 / 1000:.2f} km of {t * 0.5 / 1000:.2f} km ({m / max(t, 1):.0%})")
    m = sum(allc.values())
    print(f"\nALL: missed {m * 0.5 / 1000:.2f} km of {allt * 0.5 / 1000:.2f} km. Share of the missed length:")
    for dim, i in (("road", 0), ("where", 1), ("run", 2)):
        agg = {}
        for k, v in allc.items():
            agg[k[i]] = agg.get(k[i], 0) + v
        print(f"  by {dim}: " + ", ".join(f"{k} {v / max(m, 1):.0%}" for k, v in sorted(agg.items(), key=lambda x: -x[1])))
    print("  top 8 groups: " + "; ".join(f"{'/'.join(k)} {v / max(m, 1):.0%}" for k, v in sorted(allc.items(), key=lambda x: -x[1])[:8]))
    json.dump({"/".join(k): v * 0.5 for k, v in allc.items()}, open(f"{kp}/kerbmiss_{th}.json", "w"), indent=1)
