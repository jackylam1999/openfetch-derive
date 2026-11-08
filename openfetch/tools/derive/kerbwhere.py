#!/usr/bin/env python3
"""Where exactly is the model blind? (step 1 of docs/handoffs/kerbs-direction.md, 4 Nov 2026). The misses do not follow visibility
(trees and shadow are found as often as clear kerb) but road type, so check whether they follow WHERE the kerb sits relative to the
map layers the model leans on. For every council kerb sample (0.5 m):
  found   a drawn line within 1 m (boxes with <box>_derived_<thresh>.geojson), else max P within 1 m >= thresh
  P       pc-16-1 probability at the sample (max within 1 m)
  road    type of the nearest centreline;  lot  distance to the nearest lot, bands 0-3/3-6/6-10/10-15/>15 m
  cl      distance to the nearest centreline, 2 m bands;  side  'lot side', 'far side/median' (the way to the nearest lot crosses a
          centreline) or 'no lot' (none within 30 m)
Prints found % / median P / km per band per box, then the training boxes' label share per (lot, cl, side) type and the share of the
check boxes' missed kerb that lies in types holding < 5% of the training labels (kerb the prior has never seen).

Usage: python kerbwhere.py kp_dir P_dir thresh [train_P_dir]
"""
import sys, os, json
import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import box as sbox
from shapely.strtree import STRtree
import kerblearn as kl
from kerbmiss import flat

CELL = kl.CELL
LOTB = (3, 6, 10, 15)


def band(v, edges, fmt):
    i = np.searchsorted(edges, v, side="right")
    lab = [f"{a}-{b}" for a, b in zip((0,) + edges[:-1], edges)] + [f">{edges[-1]}"]
    return np.array([fmt.format(lab[k]) for k in i])


def one(kp, pd, th, nm):
    m = json.load(open(f"{kp}/{nm}_meta.json")); b = sbox(*m["box"])
    R = [g for g in (r.intersection(b) for r in flat(f"{kp}/{nm}_kerbs.geojson", "LineString")[0]) if not g.is_empty]
    R = [p for g in R for p in getattr(g, "geoms", [g]) if p.geom_type == "LineString"]
    xy = np.array([l.interpolate(t).coords[0] for l in R for t in np.arange(0.25, l.length, 0.5)]).reshape(-1, 2)
    if not len(xy):
        return None
    P = shapely.points(xy); out = {}
    pf = f"{pd}/{nm}_P.npy"
    if os.path.exists(pf):
        A = ndimage.maximum_filter(np.load(pf), 21)
        c = ((xy[:, 0] - m["x0"]) / CELL).astype(int); r = ((m["y0"] + m["w"] - xy[:, 1]) / CELL).astype(int)
        out["P"] = A[np.clip(r, 0, A.shape[0] - 1), np.clip(c, 0, A.shape[1] - 1)] / 255.0; del A
    df = f"{kp}/{nm}_derived_{th}.geojson"
    if os.path.exists(df):
        D = flat(df, "LineString")[0]
        out["found"] = shapely.distance(P, np.asarray(D, object)[STRtree(D).nearest(P)]) <= 1.0 if D else np.zeros(len(P), bool)
    elif "P" in out:
        out["found"] = out["P"] >= float(th)
    lots = flat(f"{kp}/{nm}_lots.geojson", "Polygon")[0]
    roads, rp = flat(f"{kp}/{nm}_roads.geojson", "LineString")
    li = STRtree(lots).nearest(P) if lots else None
    lotd = shapely.distance(P, np.asarray(lots, object)[li]) if lots else np.full(len(P), 99.0)
    if roads:
        ri = STRtree(roads).nearest(P); RA = np.asarray(roads, object)
        cld = shapely.distance(P, RA[ri])
        h = np.array([rp[i].get("functionhierarchy") or 9 for i in ri])
        out["road"] = np.where(h <= 3, "main", np.where(h <= 5, "collector", np.where(h == 6, "local", "lane")))
        U = shapely.union_all(RA); shapely.prepare(U)
        far = shapely.intersects(U, shapely.shortest_line(P, np.asarray(lots, object)[li])) if lots else np.zeros(len(P), bool)
    else:
        cld = np.full(len(P), 99.0); out["road"] = np.full(len(P), "?"); far = np.zeros(len(P), bool)
    out["lot"] = band(lotd, LOTB, "lot {} m")
    out["cl"] = band(np.minimum(cld, 99), (2, 4, 6, 8, 10, 12, 15, 20), "cl {} m")
    out["side"] = np.where(lotd > 30, "no lot", np.where(far & (lotd > 1), "far side/median", "lot side"))
    out["type"] = np.array([f"{a} | {c} | {s}" for a, c, s in zip(out["lot"], out["cl"], out["side"])])
    return out


