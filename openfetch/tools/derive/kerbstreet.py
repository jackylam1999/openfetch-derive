#!/usr/bin/env python3
"""Street-offset prior (game plan step 2, 3 Nov 2026): a street keeps its kerb at a near-constant distance from the centreline. For each
official road centreline and side, take the median distance of the drawn kerb on that side (needs MIN_SEEN m drawn, spread under SPREAD m),
carry it along the whole street as an offset line, and add the parts with no drawn line within AWAY m. Trimmed near other streets so the
offset does not run across junctions. Optionally keep only pieces the LiDAR step fit or a weak photo probability supports.

Usage (KERB_CFG as the scored model): python kerbstreet.py kp_dir long_dir thresh out_dir
Prints, per box: oracle (share of missed kerb in stretches > 40 m within 1 m of a proposal, share of proposal length on council kerb),
then found / precise / F1 for base, all proposals, and step- or P-confirmed proposals.
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
import kerbstep as ks
from shapely.geometry import shape, Point, LineString, box as sbox
from shapely.strtree import STRtree
from shapely.ops import unary_union
from affine import Affine

MIN_SEEN, SPREAD, AWAY, JUNC, PIECE = 10.0, 0.6, 1.5, 3.0, 10.0  # m
MIRROR = os.environ.get("KERB_MIRROR") == "1"


def roads(src, nm, clip):
    fs = [shape(f["geometry"]) for f in json.load(open(f"{src}/{nm}_roads.geojson"))["features"] if f.get("geometry")]
    return [p for g in fs for q in [g.intersection(clip.buffer(60))] for p in getattr(q, "geoms", [q]) if p.geom_type == "LineString" and p.length > 5]


def side(road, p):
    t = road.project(p); a, b = road.interpolate(max(t - 1, 0)), road.interpolate(min(t + 1, road.length))
    return 1 if (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x) > 0 else -1  # +1 = left


def proposals(Rd, D):
    tree = STRtree(Rd); off = {}
    for x, y in ck.samples(D)[::2]:  # samples every 0.5 m -> 1 m
        p = Point(x, y); i = int(tree.nearest(p)); d = Rd[i].distance(p)
        if 2 <= d <= 15:
            off.setdefault((i, side(Rd[i], p)), []).append(d)
    med = {k: float(np.median(v)) for k, v in off.items() if len(v) >= MIN_SEEN and np.subtract(*np.percentile(v, [75, 25])) <= SPREAD}
    if MIRROR:  # a street with one kerb drawn: the other kerb at the same distance on the other side
        med.update({(i, -s): d for (i, s), d in list(med.items()) if (i, -s) not in med})
    out = []
    for (i, s), d in med.items():
        g = Rd[i].offset_curve(s * d)
        others = unary_union([Rd[j] for j in tree.query(g.buffer(d + JUNC)) if j != i])
        if not others.is_empty:
            g = g.difference(others.buffer(d + JUNC))
        out += [p for p in getattr(g, "geoms", [g]) if p.geom_type == "LineString" and p.length >= PIECE]
    return out


def cut(ps, D, clip):
    near = unary_union([l.buffer(AWAY) for l in D]) if D else None
    out = []
    for g in ps:
        q = g.difference(near) if near is not None else g; q = q.intersection(clip)
        out += [p for p in getattr(q, "geoms", [q]) if p.geom_type == "LineString" and p.length >= PIECE]
    return out


def support(ls, grid, tr, at, share=0.3):
    """Keep pieces where at least share of 0.5 m samples have grid >= at within 0.5 m."""
    G = ndimage.maximum_filter(grid, 5); inv = ~tr; out = []
    for l in ls:
        xy = np.array([l.interpolate(t).coords[0] for t in np.arange(0.25, l.length, 0.5)])
        c, r = inv * (xy[:, 0], xy[:, 1]); v = G[np.clip(r.astype(int), 0, G.shape[0] - 1), np.clip(c.astype(int), 0, G.shape[1] - 1)]
        if (v >= at).mean() >= share:
            out.append(l)
    return out


def main():
    src, ld, th, od = sys.argv[1:5]; os.makedirs(od, exist_ok=True); res = {}; ora = {}
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{src}/{b[0]}_dem.npy") and os.path.exists(f"{ld}/{b[0]}_P.npy")]
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        trP = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        kp.vec(od, nm, P, trP, float(th))
        D, R = ck.lines(f"{od}/{nm}_derived.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        new = cut(proposals(roads(src, nm, clip), D), D, clip)
        # oracle on long misses
        xy = ck.samples(R); miss = ck.dist(xy, D) > 1
        lab, n = ndimage.label(miss); L = ndimage.sum(np.ones(len(miss)), lab, np.arange(1, n + 1)) * 0.5
        lng = miss & np.isin(lab, np.flatnonzero(L > 40) + 1)
        hit = float((ck.dist(xy[lng], new) <= 1).mean()) if new and lng.any() else 0.0
        on = float((ck.dist(ck.samples(new), R) <= 1).mean()) if new else 0.0
        ora[nm] = (round(hit, 3), round(on, 3), round(sum(l.length for l in new) / 1000, 2))
        tr, up, ok, nr, nc = ks.grids(src, nm, D)
        Pg = P  # photo grid
        sets = {"base": [], "all": new, "step3": support(new, up, tr, 0.03), "P0.1": support(new, P, trP, 0.1), "P0.2": support(new, P, trP, 0.2)}
        sets["step3|P0.1"] = [l for l in new if l in sets["step3"] or l in sets["P0.1"]]
        res[nm] = {k: (*ks.rate(D + v, R), round(sum(l.length for l in v) / 1000, 2)) for k, v in sets.items()}
        print(nm, "oracle (long-miss hit, proposals on kerb, km)", ora[nm], {k: (round(v[0], 3), round(v[1], 3), round(ks.f1(v), 3), v[2]) for k, v in res[nm].items()}, flush=True)
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    hold = [n for n in boxes if n in dict(h[:2] for h in kl.HOLD)]
    for k in res[boxes[0]]:
        print(k, "scenario score", round(float(np.mean([np.mean([ks.f1(res[n][k]) for n in v]) for v in by.values()])), 3),
              "worst held-out", round(min(ks.f1(res[n][k]) for n in hold), 3), "added km", round(sum(res[n][k][2] for n in boxes), 1), flush=True)
    json.dump({"oracle": ora, "boxes": res}, open(f"{od}/street.json", "w"), indent=1)


if __name__ == "__main__":
    main()
