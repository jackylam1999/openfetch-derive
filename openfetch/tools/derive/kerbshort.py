#!/usr/bin/env python3
"""Short misses the model sees (kerbs-lidar-rounds.md NEXT 3): 7.2 km of council kerb missed in stretches up to 40 m has P >= 0.5 within
1 m but no line within 1 m. Where is it lost? For each such sample, the first that holds:
  dropped   a raw traced piece (before kerbtidy and MIN_LEN) is within 1 m: the tidy step or the length cut threw it away
  off       the mask (P >= thresh) is within 1 m but the traced line is not: the line runs down the middle of a wide blob
  under     P is 0.5 up to thresh there: the cut is too high for it
Usage (KERB_CFG as the scored model): python kerbshort.py kp_dir long_dir thresh out_dir
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
from shapely.geometry import box as sbox
from affine import Affine


def main():
    src, ld, th, od = sys.argv[1:5]; th = float(th); os.makedirs(od, exist_ok=True); tot = {}
    for nm in [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{ld}/{b[0]}_P.npy")]:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        tr = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        P2 = P.reshape(P.shape[0] // 2, 2, P.shape[1] // 2, 2).max((1, 3)); tr2 = tr * Affine.scale(2); mask = P2 >= th
        keep, kp.MIN_LEN = kp.MIN_LEN, 0; raw = kl._trace(mask, tr2); kp.MIN_LEN = keep; kp.vec(od, nm, P, tr, th)
        D, R = ck.lines(f"{od}/{nm}_derived.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        Pm, Mm = ndimage.maximum_filter(P2, 11), ndimage.maximum_filter(mask, 11)  # within 1 m on the 0.2 m grid
        inv = ~tr2; out = {}
        for l in R:
            ts = np.arange(0.25, l.length, 0.5)
            if not len(ts):
                continue
            xy = np.array([l.interpolate(t).coords[0] for t in ts]); miss = ck.dist(xy, D) > 1
            c, r = inv * (xy[:, 0], xy[:, 1]); r, c = np.clip(r.astype(int), 0, P2.shape[0] - 1), np.clip(c.astype(int), 0, P2.shape[1] - 1)
            i = 0
            while i < len(xy):
                if not miss[i]:
                    i += 1; continue
                j = i
                while j + 1 < len(xy) and miss[j + 1]:
                    j += 1
                L = (j - i + 1) * 0.5
                if L <= 40:
                    s = slice(i, j + 1); seen = Pm[r[s], c[s]] >= 0.5
                    if seen.any():
                        dr = ck.dist(xy[s][seen], raw) <= 1 if raw else np.zeros(seen.sum(), bool)
                        mm = Mm[r[s], c[s]][seen]
                        cat = np.where(dr, "dropped", np.where(mm, "off", "under"))
                        run = "<10 m" if L < 10 else "10-40 m"
                        for k in cat:
                            out[(run, k)] = out.get((run, k), 0) + 0.0005
                i = j + 1
        print(nm, {"/".join(k): round(v, 2) for k, v in sorted(out.items())}, flush=True)
        for k, v in out.items():
            tot[k] = tot.get(k, 0) + v
    print("km of short misses with P >= 0.5 nearby, by where they are lost:")
    for k, v in sorted(tot.items()):
        print(" ", k, round(v, 2))


if __name__ == "__main__":
    main()
