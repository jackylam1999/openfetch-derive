#!/usr/bin/env python3
"""Learned kerb tracer (iCurb-style, Xu et al. RA-L 2021; plan in docs/handoffs/kerbs-lidar-rounds.md NEXT 7). The rule pilot
(kerbtrace.py) reached kerbs the pixel model misses but stopped and turned by hand-made rules, so about half of what it traced was
not kerb. Here a small CNN looks at a crop turned to the heading (photo, pc-16-1 P, LiDAR, lots, centreline distance, the path so
far) and predicts the turn for the next STEP m and whether to stop. Teacher = council kerb lines of the training boxes.

  prep  kp_dir model.pt tdir [box ...]   per box: P (pc-16-1, as kerblong.py) and a 0.2 m uint8 stack tdir/<box>_S.npy
  check tdir kp_dir box                  sample states, print teacher labels and timing (no training)
(train / dagger / eval come after the review's go-ahead.)
Stack channels: R G B, P, lot, centreline distance (0.1 m steps to 25 m), water, LiDAR height-vs-median, slope, has-LiDAR.
"""
import sys, os, json, time
import numpy as np
from scipy import ndimage
from affine import Affine
from shapely.geometry import Point, box as sbox
from shapely.ops import linemerge
from shapely.strtree import STRtree
import kerblearn as kl
import compare_kerbs as ck

G = 0.2                      # stack cell, m
CROP, AHEAD = 80, 4.0        # crop cells (16 m square), crop centre this far ahead of the point
STEP, LOOK, NEAR = 1.0, 3.0, 1.5  # m per step, teacher look-ahead along the kerb, off-kerb distance that means stop
BINS = np.radians(np.arange(-30, 31, 5))  # turn classes
NCH = 10


