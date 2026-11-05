#!/usr/bin/env python3
"""Consistency numbers for drawn kerb areas with no council kerbs to score against (kerbs-direction.md "4 Nov 11:40Z" step B).
Per box, from the drawn lines (<nm>_derived.geojson, or <nm>_derived_<thresh>.geojson on the scored boxes) and the fetched roads,
lots and LiDAR ground grid:
  km        drawn length by road type (main / collector / local / lane, as kerbapply.tag)
  both      share of local-street centreline (functionhierarchy 6, every 20 m) with a drawn kerb 2-12 m out on BOTH sides
  step      share of "model" length on a LiDAR step: kerbstep.grids step >= 5 cm within 0.5 m on at least 30% of 0.5 m samples
  fill      share of length from the street offset (filled, not seen)
  offset    median distance from drawn kerb to the nearest lot (m); lots are a model input, so weak evidence
  lidar     the box has a ground grid
Usage:
  python kerbsanity.py scored kp_dir thresh result.json     (the 4 check + 4 hold boxes, with their found share: calibration)
  python kerbsanity.py ship ship_dir boxes.json             (C:\\kerb\\ship-boxes.json from the ship run: one row per suburb)
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import shapely
from shapely.geometry import shape, box as sbox, LineString
from shapely.strtree import STRtree
import kerblearn as kl
import kerbapply as ka

G = 0.25


def lines(path, clip):
    out = []
    for f in json.load(open(path))["features"]:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"]).intersection(clip)
        for p in getattr(g, "geoms", [g]):
            if p.geom_type == "LineString" and p.length > 0:
                out.append((p, "street" if (f.get("properties") or {}).get("street") else "model"))
    return out


def one(src, nm, der):
    m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"]); kl.BX[nm] = tuple(m["box"][:2])
    L = lines(der, clip); D = [l for l, _ in L]
    r = {"km": {}, "len": sum(l.length for l in D), "fill": sum(l.length for l, s in L if s == "street"), "lidar": os.path.exists(f"{src}/{nm}_dem.npy")}
    for l, t in zip(D, ka.tag(src, nm, D)):
        r["km"][t] = r["km"].get(t, 0) + l.length / 1000
    U = shapely.union_all(D) if D else None
    loc = [shape(f["geometry"]).intersection(clip) for f in json.load(open(f"{src}/{nm}_roads.geojson"))["features"]
           if f.get("geometry") and (f.get("properties") or {}).get("functionhierarchy") == 6]
    both = tot = 0
    for g in loc:
        for c in getattr(g, "geoms", [g]):
            if c.geom_type != "LineString":
                continue
            for t in np.arange(10, c.length - 5, 20.0):
                a, b = c.interpolate(t - 1), c.interpolate(t + 1); p = c.interpolate(t)
                dx, dy = b.x - a.x, b.y - a.y; k = np.hypot(dx, dy)
                if not k:
                    continue
                nx, ny = -dy / k, dx / k; tot += 1
                if U is not None and all(U.intersects(LineString([(p.x + s * 2 * nx, p.y + s * 2 * ny), (p.x + s * 12 * nx, p.y + s * 12 * ny)]))
                                         for s in (1, -1)):
                    both += 1
    r["both"] = (both, tot)
    lots = [shape(f["geometry"]) for f in json.load(open(f"{src}/{nm}_lots.geojson"))["features"] if f.get("geometry")]
    pts = [l.interpolate(t) for l in D for t in np.arange(0.5, l.length, 2.0)]
    if lots and pts:
        T = STRtree(lots); r["offset"] = float(np.median(shapely.distance(np.asarray(pts, object), np.asarray(lots, object)[T.nearest(pts)])))
    if r["lidar"] and D:
        import kerbstep as ks
        tr, up = ks.grids(src, nm, D)[:2]; Gm = ndimage.maximum_filter(up, 5); inv = ~tr; on = tl = 0
        for l, s in L:
            if s != "model":
                continue
            xy = np.array([l.interpolate(t).coords[0] for t in np.arange(0.25, l.length, 0.5)]).reshape(-1, 2)
            if not len(xy):
                continue
            c, rr = inv * (xy[:, 0], xy[:, 1])
            v = Gm[np.clip(rr.astype(int), 0, Gm.shape[0] - 1), np.clip(c.astype(int), 0, Gm.shape[1] - 1)]
            tl += l.length; on += l.length * ((v >= 0.05).mean() >= 0.3)
        r["step"] = (on, tl)
    return r


def row(name, rs, extra=""):
    km = {}
    for r in rs:
        for k, v in r["km"].items():
            km[k] = km.get(k, 0) + v
    b = [sum(r["both"][i] for r in rs) for i in (0, 1)]
    st = [sum(r.get("step", (0, 0))[i] for r in rs) for i in (0, 1)]
    ln = sum(r["len"] for r in rs); fl = sum(r["fill"] for r in rs)
    off = [r["offset"] for r in rs if "offset" in r]
    li = sum(r["lidar"] for r in rs)
    pc = lambda a, t: f"{100 * a / t:5.1f}" if t else "    -"
    print(f"{name:14s} km local {km.get('local', 0):5.1f} coll {km.get('collector', 0):5.1f} main {km.get('main', 0):5.1f} | both {pc(*b)}"
          f" | step {pc(*st)} | fill {pc(fl, ln)} | offset {np.median(off) if off else float('nan'):4.1f} | lidar {li}/{len(rs)} {extra}", flush=True)
    return {"km": km, "both": b, "step": st, "fill": [fl, ln], "lidar": [li, len(rs)]}


def main():
    mode, src = sys.argv[1], sys.argv[2]; res = {}
    if mode == "scored":
        th, R = sys.argv[3], json.load(open(sys.argv[4]))["boxes"]
        for nm, *_ in kl.VAL + kl.HOLD:
            der = f"{src}/{nm}_derived_{th}.geojson"
            if os.path.exists(der) and nm in R and kl.CO[nm] != "com":
                b = R[nm]; loc = (b.get("scales") or {}).get("local streets", [0, None])[1]
                res[nm] = row(nm, [one(src, nm, der)], f"| found {b.get('recall')} local {loc} prec {b.get('precision')}")
    else:
        S = json.load(open(sys.argv[3])); by = {}
        for sub, lo, la in S["suburbs"]:
            rs = []
            for nm, x, y in ka.boxes(sub, lo, la, 2):
                der = f"{src}/{nm}_derived.geojson"
                if os.path.exists(der):
                    rs.append(one(src, nm, der))
            if rs:
                res[sub] = row(sub, rs)
    json.dump(res, open(f"{src}/sanity-{mode}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
