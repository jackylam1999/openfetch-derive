#!/usr/bin/env python3
"""Compare derived roofs with a reference footprint layer (same CRS, metres).

Usage: python3 tools/derive/compare.py derived.geojson reference.geojson [--hmax FIELD] [--hmean FIELD] [--bbox xmin ymin xmax ymax]

Prints: how many reference buildings were found (IoU >= 0.5 with one derived polygon), missed, extra;
area ratio, IoU and outline offset (median distance from reference boundary vertices to the derived
boundary) for the matches; height differences when the reference carries heights above ground.
"""
import sys, json
import numpy as np
from shapely.geometry import shape, box
from shapely.strtree import STRtree


def load(path, bbox):
    fc = json.load(open(path))
    geoms, props = [], []
    clip = box(*bbox) if bbox else None
    for f in fc["features"]:
        g = shape(f["geometry"])
        if g.is_empty or not g.is_valid:
            g = g.buffer(0)
        if clip is not None and not g.intersects(clip):
            continue
        geoms.append(g); props.append(f.get("properties", {}))
    return geoms, props


def outline_offset(ref, der):
    pts = np.asarray(ref.exterior.coords) if ref.geom_type == "Polygon" else np.vstack([np.asarray(p.exterior.coords) for p in ref.geoms])
    b = der.boundary
    from shapely.geometry import Point
    d = [b.distance(Point(x, y)) for x, y in pts]
    return float(np.median(d)), float(np.percentile(d, 90))


def main():
    a = sys.argv[1:]
    bbox = None; hmax = "HEIGHT_MAX"; hmean = "HEIGHT_MEAN"
    if "--bbox" in a:
        i = a.index("--bbox"); bbox = [float(v) for v in a[i + 1:i + 5]]; del a[i:i + 5]
    if "--hmax" in a:
        i = a.index("--hmax"); hmax = a[i + 1]; del a[i:i + 2]
    if "--hmean" in a:
        i = a.index("--hmean"); hmean = a[i + 1]; del a[i:i + 2]
    D, Dp = load(a[0], bbox); R, Rp = load(a[1], bbox)
    tree = STRtree(D)
    used = set(); rows = []
    for ri, (rg, rp) in enumerate(zip(R, Rp)):
        best, bi = 0.0, -1
        for di in tree.query(rg):
            dg = D[di]
            inter = rg.intersection(dg).area
            if inter == 0: continue
            iou = inter / rg.union(dg).area
            if iou > best: best, bi = iou, int(di)
        if bi >= 0 and best >= 0.5:
            used.add(bi)
            med, p90 = outline_offset(rg, D[bi])
            row = {"iou": best, "area_ratio": D[bi].area / rg.area, "off_med": med, "off_p90": p90}
            dp = Dp[bi]
            if rp.get(hmax) is not None and dp.get("h_max") is not None:
                row["d_hmax"] = dp["h_max"] - float(rp[hmax])
            if rp.get(hmean) is not None and dp.get("h_mean") is not None:
                row["d_hmean"] = dp["h_mean"] - float(rp[hmean])
            rows.append(row)
        else:
            rows.append(None)
    found = [r for r in rows if r]
    from shapely.ops import unary_union
    clip = box(*bbox) if bbox else None
    ru, du = unary_union(R), unary_union(D)
    if clip is not None: ru, du = ru.intersection(clip), du.intersection(clip)
    ov = ru.intersection(du).area
    print(f"area view (overlapping reference footprints counted once): reference {ru.area:.0f} m2, derived {du.area:.0f} m2, overlap {ov:.0f} m2 -> recall {ov/ru.area:.2f}, precision {ov/du.area:.2f}")
    # height view: reference footprint whose area is >= 60% inside one derived polygon (works when buildings were merged or split)
    dh = []
    for rg, rp in zip(R, Rp):
        if rp.get(hmax) is None: continue
        for di in tree.query(rg):
            if rg.intersection(D[di]).area >= 0.6 * rg.area and Dp[di].get("h_max") is not None:
                dh.append(Dp[di]["h_max"] - float(rp[hmax])); break
    if dh:
        v = np.array(dh)
        print(f"height view (reference building inside a derived roof, n={len(v)}): h_max difference median {np.median(v):+.2f} m, p90(|x|) {np.percentile(np.abs(v),90):.2f}, rms {np.sqrt((v**2).mean()):.2f}")
    print(f"reference buildings: {len(R)}  found (IoU>=0.5): {len(found)}  missed: {len(R)-len(found)}  extra derived: {len(D)-len(used)} of {len(D)}")
    missed_area = sum(g.area for g, r in zip(R, rows) if r is None)
    print(f"missed area: {missed_area:.0f} m2 of {sum(g.area for g in R):.0f} m2 ({100*missed_area/max(1,sum(g.area for g in R)):.1f}%)")
    if not found: return
    def stat(k, unit="m"):
        v = np.array([r[k] for r in found if k in r])
        if not len(v): return
        rms = float(np.sqrt((v ** 2).mean()))
        print(f"  {k:10s} n={len(v):4d} median {np.median(v):+.2f} {unit}  mean {v.mean():+.2f}  p90(|x|) {np.percentile(np.abs(v),90):.2f}  rms {rms:.2f}")
    stat("iou", ""); stat("area_ratio", "x"); stat("off_med"); stat("off_p90"); stat("d_hmax"); stat("d_hmean")


if __name__ == "__main__":
    main()
