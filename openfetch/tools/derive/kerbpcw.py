"""Footpath width from the LiDAR point cloud where no kerb trace exists (kerblot.py, 18 Nov 2026). Not a tracer: one width per
street side. Ground points (class 2) are gridded at 0.5 m per 1 km square; every front sample of a side gives a height profile
from the lot front out towards the street, and the median of the side's profiles (parked cars, bins and noise fall out, they
are not ground) shows the kerb as one clear step down of 6-35 cm. A side with no clear step is not measured (block left blank).

    python3 kerbpcw.py grid <out_dir> <x> <y> file.laz [...]     ground grid for 1 km square x_y (MGA56 km numbers)
    python3 kerbpcw.py --selftest
"""
import os, sys
import numpy as np

RES = 0.5   # ground points are about 4 per m2: a 0.5 m cell holds one or two
STEP_D = 0.1
LAT = (-0.75, 0.0, 0.75)
DROP_MIN, DROP_MAX, DROP_RUN = 0.06, 0.35, 0.4   # m: a kerb face drops 6-35 cm within 40 cm
SHIFT = 0.35     # m: the step's median sits 0.35 m nearer the lot than the LiDAR kerb traces (502 sides in MGA 334_6246-6247,
                 # 285 measured, 84 % within 0.75 m of that offset; 18 Nov 2026), so widths are put on the traces' footing
FLAT = 0.07      # m: the 60 cm either side of the step must each be flat within this (a ramp or slope is not a kerb)


def make_grid(paths, x, y, out):
    import laspy
    n = int(1000 / RES)
    s, c = np.zeros((n, n)), np.zeros((n, n))
    x0, y0 = x * 1000.0, y * 1000.0
    for p in paths:
        with laspy.open(p) as f:
            for ch in f.chunk_iterator(2_000_000):
                k = np.asarray(ch.classification) == 2
                X, Y, Z = np.asarray(ch.x)[k], np.asarray(ch.y)[k], np.asarray(ch.z)[k]
                i = ((X - x0) / RES).astype(int); j = ((Y - y0) / RES).astype(int)
                m = (i >= 0) & (i < n) & (j >= 0) & (j < n)
                np.add.at(s, (j[m], i[m]), Z[m]); np.add.at(c, (j[m], i[m]), 1)
    g = np.where(c > 0, s / np.maximum(c, 1), np.nan).astype(np.float32)
    np.savez_compressed(os.path.join(out, f"{x}_{y}.npz"), g=g, x0=x0, y0=y0)
    return float(np.isfinite(g).mean())


class Ground:
    def __init__(self, d):
        self.d, self.mem = d, {}

    def get(self, i, j):
        if (i, j) not in self.mem:
            fn = os.path.join(self.d, f"{i}_{j}.npz")
            self.mem[(i, j)] = np.load(fn)["g"] if os.path.exists(fn) else None
        return self.mem[(i, j)]

    def height(self, X, Y):
        out = np.full(X.shape, np.nan, dtype=np.float32)
        I, J = np.floor(X / 1000).astype(int), np.floor(Y / 1000).astype(int)
        n = int(1000 / RES)
        for i, j in set(zip(I.ravel().tolist(), J.ravel().tolist())):
            g = self.get(i, j)
            if g is None:
                continue
            m = (I == i) & (J == j)
            c = ((X[m] - i * 1000) / RES).astype(int).clip(0, n - 1)
            r = ((Y[m] - j * 1000) / RES).astype(int).clip(0, n - 1)
            out[m] = g[r, c]
        return out

    def covers(self, P):
        return all(self.get(int(x // 1000), int(y // 1000)) is not None for x, y in P[:: max(1, len(P) // 5)])


def step_in(h, t, dmin, dmax):
    """Distance of the one clear kerb step in a median profile h(t), or None."""
    w = int(round(0.6 / STEP_D)); r = int(round(DROP_RUN / STEP_D))
    cands = []
    for e in range(max(w, int(dmin / STEP_D)), min(len(t) - w - r, int(dmax / STEP_D) + 1)):
        a, b = h[e - w:e], h[e + r:e + r + w]
        if np.isnan(a).any() or np.isnan(b).any():
            continue
        drop = np.median(a) - np.median(b)
        if DROP_MIN <= drop <= DROP_MAX and np.ptp(a) <= FLAT and np.ptp(b) <= FLAT:
            seg = h[e:e + r + 1]
            k = int(np.argmax(-np.diff(seg))) if len(seg) > 1 else 0
            cands.append((drop, t[e + k]))
    if not cands:
        return None
    best = max(c[0] for c in cands)
    pos = [p for d, p in cands if d >= best - 0.02]
    if max(pos) - min(pos) > 0.6:
        return None   # two different steps: not clear
    return float(np.median(pos))


def side_width(ground, P, N, reach, dmin=1.0, dmax=7.0):
    if len(P) < 4 or not ground.covers(P):
        return None
    t = np.arange(0.0, min(reach, dmax + 1.5), STEP_D)
    T = np.c_[N[:, 1], -N[:, 0]]
    prof = []
    for lat in LAT:
        X = P[:, 0, None] + N[:, 0, None] * t + T[:, 0, None] * lat
        Y = P[:, 1, None] + N[:, 1, None] * t + T[:, 1, None] * lat
        prof.append(ground.height(X, Y))
    H = np.stack(prof)                                   # lat, sample, t
    H = H - np.nanmedian(H[:, :, :5], axis=2, keepdims=True)   # each profile relative to its own lot front (streets slope)
    with np.errstate(all="ignore"):
        h = np.nanmedian(H.reshape(-1, len(t)), axis=0)
    if np.isnan(h).mean() > 0.3:
        return None
    d = step_in(h, t, dmin, dmax)
    return None if d is None or not dmin <= d + SHIFT <= dmax else d + SHIFT


def selftest():
    t = np.arange(0, 9, STEP_D)
    h = np.where(t < 3.2, 0.0, -0.15) - 0.01 * t           # 3.2 m footpath, 15 cm kerb, gentle crossfall
    assert abs(step_in(h, t, 1.0, 7.0) - 3.2) < 0.25, step_in(h, t, 1.0, 7.0)
    assert step_in(-0.02 * t, t, 1.0, 7.0) is None         # a slope with no step
    h2 = np.where(t < 2.0, 0.0, -0.15) + np.where(t < 5.0, 0.0, -0.15)
    assert step_in(h2, t, 1.0, 7.0) is None                # two steps: not clear
    print("kerbpcw selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    if a and a[0] == "grid":
        print(make_grid(a[4:], int(a[2]), int(a[3]), a[1]))
