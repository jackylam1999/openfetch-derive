#!/usr/bin/env python3
"""Short misses (kerbshort.py, 3 Nov 2026): of 7.5 km missed in stretches up to 40 m with P >= 0.5 nearby, 6.2 km has the mask (P >= cut)
within 1 m but the traced line over 1 m away: the skeleton runs down the middle of a wide blob, not along the kerb. Try tracing the
ridge instead: keep only mask cells within FRAC of the strongest P in a WIN x WIN window (0.2 m cells), then trace as usual.
Usage (KERB_CFG as the scored model): python kerbridge.py kp_dir long_dir thresh out_dir
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
from shapely.geometry import mapping, box as sbox
from affine import Affine
from kerbstep import rate, f1

VARIANTS = [("base", 0, 0)] + [(f"{w}/{f}", w, f) for w in (5, 9, 15) for f in (0.8, 0.9)]


def main():
    src, ld, th, od = sys.argv[1:5]; th = float(th); os.makedirs(od, exist_ok=True); res = {}
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{ld}/{b[0]}_P.npy")]
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"]); R = ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        tr = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        P2 = P.reshape(P.shape[0] // 2, 2, P.shape[1] // 2, 2).max((1, 3)); tr2 = tr * Affine.scale(2); res[nm] = {}
        for k, w, f in VARIANTS:
            mask = P2 >= th
            if w:
                mask &= P2 >= f * ndimage.maximum_filter(P2, w)
            ls = kp.vectorise(mask, tr2)
            json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(l)} for l in ls]},
                      open(f"{od}/{nm}_{k.replace('/', '_')}.geojson", "w"))
            res[nm][k] = rate(ck.lines(f"{od}/{nm}_{k.replace('/', '_')}.geojson", clip), R)
        print(nm, {k: (round(v[0], 3), round(v[1], 3), round(f1(v), 3)) for k, v in res[nm].items()}, flush=True)
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    hold = [n for n in boxes if n in dict(h[:2] for h in kl.HOLD)]
    for k, *_ in VARIANTS:
        print(k, "scenario score", round(float(np.mean([np.mean([f1(res[n][k]) for n in v]) for v in by.values()])), 3),
              "worst held-out", round(min(f1(res[n][k]) for n in hold), 3), "better boxes", sum(f1(res[n][k]) > f1(res[n]["base"]) for n in boxes), flush=True)
    json.dump(res, open(f"{od}/ridge.json", "w"), indent=1)


if __name__ == "__main__":
    main()
