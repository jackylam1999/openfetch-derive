#!/usr/bin/env python3
"""Known-answer score of the LiDAR kerb finders against official council kerbs (kerb lead, 21 Nov 2026). Every block front facing
a street (fh 2-6 centreline within REACH m) is sampled every 2 m with a profile square to the front; the truth is the distance along
the profile to the first council kerb line (D_MIN to D_MAX m). Each finder gives a distance on the LiDAR traces' footing:
  strongest   the strongest drop in each profile on its own (kerbpcw.prof_step), what kerbpcw reads profile by profile
  side        one width per RUN samples of a front (kerbpcw.side_width), what kerblot uses for a block side
  chain       the road-most continuous chain through every drop (kerbcds.kerb_chain)
Reports per finder: share of truth samples answered, and of those within 0.5 m and 1 m, and the median signed error.

    python3 kerbknown.py roads_dir lots_dir grids_dir council.geojson EPSG out.json [--cells cells.txt]
council.geojson in lon/lat of EPSG (4283 for GDA94 portals: the datum step to GDA2020 is applied here, P-0216).
"""
import json, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbcds as kc
import kerbpcw as kpw

REACH = 25.0
RUN = 15


def truth_lines(path, epsg):
    T = Transformer.from_crs(int(epsg), 7856, always_xy=True); out = []
    for f in json.load(open(path))["features"]:
        g = shapely.transform(shape(f["geometry"]), lambda a: np.column_stack(T.transform(a[:, 0], a[:, 1])))
        out += [l for l in getattr(g, "geoms", [g]) if l.length > 0]
    return out


def fronts(lots, frame):
    """Block outlines (lots joined, gaps under 0.8 m closed) inside frame, anticlockwise: the street lies to the right."""
    near = [g for g in lots if g.intersects(frame)]
    land = unary_union([g.buffer(kc.CLOSE) for g in near]).buffer(-kc.CLOSE)
    out = []
    for b in getattr(land, "geoms", [land]):
        if b.geom_type == "Polygon" and b.area > 200:
            out.append(shapely.geometry.polygon.orient(b).exterior)
    return out


def samples(ring, streets_t, streets, truth_t, truth):
    """Ordered samples of one block outline: points, outward normals, reach to the street centreline, truth distance (nan)."""
    P, N, R, D = [], [], [], []
    for t in np.arange(0.0, ring.length, 2.0):
        q = ring.interpolate(t)
        a, b = np.array(ring.interpolate((t - 2) % ring.length).coords[0]), np.array(ring.interpolate((t + 2) % ring.length).coords[0])
        v = b - a; nv = np.linalg.norm(v)
        if nv < 1e-6:
            continue
        nrm = np.array([v[1], -v[0]]) / nv
        k = streets_t.query_nearest(q); r = streets[int(k[0])].distance(q) if len(k) else 1e9
        ray = LineString([q.coords[0], tuple(np.array(q.coords[0]) + nrm * kc.D_MAX)])
        hits = [ray.intersection(truth[int(j)]) for j in truth_t.query(ray)]
        ds = [Point(q).distance(h) for h in hits if not h.is_empty]
        P.append(q.coords[0]); N.append(nrm); R.append(r); D.append(min(ds) if ds and min(ds) >= kc.D_MIN else np.nan)
    return np.array(P), np.array(N), np.array(R), np.array(D)


def finders(ground, P, N, R):
    ok = (R <= REACH) & np.isfinite(R)
    cands = kc.candidates(ground, P, N, R, ok)
    extra = {}
    strongest = np.full(len(P), np.nan)
    if ok.any() and ground.covers(P[ok]):
        t = np.arange(0.0, kc.D_MAX + 1.5, kpw.STEP_D)
        with np.errstate(all="ignore"):
            H = np.nanmedian(kpw.profiles(ground, P[ok], N[ok], t), axis=0)
        strongest[ok] = kpw.prof_positions(H, t, kc.D_MIN - kpw.P_SHIFT, kc.D_MAX - kpw.P_SHIFT) + kpw.P_SHIFT
    side = np.full(len(P), np.nan)
    for k in range(0, len(P), RUN):
        j = np.arange(k, min(k + RUN, len(P)))
        j = j[ok[j]]
        if len(j) >= 4 and (v := kpw.side_width(ground, P[j], N[j], float(np.median(R[j])))) is not None:
            side[j] = v
    out = {"strongest": strongest, "side": side}
    runs = kc.keep_runs(list(ok)) if ok.any() else []
    for name, cd in [("chain", cands)] + list(extra.items()):
        v = np.full(len(P), np.nan); vb = np.full(len(P), np.nan)
        for a, b in runs:
            idx = [(a + k) % len(P) for k in range(((b - a) % len(P)) + 1)]
            c = kc.kerb_chain([cd[i] for i in idx])
            v[idx] = c; vb[idx] = bridge(c)
        out[name] = v; out[name + "_bridged"] = vb
    out["chain_else_side"] = np.where(np.isfinite(out["chain_bridged"]), out["chain_bridged"], side)
    return out


def bridge(c):
    """Chain readings carried across gaps of up to kc.GAP_MAX samples between two readings (as kerbcds draws them)."""
    c = c.copy(); f = np.flatnonzero(np.isfinite(c))
    for a, b in zip(f[:-1], f[1:]):
        if 1 < b - a <= kc.GAP_MAX + 1:
            c[a + 1:b] = np.interp(np.arange(a + 1, b), [a, b], [c[a], c[b]])
    return c


def main(a):
    roads_d, lots_d, grids_d, council, epsg, out = a[:6]
    cells = None
    if "--cells" in a:
        cells = [tuple(map(int, l.split())) for l in open(a[a.index("--cells") + 1]) if l.strip()]
    roads = [r["g"] for r in kc.load_roads(roads_d) if r["fh"] in kc.STREET_FH]
    lots = kc.load_lots(lots_d); truth = truth_lines(council, epsg)
    ST, TT, ground = STRtree(roads), STRtree(truth), kpw.Ground(grids_d)
    acc = {}; n_truth = 0
    for x, y in cells:
        frame = box(x * 1000, y * 1000, x * 1000 + 1000, y * 1000 + 1000)
        if not len(TT.query(frame)) or ground.get(x, y) is None:
            continue
        for ring in fronts(lots, frame.buffer(150)):
            P, N, R, D = samples(ring, ST, roads, TT, truth)
            if not len(P):
                continue
            inside = shapely.contains_xy(frame, P[:, 0], P[:, 1]) & np.isfinite(D) & (R <= REACH)
            if not inside.any():
                continue
            F = finders(ground, P, N, R); n_truth += int(inside.sum())
            for k, v in F.items():
                acc.setdefault(k, []).append(np.c_[D[inside], v[inside]])
    res = {"truth_samples": n_truth}
    for k, parts in acc.items():
        A = np.vstack(parts) if parts else np.zeros((0, 2)); m = np.isfinite(A[:, 1]); e = A[m, 1] - A[m, 0]
        res[k] = {"answered": round(float(m.mean()), 3) if len(A) else 0,
                  "within_0.5": round(float((np.abs(e) <= 0.5).mean()), 3) if m.any() else None,
                  "within_1": round(float((np.abs(e) <= 1.0).mean()), 3) if m.any() else None,
                  "of_all_within_1": round(float((np.abs(e) <= 1.0).sum() / max(len(A), 1)), 3),
                  "median_err": round(float(np.median(e)), 2) if m.any() else None}
    json.dump(res, open(out, "w"), indent=1); print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
