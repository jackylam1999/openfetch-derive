#!/usr/bin/env python3
"""Long misses: stretches over 40 m with neither kerb of the street drawn are the largest share of what the model misses (3 Nov 2026).
Did the model see them faintly, or not at all? That decides between a cheap fix and a new kerb tracing model.

Usage (KERB_CFG with context 1, lidar 1, tta 1):  python kerblong.py kp_dir model.pt lines_dir thresh long_dir
For each NSW check and held-out box: makes the kerb probability once (long_dir/<box>_P.npy), then reports
  seen     share of missed length by the strongest probability within 1 m, split by the length of the missed stretch
  grow     scores when weak pixels (low, high) are kept only if joined to a strong line: found and precise as the same bar as the rounds
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
from shapely.geometry import box as sbox

LOWS = (0.2, 0.3, 0.4, 0.5)


def probs(src, model, ld, nm):
    p = f"{ld}/{nm}_P.npy"
    if os.path.exists(p):
        return np.load(p).astype(np.float32) / 255
    if not hasattr(probs, "net"):
        probs.net = kl.model(False); kl.load(probs.net, model); probs.net = probs.net.to(kl.DEV()).eval()
    m, tr, rgb, lot, lab, road = kl.labels(src, nm)
    P = kl.prob(probs.net, rgb, kl.inputs(src, nm, lot), kl.inside(src, nm, lab.shape[0], tr), 1)
    np.save(p, np.rint(P * 255).astype(np.uint8))
    return P


def seen(P, tr, D, R):
    """km of missed council kerb per (stretch length, strongest P within 1 m)."""
    inv = ~tr; M = ndimage.maximum_filter(P, 21); out = {}
    for l in R:
        ts = np.arange(0.25, l.length, 0.5)
        if not len(ts):
            continue
        xy = np.array([l.interpolate(t).coords[0] for t in ts]); miss = ck.dist(xy, D) > 1
        c, r = inv * (xy[:, 0], xy[:, 1]); v = M[np.clip(r.astype(int), 0, P.shape[0] - 1), np.clip(c.astype(int), 0, P.shape[1] - 1)]
        i = 0
        while i < len(xy):
            if not miss[i]:
                i += 1; continue
            j = i
            while j + 1 < len(xy) and miss[j + 1]:
                j += 1
            L = (j - i + 1) * 0.5; run = "<10 m" if L < 10 else "10-40 m" if L <= 40 else ">40 m"
            for x in v[i:j + 1]:
                b = "P<0.1" if x < 0.1 else "P 0.1-0.3" if x < 0.3 else "P 0.3-0.5" if x < 0.5 else "P>=0.5"
                out[(run, b)] = out.get((run, b), 0) + 0.0005
            i = j + 1
    return out


def rate(D, R):
    ds, rs = ck.samples(D), ck.samples(R); dd, rd = ck.dist(ds, R), ck.dist(rs, D)
    return float((rd <= 1).mean()), float((dd <= 1).mean())


def f1(v):
    return 2 * v[0] * v[1] / max(v[0] + v[1], 1e-6)


def main():
    src, model, lines, th, ld = sys.argv[1:6]; os.makedirs(ld, exist_ok=True); high = float(th)
    res, tot = {}, {}
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{src}/{b[0]}_dem.npy")]
    for nm in boxes:
        m, tr, rgb, lot, lab, road = kl.labels(src, nm); P = probs(src, model, ld, nm); clip = sbox(*json.load(open(f"{src}/{nm}_meta.json"))["box"])
        D, R = ck.lines(f"{lines}/{nm}_derived_{th}.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        for k, v in seen(P, tr, D, R).items():
            tot[k] = tot.get(k, 0) + v
        res[nm] = {"base": rate(D, R)}
        for low in LOWS:
            lb, n = ndimage.label(P >= low, np.ones((3, 3)))
            keep = np.unique(lb[P >= high]); G = np.where(np.isin(lb, keep[keep > 0]), np.maximum(P, high), P)
            kp.vec(ld, nm, G, tr, high)
            res[nm][str(low)] = rate(ck.lines(f"{ld}/{nm}_derived.geojson", clip), R)
        print(nm, {k: (round(v[0], 3), round(v[1], 3), round(f1(v), 3)) for k, v in res[nm].items()}, flush=True)
    print("missed km by stretch and strongest probability:")
    for k, v in sorted(tot.items()):
        print(" ", k, round(v, 2))
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    for c in ("base", *map(str, LOWS)):
        print(c, "scenario score", round(float(np.mean([np.mean([f1(res[n][c]) for n in v]) for v in by.values()])), 3))
    json.dump({"boxes": res, "seen": {"/".join(k): v for k, v in tot.items()}}, open(f"{ld}/long.json", "w"), indent=1)


if __name__ == "__main__":
    main()
