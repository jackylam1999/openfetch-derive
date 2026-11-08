#!/usr/bin/env python3
"""Kerb lines against a reference kerb layer, per metre.

Usage: python3 tools/derive/compare_kerbs.py derived.geojson reference.geojson xmin ymin xmax ymax [--tol 1.0] [--png out.png]

Both layers are clipped to the box and sampled every 0.5 m. Recall = share of reference length with a derived line within
--tol; precision = share of derived length with a reference line within --tol; offset = distance from matched derived
samples to the reference (median / 90th percentile). The picture shows reference grey, matched derived green, extra red.
"""
import sys, json
import numpy as np
from shapely.geometry import shape, box as sbox
from shapely.strtree import STRtree


def lines(path, clip):
    out = []
    for f in json.load(open(path))["features"]:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"]).intersection(clip)
        for p in (g.geoms if hasattr(g, "geoms") else [g]):
            if p.geom_type == "LineString" and p.length > 0:
                out.append(p)
    return out


def samples(ls, step=0.5):
    pts = []
    for l in ls:
        for t in np.arange(step / 2, l.length, step):
            pts.append(l.interpolate(t).coords[0])
    return np.array(pts).reshape(-1, 2)


def dist(pts, ls):
    from shapely import points
    tree = STRtree(ls)
    p = points(pts)
    idx = tree.nearest(p)
    return np.array([ls[i].distance(q) for i, q in zip(idx, p)])


def main():
    a = sys.argv[1:]
    tol = float(a[a.index("--tol") + 1]) if "--tol" in a else 1.0
    png = a[a.index("--png") + 1] if "--png" in a else None
    der, ref = a[0], a[1]; clip = sbox(*map(float, a[2:6]))
    D, R = lines(der, clip), lines(ref, clip)
    ds, rs = samples(D), samples(R)
    dd = dist(ds, R) if len(R) and len(ds) else np.full(len(ds), np.inf)
    rd = dist(rs, D) if len(D) and len(rs) else np.full(len(rs), np.inf)
    m = dd <= tol
    res = {"reference_km": round(len(rs) * 0.5 / 1000, 2), "derived_km": round(len(ds) * 0.5 / 1000, 2),
           "recall": round(float((rd <= tol).mean()), 3) if len(rd) else 0, "precision": round(float(m.mean()), 3) if len(dd) else 0,
           "offset_median_m": round(float(np.median(dd[m])), 2) if m.any() else None,
           "offset_p90_m": round(float(np.percentile(dd[m], 90)), 2) if m.any() else None, "tol_m": tol}
    for t in (0.5, 2.0):
        res[f"recall_at_{t}m"] = round(float((rd <= t).mean()), 3) if len(rd) else 0
    print(json.dumps(res))
    if png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 10))
        for l in R:
            ax.plot(*l.xy, color="#999999", lw=1.2, solid_capstyle="round")
        ax.scatter(ds[m, 0], ds[m, 1], s=2, c="#1a9850")
        ax.scatter(ds[~m, 0], ds[~m, 1], s=2, c="#d73027")
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"grey = council kerbs, green = LiDAR kerbs matched, red = extra  |  recall {res['recall']:.0%}, "
                     f"precision {res['precision']:.0%}, offset {res['offset_median_m']} m", fontsize=10)
        fig.tight_layout(); fig.savefig(png, dpi=110)


if __name__ == "__main__":
    main()