def prep(src, model, td, names):
    import kerblong
    os.makedirs(td, exist_ok=True)
    for nm in names:
        p = f"{td}/{nm}_S.npy"
        if os.path.exists(p):
            continue
        t0 = time.time()
        P = kerblong.probs(src, model, td, nm)  # tdir/<box>_P.npy, 0.1 m
        m, tr, rgb, lot, lab, road = kl.labels(src, nm)
        inp = kl.inputs(src, nm, lot)  # lot, rd, water, rel, slope, has
        n = (rgb.shape[0] // 2) * 2; k = n // 2
        S = np.lib.format.open_memmap(p + ".tmp.npy", "w+", np.uint8, (k, k, NCH))
        for r0 in range(0, n, 2000):  # in bands, so a box never sits in memory whole
            r1 = min(r0 + 2000, n); h = (r1 - r0) // 2
            def half(a, f=np.mean):
                a = np.asarray(a[r0:r1, :n], np.float32); return f(a.reshape(h, 2, k, 2, *a.shape[2:]), axis=(1, 3))
            S[r0 // 2:r1 // 2, :, 0:3] = np.rint(half(rgb))
            S[r0 // 2:r1 // 2, :, 3] = np.rint(half(P, np.max) * 255)
            S[r0 // 2:r1 // 2, :, 4] = np.rint(half(lot) * 255)
            S[r0 // 2:r1 // 2, :, 5:10] = np.rint(half(inp[..., 1:6]) * np.array([1, 255, 1, 1, 255], np.float32)).clip(0, 255)
        S.flush(); del S; os.replace(p + ".tmp.npy", p)
        json.dump({"x0": m["x0"], "y0": m["y0"] + m["w"], "box": m["box"]}, open(f"{td}/{nm}_S.json", "w"))
        print(nm, "prep", round(time.time() - t0), "s", flush=True)


class Box:
    """One box's stack, council kerbs (the teacher) and crop sampler."""
    def __init__(self, td, src, nm):
        j = json.load(open(f"{td}/{nm}_S.json")); self.nm = nm
        self.S = np.load(f"{td}/{nm}_S.npy", mmap_mode="r"); self.inv = ~Affine(G, 0, j["x0"], 0, -G, j["y0"])
        self.clip = sbox(*j["box"])
        R = ck.lines(f"{src}/{nm}_kerbs.geojson", self.clip); mg = linemerge(R)
        self.R = list(mg.geoms) if hasattr(mg, "geoms") else [mg]; self.tree = STRtree(self.R)
        self.len = np.cumsum([l.length for l in self.R])

    def crop(self, p, h, path=()):
        """CROP x CROP x NCH+1 float32 turned so the heading points up; last channel = the path so far."""
        f, s = np.array([np.cos(h), np.sin(h)]), np.array([np.sin(h), -np.cos(h)])  # forward, right
        u = AHEAD + (CROP / 2 - 0.5 - np.arange(CROP)) * G; v = (np.arange(CROP) - CROP / 2 + 0.5) * G
        xy = p + u[:, None, None] * f + v[None, :, None] * s
        c, r = self.inv * (xy[..., 0], xy[..., 1])
        r0, c0 = int(max(r.min() - 2, 0)), int(max(c.min() - 2, 0)); r1, c1 = int(r.max() + 3), int(c.max() + 3)
        W = np.asarray(self.S[r0:r1, c0:c1], np.float32)
        out = np.zeros((NCH + 1, CROP, CROP), np.float32)
        if W.size:
            for i in range(NCH):
                out[i] = ndimage.map_coordinates(W[..., i], [r - r0, c - c0], order=1, cval=0)
        out[:NCH] /= 255; out[5] *= 255 / 250
        for q in path[-12:]:  # mark the last 12 path points
            d = np.asarray(q) - p; a, b = d @ f, d @ s
            i, k = int(round((CROP / 2 - 0.5) - (a - AHEAD) / G)), int(round(b / G + CROP / 2 - 0.5))
            if 0 <= i < CROP and 0 <= k < CROP:
                out[NCH, max(i - 1, 0):i + 2, max(k - 1, 0):k + 2] = 1
        return out

    def teach(self, p, h):
        """(turn class, stop): turn toward the council kerb LOOK m further along, or stop when no kerb is within NEAR m or it ends."""
        P = Point(p); i = self.tree.nearest(P); l = self.R[i]
        if l.distance(P) > NEAR:
            return 0, 1
        t = l.project(P); a, b = l.interpolate(max(t - 0.5, 0)), l.interpolate(min(t + 0.5, l.length))
        tg = np.array([b.x - a.x, b.y - a.y]); sg = 1 if tg @ [np.cos(h), np.sin(h)] >= 0 else -1
        t2 = t + sg * LOOK
        if t2 < -0.5 or t2 > l.length + 0.5:
            return 0, 1
        q = l.interpolate(min(max(t2, 0), l.length)); d = np.arctan2(q.y - p[1], q.x - p[0]) - h
        d = (d + np.pi) % (2 * np.pi) - np.pi
        if abs(d) > np.radians(60):
            return 0, 1
        return int(np.argmin(abs(BINS - d))), 0

    def on_kerb(self, rng):
        """A state near a council kerb: point jittered across it, heading jittered off it, path = the kerb behind it."""
        i = int(np.searchsorted(self.len, rng.random() * self.len[-1])); l = self.R[i]
        t = rng.random() * l.length; sg = rng.choice([-1, 1])
        a, b = l.interpolate(max(t - 0.5, 0)), l.interpolate(min(t + 0.5, l.length))
        h = np.arctan2(b.y - a.y, b.x - a.x) + (0 if sg > 0 else np.pi)
        off = np.clip(rng.normal(0, 0.5), -1.4, 1.4); n = np.array([np.sin(h), -np.cos(h)])
        p = np.array(l.interpolate(t).coords[0]) + off * n; h += np.radians(rng.normal(0, 10))
        path = [np.array(l.interpolate(t - sg * k).coords[0]) + off * n for k in range(12, 0, -1) if 0 <= t - sg * k <= l.length]
        return p, h, path


def check(td, src, nm):
    bx = Box(td, src, nm); rng = np.random.default_rng(0); t0 = time.time(); ys = []
    for _ in range(200):
        p, h, path = bx.on_kerb(rng); x = bx.crop(p, h, path); ys.append(bx.teach(p, h))
    ys = np.array(ys)
    print(nm, "kerb km", round(bx.len[-1] / 1000, 1), "ms/state", round((time.time() - t0) * 5, 1), "stop share", ys[:, 1].mean(),
          "turn classes", np.bincount(ys[ys[:, 1] == 0, 0], minlength=len(BINS)), "crop mean per channel", x.mean((1, 2)).round(2))
    np.save(f"{td}/{nm}_crop_check.npy", x)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prep":
        prep(a[1], a[2], a[3], a[4:] or [b[0] for b in kl.TRAIN + kl.VAL + kl.HOLD])
    elif a[0] == "check":
        check(a[1], a[2], a[3])
