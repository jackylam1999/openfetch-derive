#!/usr/bin/env python3
"""Kerb tracing pilot (4 Nov 2026, before an iCurb-style learned tracer): walk on from each end of a drawn kerb line, one STEP m at a
time, turning at most TURN degrees per step, to wherever the evidence is strongest. Evidence at a point = max(photo P, LiDAR step / FULL),
so where the model is blind the ground step can carry the trace. Stop after MISS weak steps in a row, after MAXLEN m, or on reaching
another drawn line (a bridged gap). No training: if this does not beat the base, a learned tracer has to see more than P and the step.

Usage (KERB_CFG as the scored model): python kerbtrace.py kp_dir long_dir thresh
  kp_dir holds <box>_derived_<thresh>.geojson (the round's lines), long_dir pc-16-1's <box>_P.npy (kerblong.py).
  Prints found / precise / F1 / added km per box for each variant, then the scenario score as the rounds report it.
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import compare_kerbs as ck
import kerbstep as ks
from shapely.geometry import LineString, Point, box as sbox
from shapely.strtree import STRtree
from affine import Affine

STEP, TURN, MISS, MAXLEN, MINLEN, FULL, JOIN = 1.0, 15, 3, 80.0, 5.0, 0.08, 1.5  # m, degrees, steps, m, m, m step = evidence 1, m
VARIANTS = [("e0.3", 0.3, False), ("e0.5", 0.5, False), ("e0.3 bridge", 0.3, True), ("e0.5 bridge", 0.5, True)]


class Ev:
    def __init__(self, P, trP, up, trU):
        self.P, self.iP = ndimage.maximum_filter(P, 3), ~trP
        self.U, self.iU = (ndimage.maximum_filter(up, 3), ~trU) if up is not None else (None, None)

    def at(self, xy):
        def get(G, inv):
            c, r = inv * (xy[:, 0], xy[:, 1]); r, c = r.astype(int), c.astype(int)
            ok = (r >= 0) & (c >= 0) & (r < G.shape[0]) & (c < G.shape[1])
            v = np.zeros(len(xy), np.float32); v[ok] = G[r[ok], c[ok]]; return v
        e = get(self.P, self.iP)
        return np.maximum(e, np.clip(get(self.U, self.iU) / FULL, 0, 1)) if self.U is not None else e


def walk(p, h, ev, at, tree, D, own, clip):
    """From point p heading h (radians): returns (points, reached another line)."""
    pts, weak, angs = [p], 0, np.radians(np.arange(-TURN, TURN + 1, 5))
    for _ in range(int(MAXLEN / STEP)):
        hs = h + angs; q = np.column_stack([pts[-1][0] + STEP * np.cos(hs), pts[-1][1] + STEP * np.sin(hs)])
        mid = (q + pts[-1]) / 2; s = (ev.at(q) + ev.at(mid)) / 2; k = int(np.argmax(s))
        if s[k] >= at:
            weak = 0; h = hs[k]
        else:  # weak: go straight on, give up after MISS steps
            weak += 1; k = len(angs) // 2
            if weak > MISS:
                return pts[:-MISS] if len(pts) > MISS else [p], False
        pts.append(q[k])
        if not clip.contains(Point(q[k])):
            return pts, False
        for j in tree.query(Point(q[k]).buffer(JOIN)):
            if j != own and D[j].distance(Point(q[k])) <= JOIN:
                return pts, True
    return pts, False


def trace(D, ev, at, bridge, clip):
    tree = STRtree(D); out = []
    for i, l in enumerate(D):
        if l.length < MINLEN:
            continue
        for a, b in ((l.coords[1], l.coords[0]), (l.coords[-2], l.coords[-1])):
            # heading from the last 2 m of the line
            t = l.project(Point(b)); c = l.interpolate(max(t - 2, 0) if t > 0 else min(2, l.length))
            h = np.arctan2(b[1] - c.y, b[0] - c.x)
            pts, hit = walk(np.array(b, float), h, ev, at, tree, D, i, clip)
            if len(pts) * STEP >= MINLEN and (hit or not bridge):
                out.append(LineString(pts))
    return out


def main():
    src, ld, th = sys.argv[1:4]; res = {}
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{ld}/{b[0]}_P.npy") and os.path.exists(f"{src}/{b[0]}_derived_{th}.geojson")]
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        trP = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        D, R = ck.lines(f"{src}/{nm}_derived_{th}.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        up, trU = (None, None)
        if os.path.exists(f"{src}/{nm}_dem.npy"):
            trU, up = ks.grids(src, nm, D)[:2]
        ev = Ev(P, trP, up, trU)
        res[nm] = {"base": (*ks.rate(D, R), 0.0)}
        for name, at, br in VARIANTS:
            new = trace(D, ev, at, br, clip)
            res[nm][name] = (*ks.rate(D + new, R), round(sum(l.length for l in new) / 1000, 2))
        print(nm, "LiDAR" if up is not None else "photo only", {k: (round(v[0], 3), round(v[1], 3), round(ks.f1(v), 3), v[2]) for k, v in res[nm].items()}, flush=True)
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    hold = [n for n in boxes if n in dict(h[:2] for h in kl.HOLD)]
    for k in res[boxes[0]]:
        print(k, "scenario score", round(float(np.mean([np.mean([ks.f1(res[n][k]) for n in v]) for v in by.values()])), 3),
              "worst held-out", round(min(ks.f1(res[n][k]) for n in hold), 3), "added km", round(sum(res[n][k][2] for n in boxes), 1), flush=True)


if __name__ == "__main__":
    main()
