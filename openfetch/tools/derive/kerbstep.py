#!/usr/bin/env python3
"""LiDAR kerb-step detector (kerbs-lidar-rounds.md NEXT 2): a second judge for the long stretches the model does not see. Of the missed
length in stretches > 40 m, 78% has P < 0.1 within 1 m, yet the LiDAR ground shows a median 7 cm step across the council kerb there.
No training, CPU only. On the 0.25 m ground grid, away from drawn lines, keep cells where the ground steps UP by smin-25 cm over 1 m
going away from the official road centreline, with flat ground either side and at the strongest point of that step, then draw lines
through them and keep pieces that run along the centreline.

Usage (KERB_CFG as the scored model):  python kerbstep.py kp_dir long_dir thresh step_dir
  long_dir holds pc-16-1's <box>_P.npy (kerblong.py); base lines are redrawn from it at thresh, so the base is the round's score.
  Prints found / precise / F1 / added km per box for each (smin, min length), and the scenario score as the rounds report it.
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
from shapely.geometry import shape, mapping, box as sbox
from affine import Affine

G, H = 0.25, 2  # grid m; half the step span in cells (step measured over 1 m)
BAND = (2.0, 15.0)  # m from the road centreline where a kerb can be
AWAY = 1.5  # m: only look this far from any drawn line
SMIN, LMIN = (0.04, 0.06, 0.08), (5, 10, 20)
SMAX, ANG = 0.25, 0.42  # m; |sin| of the largest angle between a piece and the centreline
W, FLAT, LOTPAD, DIAG = 6, 3.0, None, False  # profile +-1.5 m; step >= FLAT x leftover roughness; lots deeper than LOTPAD m out (None: off)


def burn(path, n, tr, lines=False):
    import rasterio.features as rf
    fs = [shape(f["geometry"]) for f in json.load(open(path))["features"] if f.get("geometry")] if os.path.exists(path) else []
    return rf.rasterize(((g, 1) for g in fs), out_shape=(n, n), transform=tr, all_touched=lines, dtype=np.uint8) > 0 if fs \
        else np.zeros((n, n), bool)


def grids(src, nm, D):
    """Step up across the road (m), flatness, the unit normal away from the centreline and the cells allowed to hold a new kerb."""
    dem = np.load(f"{src}/{nm}_dem.npy").astype(np.float32); n = dem.shape[0]; x0, y0 = kl.BX[nm]
    tr = Affine(G, 0, x0, 0, -G, y0 + n * G)
    m = np.isfinite(dem); w = ndimage.gaussian_filter(m.astype(np.float32), 1.5)  # as kl.steps: fill 0.25 m gaps
    z = ndimage.gaussian_filter(np.where(m, dem, 0), 1.5) / np.maximum(w, 1e-6); z[w < 0.05] = np.nan
    cl = burn(f"{src}/{nm}_roads.geojson", n, tr, True)
    dist, (ri, ci) = ndimage.distance_transform_edt(~cl, return_indices=True)
    rr, cc = np.mgrid[:n, :n].astype(np.float32); nr, nc = (rr - ri) / np.maximum(dist, 1e-6), (cc - ci) / np.maximum(dist, 1e-6)
    del ri, ci
    # Zhou & Vosselman 2012 style: across the road, fit ground = a + b k + h [k > 0] on a 3 m profile; h is the step, and it must
    # explain the profile much better than a plain slope (hills and road crossfall are slopes, a kerb is a jump)
    ks = np.arange(-W, W + 1); X = np.stack([np.ones(len(ks)), ks, (ks > 0).astype(float)], 1); Pi = np.linalg.pinv(X)
    up = np.zeros((n, n), np.float32); Z = []
    for i, k in enumerate(ks):
        Z.append(ndimage.map_coordinates(z, [rr + k * nr, cc + k * nc], order=1, cval=np.nan).astype(np.float32)); up += Pi[2, i] * Z[-1]
    fit = [sum(Pi[j, i] * Z[i] for i in range(len(ks))) for j in (0, 1)]
    rss = sum((Z[i] - fit[0] - fit[1] * k - up * (k > 0)) ** 2 for i, k in enumerate(ks)); del Z, fit
    flat = np.sqrt(rss / (len(ks) - 3)) * FLAT  # leftover roughness; a kerb step stands well above it
    peak = (up >= ndimage.map_coordinates(up, [rr + nr, cc + nc], order=0, cval=0)) & \
           (up >= ndimage.map_coordinates(up, [rr - nr, cc - nc], order=0, cval=0))
    drawn = burn_lines(D, n, tr)
    parts = {"band": (dist * G >= BAND[0]) & (dist * G <= BAND[1]), "notwater": ~burn(f"{src}/{nm}_water.geojson", n, tr),
             "inside": kl.inside(src, nm, n, tr), "away": ndimage.distance_transform_edt(~drawn) * G > AWAY, "peak": peak,
             "notmax": up <= SMAX, "flat": flat <= up}
    if LOTPAD is not None:  # council kerbs often sit inside the lot layer (road lots): only deep inside a lot is ruled out
        parts["notlot"] = ~ndimage.binary_erosion(burn(f"{src}/{nm}_lots.geojson", n, tr), iterations=int(LOTPAD / G))
    ok = np.logical_and.reduce(list(parts.values()))
    tr_, up_ = tr, np.nan_to_num(up)
    if DIAG:
        return tr_, up_, ok, nr, nc, parts
    return tr_, up_, ok, nr, nc


def burn_lines(D, n, tr):
    import rasterio.features as rf
    return rf.rasterize(((g, 1) for g in D), out_shape=(n, n), transform=tr, all_touched=True, dtype=np.uint8) > 0 if D \
        else np.zeros((n, n), bool)


def along(l, tr, nr, nc):
    """True when the piece runs along the centreline: small angle between it and the line perpendicular to the normal."""
    a, b = np.array(l.coords[0]), np.array(l.coords[-1]); d = b - a; k = np.hypot(*d)
    if not k:
        return False
    c, r = ~tr * tuple(l.interpolate(0.5, normalized=True).coords[0]); r, c = int(np.clip(r, 0, nr.shape[0] - 1)), int(np.clip(c, 0, nr.shape[1] - 1))
    # the normal (row, col) in map axes is (east = col, north = -row)
    return abs(d[0] / k * nc[r, c] - d[1] / k * nr[r, c]) <= ANG


def rate(D, R):
    ds, rs = ck.samples(D), ck.samples(R); dd, rd = ck.dist(ds, R), ck.dist(rs, D)
    return float((rd <= 1).mean()), float((dd <= 1).mean())


def f1(v):
    return 2 * v[0] * v[1] / max(v[0] + v[1], 1e-6)


def main():
    src, ld, th, sd = sys.argv[1:5]; os.makedirs(sd, exist_ok=True)
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{src}/{b[0]}_dem.npy") and os.path.exists(f"{ld}/{b[0]}_P.npy")]
    res = {}
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        trP = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"])
        kp.vec(sd, nm, np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255, trP, float(th))
        D, R = ck.lines(f"{sd}/{nm}_derived.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        tr, up, ok, nr, nc = grids(src, nm, D); res[nm] = {"base": rate(D, R)}
        for s in SMIN:
            mask = ndimage.binary_dilation(ok & (up >= s))
            ls = [l for l in kp.vectorise(mask, tr) if along(l, tr, nr, nc)]
            for L in LMIN:
                ins = [p for g in ls if g.length >= L for q in [g.intersection(clip)] for p in getattr(q, "geoms", [q]) if p.geom_type == "LineString" and p.length > 0]
                k = f"{s}/{L}"; res[nm][k] = (*rate(D + ins, R), round(sum(l.length for l in ins) / 1000, 2))
                json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in ins]},
                          open(f"{sd}/{nm}_step_{s}_{L}.geojson", "w"))
        print(nm, {k: (round(v[0], 3), round(v[1], 3), round(f1(v), 3), *v[2:]) for k, v in res[nm].items()}, flush=True)
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    for k in res[boxes[0]]:
        hold = [f1(res[n][k]) for n in boxes if n in dict(h[:2] for h in kl.HOLD)]
        print(k, "scenario score", round(float(np.mean([np.mean([f1(res[n][k]) for n in v]) for v in by.values()])), 3),
              "worst held-out", round(min(hold), 3), "added km", round(sum(res[n][k][2] for n in boxes) if k != "base" else 0, 1), flush=True)
    json.dump(res, open(f"{sd}/step.json", "w"), indent=1)


if __name__ == "__main__":
    main()
