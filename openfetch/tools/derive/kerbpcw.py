"""Footpath width from the LiDAR point cloud where no kerb trace exists (kerblot.py, 18 Nov 2026). Not a tracer: one width per
street side. Ground points (class 2) are gridded at 0.5 m per 1 km square; every front sample of a side gives a height profile
from the lot front out towards the street, and the median of the side's profiles (parked cars, bins and noise fall out, they
are not ground) shows the kerb as one clear step down of 6-35 cm. A side with no clear step is not measured (block left blank).
Since 19 Nov 2026 the kerb is first found in each profile on its own (a line fitted either side, so crossfall, camber and parked
cars do not hide it) and the side is measured when the profiles agree: the median profile smears the kerb where lot fronts jog.

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
LAST, SUPPORT = None, None
STEP_SUPPORT = 0.10   # share of profiles that must find their own kerb near the median-profile step (19 Nov 2026, 909 traced
                      # sides: sides off by over 1.5 m 80 -> 26, 676 kept); a smeared median shows a step where no profile has one
PROFILES = "--no-profiles" not in sys.argv
P_W, P_SLOPE, P_FLAT = 0.8, 0.10, 0.05   # m, slope, m: each side of a kerb in one profile: 80 cm, crossfall under 10 %, within 5 cm of a line
P_NMIN, P_HIT, P_SHARE, P_WIN = 4, 0.25, 0.7, 1.2   # the densest 1.2 m of the profiles' kerbs holds 4 profiles at least, a quarter of
                                                    # the side's profiles and 70 % of those that found a kerb
P_NEAR = 0.6     # m: a profile's kerb this near the median-profile step supports it
P_SHIFT = 0.25                           # m, per-profile kerb face to the LiDAR kerb traces (2,154 traced sides, 19 Nov 2026: kerblot --calib)
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


def prof_step(h, t, lo, hi):
    """(drop, distance) of the strongest kerb drop in one profile h(t), or None. Each side of the drop is fitted with a line, so a
    footpath with a steep crossfall or a road with camber still shows its kerb, and up to half a side may be missing (parked cars
    hide the gutter from the LiDAR). The drop is the gap between the two lines at the kerb face."""
    w = int(round(P_W / STEP_D)); r = int(round(DROP_RUN / STEP_D)); u = np.arange(w) * STEP_D
    best = None
    for e in range(max(w, int(lo / STEP_D)), min(len(t) - w - r, int(hi / STEP_D) + 1)):
        a, b = h[e - w:e], h[e + r:e + r + w]
        ma, mb = np.isfinite(a), np.isfinite(b)
        if ma.sum() < w / 2 or mb.sum() < w / 2:
            continue
        pa, pb = np.polyfit(u[ma], a[ma], 1), np.polyfit(u[mb], b[mb], 1)
        if max(abs(pa[0]), abs(pb[0])) > P_SLOPE:
            continue
        if np.ptp(a[ma] - np.polyval(pa, u[ma])) > P_FLAT or np.ptp(b[mb] - np.polyval(pb, u[mb])) > P_FLAT:
            continue
        drop = np.polyval(pa, P_W + DROP_RUN / 2) - np.polyval(pb, -DROP_RUN / 2)
        if DROP_MIN <= drop <= DROP_MAX and (best is None or drop > best[0]):
            best = (drop, t[e] + DROP_RUN / 2)
    return best


def prof_positions(H, t, lo, hi):
    """Kerb distance found in each profile on its own (nan where none)."""
    return np.asarray([np.nan if (s := prof_step(h, t, lo, hi)) is None else s[1] for h in H])


def prof_width(pos):
    """One width from the kerb found in each profile on its own (19 Nov 2026): the median profile of a side smears the kerb when
    the lot fronts jog or the footpath narrows along the street, so 334 inner-city blocks (Redfern, Waterloo, Kensington) had LiDAR
    ground but no width. The densest P_WIN m of the profiles' kerbs is the kerb when it holds P_HIT of all profiles and P_SHARE of
    those that found one (a driveway, tree pit or path edge in a few profiles does not move it); otherwise None."""
    ok = np.sort(pos[np.isfinite(pos)])
    if len(ok) < P_NMIN:
        return None
    j = np.searchsorted(ok, ok + P_WIN, side="right")
    i = int(np.argmax(j - np.arange(len(ok))))
    n = j[i] - i
    if n < max(P_NMIN, P_HIT * len(pos)) or n < P_SHARE * len(ok):
        return None
    return float(np.median(ok[i:j[i]]))


def support(pos, d):
    """Share of a side's profiles whose own kerb lies within P_NEAR of width d (both on the traces' footing)."""
    return float(np.mean(np.abs(pos + P_SHIFT - d) <= P_NEAR)) if len(pos) else 0.0


def profiles(ground, P, N, t):
    """Ground heights (lateral line, sample, t) out from each front sample, each relative to its own lot front (streets slope)."""
    T = np.c_[N[:, 1], -N[:, 0]]
    prof = []
    for lat in LAT:
        X = P[:, 0, None] + N[:, 0, None] * t + T[:, 0, None] * lat
        Y = P[:, 1, None] + N[:, 1, None] * t + T[:, 1, None] * lat
        prof.append(ground.height(X, Y))
    H = np.stack(prof)
    with np.errstate(all="ignore"):
        return H - np.nanmedian(H[:, :, :5], axis=2, keepdims=True)


def side_width(ground, P, N, reach, dmin=1.0, dmax=7.0):
    """Footpath width of one street side (on the LiDAR kerb traces' footing), or None. The kerb found profile by profile comes
    first, then the step in the median profile when one profile in ten or more agrees with it. On 2,186 sides with a LiDAR kerb
    trace (19 Nov 2026, kerblot --calib): 1,049 measured, 92 % within 0.75 m, 3.2 % over 1.5 m off; the step alone was 1,149,
    85 % and 7.1 %."""
    global LAST, SUPPORT
    LAST, SUPPORT = None, None
    if len(P) < 4 or not ground.covers(P):
        return None
    t = np.arange(0.0, min(reach, dmax + 1.5), STEP_D)
    H = profiles(ground, P, N, t)
    with np.errstate(all="ignore"):
        pos = prof_positions(np.nanmedian(H, axis=0), t, dmin - P_SHIFT, dmax - P_SHIFT) if PROFILES else np.asarray([])
        h = np.nanmedian(H.reshape(-1, len(t)), axis=0)
    v = prof_width(pos) if PROFILES else None
    if v is not None and dmin <= v + P_SHIFT <= dmax:
        LAST = "lidar profiles"
        return v + P_SHIFT
    d = step_in(h, t, dmin, dmax) if np.isnan(h).mean() <= 0.3 else None
    if d is None or not dmin <= d + SHIFT <= dmax:
        return None
    SUPPORT = support(pos, d + SHIFT)
    if PROFILES and SUPPORT < STEP_SUPPORT:
        return None
    LAST = "lidar step"
    return d + SHIFT


def selftest():
    t = np.arange(0, 9, STEP_D)
    h = np.where(t < 3.2, 0.0, -0.15) - 0.01 * t           # 3.2 m footpath, 15 cm kerb, gentle crossfall
    assert abs(step_in(h, t, 1.0, 7.0) - 3.2) < 0.25, step_in(h, t, 1.0, 7.0)
    assert step_in(-0.02 * t, t, 1.0, 7.0) is None         # a slope with no step
    h2 = np.where(t < 2.0, 0.0, -0.15) + np.where(t < 5.0, 0.0, -0.15)
    assert step_in(h2, t, 1.0, 7.0) is None                # two steps: not clear
    h3 = np.where(t < 2.4, 0.0, -0.12) - 0.05 * t           # 5 % crossfall on the footpath, 12 cm kerb (the flat test refuses it)
    h3[30:34] = np.nan                                      # a parked car hides part of the road
    s3 = prof_step(h3, t, 1.0, 7.0)
    assert s3 is not None and abs(s3[1] - 2.4) < 0.25 and abs(s3[0] - 0.12) < 0.04, s3
    pos = np.r_[np.full(6, 2.0), np.full(4, np.nan)]
    assert prof_width(pos) == 2.0 and prof_width(np.r_[2.0, 2.1, np.full(8, np.nan)]) is None   # too few profiles agree
    assert prof_width(np.r_[1.2, 1.3, 3.0, 3.1, 1.2, 3.0]) is None                               # two kerbs: they disagree
    assert prof_width(np.r_[np.full(8, 2.0), 4.5, np.full(2, np.nan)]) == 2.0                     # one stray reading does not move it
    assert abs(support(np.r_[2.0, 2.1, 5.0, np.nan], 2.0 + P_SHIFT) - 0.5) < 1e-9
    print("kerbpcw selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    if a and a[0] == "grid":
        print(make_grid(a[4:], int(a[2]), int(a[3]), a[1]))
