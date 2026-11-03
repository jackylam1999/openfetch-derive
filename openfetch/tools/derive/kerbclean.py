#!/usr/bin/env python3
"""Score a box against a cleaned council kerb layer (kerbs-lidar-rounds.md NEXT 1): a picture check of the long misses in Parramatta CBD
found about 70% were not street kerbs (2 Nov 2026). The normal reference is untouched, so rounds stay comparable; this reports both.

Usage: python3 kerbclean.py kp_dir box roofs.geojson thresh [thresh ...]
Input: <box>_kerbs/_derived_<thresh>/_roads/_meta in kp_dir, roofs from roofs.py (Jacky has no official NSW footprints).
Output: <box>_kerbs_clean.geojson, <box>_clean_<thresh>.png, <box>_clean.json; prints old and clean scores.

Council lines are cut into PIECE m pieces, and a piece is dropped when (first rule that applies):
  building  it runs inside a LiDAR roof, ROOF_IN m or more in from the roof edge (awnings at the kerb stay)
  rail      within RAIL m of a railway and over ROAD m from every road centreline
  off road  over ROAD m from every road centreline: plazas, forecourts, car parks
A drawn line within KEEP m of a dropped piece counts neither way, so cleaning can only lift found, not precise by itself.
"""
import sys, os, json
import numpy as np
import shapely
from shapely.geometry import shape, mapping, box as sbox
from shapely.ops import substring
from shapely.strtree import STRtree
import compare_kerbs as ck

PIECE, ROOF_IN, RAIL, ROAD, KEEP = 5.0, 1.0, 12.0, 15.0, 1.5
RAILWAY = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Transport_Theme_multiCRS/FeatureServer/7/query"


def layer(path, kinds):
    fs = json.load(open(path))["features"]
    gs = [p for f in fs if f.get("geometry") for g in [shape(f["geometry"])] for p in getattr(g, "geoms", [g])]
    return [g for g in gs if g.geom_type in kinds and not g.is_empty]


def railway(kp, nm, b):
    p = f"{kp}/{nm}_rail.geojson"
    if not os.path.exists(p):
        import kerbphoto
        fs = kerbphoto.query(RAILWAY, tuple(b), fields="OBJECTID,classsubtype,operationalstatus,railontype")
        json.dump({"type": "FeatureCollection", "features": fs}, open(p, "w"))
    return layer(p, ("LineString",))


def near(pts, gs):
    if not gs:
        return np.full(len(pts), np.inf)
    return shapely.distance(pts, np.asarray(gs, object)[STRtree(gs).nearest(pts)])


def clean(kp, nm, roofs):
    bb = json.load(open(f"{kp}/{nm}_meta.json"))["box"]; clip = sbox(*bb)
    R = ck.lines(f"{kp}/{nm}_kerbs.geojson", clip)
    ps = [substring(l, a, min(a + PIECE, l.length)) for l in R for a in np.arange(0, l.length, PIECE)]
    ps = [p for p in ps if p.length > 0.01]
    mid = shapely.points([p.interpolate(0.5, normalized=True).coords[0] for p in ps])
    roads = layer(f"{kp}/{nm}_roads.geojson", ("LineString",))
    inner = [g for g in (r.buffer(-ROOF_IN) for r in layer(roofs, ("Polygon",))) if not g.is_empty]
    t = shapely.STRtree(inner); hit = t.query(mid, predicate="intersects")
    bld = np.zeros(len(ps), bool); bld[hit[0]] = True
    far = near(mid, roads) > ROAD
    rail = near(mid, railway(kp, nm, bb)) <= RAIL
    why = np.where(bld, "building", np.where(far & rail, "rail", np.where(far, "off road", "")))
    return bb, R, ps, why


def rate(D, R, tol=1.0):
    ds, rs = ck.samples(D), ck.samples(R)
    dd, rd = ck.dist(ds, R), ck.dist(rs, D); m = dd <= tol
    p, r = float(m.mean()), float((rd <= tol).mean())
    return {"found": round(r, 3), "precise": round(p, 3), "f1": round(2 * p * r / max(p + r, 1e-6), 3), "offset_m": round(float(np.median(dd[m])), 2),
            "reference_km": round(len(rs) * 0.5 / 1000, 2), "drawn_km": round(len(ds) * 0.5 / 1000, 2)}, ds, m


def picture(path, keep, gone, ds, m, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 10))
    for l in keep:
        ax.plot(*l.xy, color="#999999", lw=1.2)
    for l in gone:
        ax.plot(*l.xy, color="#2166ac", lw=1.6)
    ax.scatter(ds[m, 0], ds[m, 1], s=2, c="#1a9850"); ax.scatter(ds[~m, 0], ds[~m, 1], s=2, c="#d73027")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    kp, nm, roofs, ths = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    bb, R, ps, why = clean(kp, nm, roofs)
    keep = [p for p, w in zip(ps, why) if not w]; gone = [p for p, w in zip(ps, why) if w]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(p)} for p in keep]},
              open(f"{kp}/{nm}_kerbs_clean.geojson", "w"))
    res = {"dropped_km": {w: round(sum(p.length for p, y in zip(ps, why) if y == w) / 1000, 2) for w in ("building", "rail", "off road")}}
    zone = shapely.union_all([p.buffer(KEEP) for p in gone]) if gone else None
    for th in ths:
        D = ck.lines(f"{kp}/{nm}_derived_{th}.geojson", sbox(*bb))
        old = rate(D, R)[0]
        Dc = [p for g in ([l.difference(zone) for l in D] if zone is not None else D) for p in getattr(g, "geoms", [g])
              if p.geom_type == "LineString" and p.length > 0]
        new, ds, m = rate(Dc, keep)
        res[th] = {"council": old, "clean": new}
        print(f"{nm} {th}: council found {old['found']:.1%} precise {old['precise']:.1%} F1 {old['f1']:.3f}; "
              f"clean found {new['found']:.1%} precise {new['precise']:.1%} F1 {new['f1']:.3f} offset {new['offset_m']} m")
        picture(f"{kp}/{nm}_clean_{th}.png", keep, gone, ds, m, f"{nm}, grey = kept council kerbs, blue = dropped, green = matched, red = extra  |  "
                f"found {new['found']:.0%}, precise {new['precise']:.0%}")
    print("dropped km:", res["dropped_km"], "of", round(sum(l.length for l in R) / 1000, 2))
    json.dump(res, open(f"{kp}/{nm}_clean.json", "w"), indent=1)


if __name__ == "__main__":
    main()
