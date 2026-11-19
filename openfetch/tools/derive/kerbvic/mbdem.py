"""Merri-bek 2023 LiDAR ground (council's public tile service, ~0.94 m cells, heights in 5 cm steps) as a footpath-width measure
for Brunswick and Coburg: no kerb step survives at this cell size, but the gutter does, as the lowest line between the lot front
and the road crown. Per street side, the median profile of the side's front samples puts the gutter, and the kerb sits GUT_K
nearer the lot than the gutter's low cell.
    python3 mbdem.py fetch out_dir lon0 lat0 lon1 lat1      (tiles, level 17)
"""
import json, math, os, sys, urllib.request
import numpy as np
from pyproj import Transformer
SVC = "https://tiles.arcgis.com/tiles/8L5sOwfzTAvcvQur/arcgis/rest/services/merribek_Elevation_2023jul25_dem50cm_v10cm_epsg28355_tif/ImageServer"
Z = 17
GUT_K = 0.55         # m from the gutter's low cell to the kerb line (Brunswick: 0.3 left the gutter widths 0.30 m wider than the OSM ones)
PROF = 0.25          # m between profile points
NEED = 6             # profiles a side needs
REL_DEEP, REL_NEED, REL_IQR, REL_SHIFT = 0.03, 0.4, 1.0, 0.3
DIP = 0.04           # m: the gutter sits at least this far below both the footpath and the road crown in the median profile


def tile_xy(lon, lat, z=Z):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)


def fetch(out, lon0, lat0, lon1, lat1):
    import lerc
    os.makedirs(out, exist_ok=True)
    x0, y1 = tile_xy(lon0, lat0); x1, y0 = tile_xy(lon1, lat1)
    got = 0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            fn = os.path.join(out, f"{x}_{y}.npy")
            if os.path.exists(fn):
                continue
            try:
                b = urllib.request.urlopen(urllib.request.Request(f"{SVC}/tile/{Z}/{y}/{x}", headers={"User-Agent": "openfetch-derive"}), timeout=60).read()
            except Exception:
                continue
            r = lerc.decode(b)
            d = np.asarray(r[1], dtype=np.float32)
            if r[2] is not None and np.asarray(r[2]).shape == d.shape:
                d[np.asarray(r[2]) == 0] = np.nan
            np.save(fn, d); got += 1
    return got


class Dem:
    """Heights at MGA55 points from the cached tiles (bilinear on the web-mercator grid; a tile is 256 cells + 1 overlap)."""
    def __init__(self, d):
        self.d, self.c = d, {}
        self.to = Transformer.from_crs(7855, 3857, always_xy=True).transform
        self.R = 20037508.342789244

    def side_width(self, P, N, C):
        return side_width(self, P, N, C)

    def tile(self, x, y):
        k = (x, y)
        if k not in self.c:
            fn = os.path.join(self.d, f"{x}_{y}.npy")
            self.c[k] = np.load(fn) if os.path.exists(fn) else None
        return self.c[k]

    def height(self, X, Y):
        mx, my = self.to(np.asarray(X, float), np.asarray(Y, float))
        n = 2 ** Z; size = 2 * self.R / n
        fx = (mx + self.R) / size; fy = (self.R - my) / size
        tx, ty = np.floor(fx).astype(int), np.floor(fy).astype(int)
        out = np.full(np.shape(fx), np.nan)
        for k in set(zip(tx.ravel().tolist(), ty.ravel().tolist())):
            t = self.tile(*k)
            if t is None:
                continue
            m = (tx == k[0]) & (ty == k[1]); cells = t.shape[0] - 1
            u = (fx[m] - k[0]) * cells - 0.5; v = (fy[m] - k[1]) * cells - 0.5
            i0 = np.clip(np.floor(u).astype(int), 0, t.shape[1] - 2); j0 = np.clip(np.floor(v).astype(int), 0, t.shape[0] - 2)
            a, b = np.clip(u - i0, 0, 1), np.clip(v - j0, 0, 1)
            out[m] = (t[j0, i0] * (1 - a) * (1 - b) + t[j0, i0 + 1] * a * (1 - b) + t[j0 + 1, i0] * (1 - a) * b + t[j0 + 1, i0 + 1] * a * b)
        return out


def side_width(dem, P, N, reach_m, dmin=1.0, dmax=7.0):
    """Kerb distance from the lot front for one side (P points, N outward normals, reach_m: how far out the road crown may lie,
    half the reserve; Vicmap centrelines are metres off), or None. The gutter is the deepest valley of the side's median profile:
    lower by DIP than the highest point between it and the footpath and than the crown beyond it (a street lying higher or lower
    than its lots tilts the profile, so the valley, not the lowest point, is the gutter)."""
    reach = float(np.nanmedian(reach_m))
    if not np.isfinite(reach) or reach < dmin + GUT_K + 1.0:
        return None
    t = np.arange(0.0, reach + 1e-6, PROF)
    X = P[:, 0][:, None] + N[:, 0][:, None] * t[None, :]; Y = P[:, 1][:, None] + N[:, 1][:, None] * t[None, :]
    H = dem.height(X, Y)
    H = H - np.nanmedian(H[:, (t >= 0.3) & (t <= 1.0)], axis=1)[:, None]
    ok = np.isfinite(H).all(axis=1)
    if ok.sum() < NEED:
        return None
    prof = np.median(H[ok], axis=0)
    foot = t >= 0.3
    best, bi = 0.0, -1
    for i in np.flatnonzero((t >= dmin + GUT_K) & (t <= min(dmax + GUT_K, reach - 0.75))):
        left = prof[foot & (t < t[i])].max(); right = prof[i:].max()
        depth = min(left, right) - prof[i]
        if depth > best + 1e-6:
            best, bi = depth, i
    if bi < 0 or best < DIP:
        return relief_width(dem, P, N, reach)
    return float(t[bi] - GUT_K)


def relief_width(dem, P, N, reach, dmin=1.0, dmax=7.0):
    """Fallback where the median profile shows no valley (a street lying higher or lower than its lots, a road crown under 4 cm):
    each front sample's own profile minus its 10 m running mean (tilt and crown taken out) puts the gutter at its deepest point,
    at least REL_DEEP deep; the side's samples must agree (middle half within REL_IQR). Brunswick: measures 243 of 313 sides
    (the valley 197), within 1 m of the OSM width on 86 %, and of the valley on 99 %; it sits REL_SHIFT nearer the lot."""
    if reach < dmin + 1.5:
        return None
    half = 5.0
    t = np.arange(-half, reach + half + 1e-6, PROF)
    H = dem.height(P[:, 0][:, None] + N[:, 0][:, None] * t[None, :], P[:, 1][:, None] + N[:, 1][:, None] * t[None, :])
    k = int(half / PROF); w = np.ones(2 * k + 1) / (2 * k + 1)
    win = np.flatnonzero((t >= dmin + GUT_K) & (t <= min(dmax + GUT_K, reach - 0.75)))
    if not len(win):
        return None
    vals = []
    for h in H:
        if not np.isfinite(h).all():
            continue
        rel = h - np.convolve(h, w, mode="same")
        i = win[np.argmin(rel[win])]
        if rel[i] <= -REL_DEEP:
            vals.append(t[i] - GUT_K + REL_SHIFT)
    if len(vals) < max(NEED, REL_NEED * len(P)):
        return None
    q1, q2, q3 = np.percentile(vals, [25, 50, 75])
    return float(q2) if q3 - q1 <= REL_IQR else None


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        print("tiles", fetch(sys.argv[2], *map(float, sys.argv[3:7])))