def table(nm, o):
    f = o.get("found"); p = o.get("P"); n = len(o["lot"])
    print(f"\n{nm}: {n * 0.5 / 1000:.1f} km council kerb" + (f", found {f.mean():.0%}" if f is not None else ""), flush=True)
    for dim in ("road", "lot", "cl", "side"):
        rows = []
        for k in sorted(set(o[dim])):
            s = o[dim] == k
            rows.append(f"{k}: {s.sum() * 0.5 / 1000:.1f} km" + (f" found {f[s].mean():.0%}" if f is not None else "") +
                        (f" P50 {np.median(p[s]):.2f}" if p is not None else ""))
        print(f"  {dim:5s} " + "; ".join(rows))


def main():
    kp, pd, th = sys.argv[1:4]; tpd = sys.argv[4] if len(sys.argv) > 4 else None
    ev = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{kp}/{b[0]}_dem.npy")]
    res = {}
    for nm in ev:
        o = one(kp, pd, th, nm)
        if o is not None:
            res[nm] = o; table(nm, o)
    tr = {}
    for b in kl.TRAIN:
        o = one(kp, tpd or "-", th, b[0])
        if o is not None:
            tr[b[0]] = o
            if tpd and "P" in o:
                table(b[0] + " (training box, found = P >= thresh)", o)
    types = np.concatenate([o["type"] for o in tr.values()]); u, c = np.unique(types, return_counts=True); share = dict(zip(u, c / c.sum()))
    print("\nTraining label share by side:", (lambda u, c: {str(k): f"{v / c.sum():.0%}" for k, v in zip(u, c)})(*np.unique(np.concatenate([o["side"] for o in tr.values()]), return_counts=True)))
    rare = {k for k, v in share.items() if v < 0.05}
    for nm, o in res.items():
        miss = ~o["found"]; t = o["type"]
        print(f"{nm}: missed {miss.sum() * 0.5 / 1000:.2f} km, in rare types (< 5% of training labels) "
              f"{np.isin(t[miss], list(rare)).mean():.0%}, found kerb in rare types {np.isin(t[~miss], list(rare)).mean():.0%}")
    allm = np.concatenate([o["type"][~o["found"]] for o in res.values()]); allf = np.concatenate([o["found"] for o in res.values()])
    allt = np.concatenate([o["type"] for o in res.values()])
    print("\nTop 12 types by missed length (all check boxes): type, missed km, found %, training share")
    u, c = np.unique(allm, return_counts=True)
    for k, v in sorted(zip(u, c), key=lambda x: -x[1])[:12]:
        print(f"  {k}: {v * 0.5 / 1000:.2f} km, found {allf[allt == k].mean():.0%}, train {share.get(k, 0):.1%}")
    for dim in ("side", "lot", "cl", "road"):
        a = np.concatenate([o[dim] for o in res.values()]); ta = np.concatenate([o[dim] for o in tr.values()])
        print(f"ALL {dim}: " + "; ".join(f"{k} found {allf[a == k].mean():.0%} ({(a == k).sum() * 0.5 / 1000:.1f} km, train {(ta == k).mean():.0%})"
                                         for k in sorted(set(a))))


if __name__ == "__main__":
    main()
