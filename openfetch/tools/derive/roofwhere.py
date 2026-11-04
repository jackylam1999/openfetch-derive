#!/usr/bin/env python3
"""Where is the roof tracer blind (RT5, the kerbwhere.py lesson): per reference house, found / merged against what it stands on.

Usage: python3 tools/derive/roofwhere.py NAME=BOXDIR[,ref.geojson] ... --box NAME xmin ymin xmax ymax ... [--json out.json]

Same judges as roofscore.py (OSM shapes with the block-over-parts double drawing left out, or an official --ref file).
Each reference house gets: lot kind (torrens = DP lot, strata = SP lot, none = not on a 30-2000 m2 lot), shared walls (another
reference house within 0.5 m), height band (official HEIGHT_MAX, else the matched roof's h_max), size band, and who drew the
output roof that judges it (osm / ms / traced / none). For an official box also: did OSM draw it (an OSM shape at IoU >= 0.5).
Prints found % and merged % per band, per box and all boxes together. Bands with fewer than 10 houses are shown but not ranked.
"""
import sys, os, json, collections
import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roofscore as rs

HB = [(0, 6, "h<6"), (6, 12, "h6-12"), (12, 25, "h12-25"), (25, 999, "h25+")]
AB = [(0, 60, "a<60"), (60, 150, "a60-150"), (150, 400, "a150-400"), (400, 1e9, "a400+")]


def band(v, B):
    if v is None:
        return "h?"
    return next(n for a, b, n in B if a <= v < b)


def lot_kind(r, L, Lp, lt):
    best, kind = 0, "none"
    for i in lt.query(r):
        a = L[i].intersection(r).area
        if a > best and rs.LOT[0] <= L[i].area <= rs.LOT[1]:
            plan = (Lp[i].get("lot") or "").split("/")[-1].upper()
            best, kind = a, ("strata" if plan.startswith("SP") else "torrens")
    return kind if best >= 0.3 * r.area else "none"


def houses(name, d, ref=None, bbox=None):
    O, Op = rs.load(os.path.join(d, "combined.geojson"))
    L, Lp = rs.load(os.path.join(d, "lots.geojson"))
    C, Cp = rs.load(os.path.join(d, "community.geojson"), lambda p: p.get("src") == "osm")
    if ref:
        R, Rp = rs.load(ref)
    else:
        R, Rp = C, Cp
    if bbox:
        clip = box(*bbox)
        k = [i for i, r in enumerate(R) if clip.contains(r.centroid)]
        R, Rp = [R[i] for i in k], [Rp[i] for i in k]
    if not ref:
        R, Rp, _ = rs.drop_double(R, Rp)
    best, found, merged, split, omatch, covers = rs.match(R, O)
    lt, rt, ct = STRtree(L), STRtree(R), STRtree(C)
    out = []
    for i, r in enumerate(R):
        j = best[i][0]
        p = Op[j] if j >= 0 and best[i][1] > 0 else {}
        h = Rp[i].get("HEIGHT_MAX") if ref else None
        h = float(h) if h not in (None, "") else p.get("h_max")
        src = "none" if not p else ("traced" if "traced" in str(p.get("kind", "")) else (p.get("src") or "?"))
        row = {"box": name, "found": bool(found[i]), "merged": bool(merged[i]),
               "lot": lot_kind(r, L, Lp, lt) if L else "nolots",
               "walls": "shared" if any(int(k) != i and R[k].distance(r) <= 0.5 for k in rt.query(r.buffer(0.5))) else "free",
               "height": band(h, HB), "size": band(r.area, AB), "drawn_by": src}
        if ref:
            row["osm_had"] = "osm yes" if any(rs.TOL_IOU <= C[k].intersection(r).area / C[k].union(r).area for k in ct.query(r)) else "osm no"
        out.append(row)
    return out


def table(H, title):
    print(f"\n{title} ({len(H)} houses, found {100 * np.mean([h['found'] for h in H]):.0f}%, merged {100 * np.mean([h['merged'] for h in H]):.0f}%)")
    print("| key | band | n | found | merged | missed (n) |"); print("|---|---|---|---|---|---|")
    for key in ["lot", "walls", "height", "size", "drawn_by", "osm_had"]:
        g = collections.defaultdict(list)
        for h in H:
            if key in h:
                g[h[key]].append(h)
        for b in sorted(g, key=lambda b: -len(g[b])):
            x = g[b]
            print(f"| {key} | {b} | {len(x)} | {100 * np.mean([h['found'] for h in x]):.0f}% | {100 * np.mean([h['merged'] for h in x]):.0f}% | {sum(not h['found'] for h in x)} |")


if __name__ == "__main__":
    a = sys.argv[1:]
    boxes = {}
    while "--box" in a:
        k = a.index("--box"); boxes[a[k + 1]] = [float(v) for v in a[k + 2:k + 6]]; del a[k:k + 6]
    js = None
    if "--json" in a:
        k = a.index("--json"); js = a[k + 1]; del a[k:k + 2]
    allh = []
    for arg in a:
        name, rest = arg.split("=", 1)
        d, ref = (rest.split(",") + [None])[:2]
        H = houses(name, d, ref, boxes.get(name))
        table(H, name); allh += H
    if len(a) > 1:
        table(allh, "all boxes")
    if js:
        json.dump(allh, open(js, "w"))
