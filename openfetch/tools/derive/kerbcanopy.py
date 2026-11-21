"""Kerbs under tree canopy (scenario 10, 21 Nov 2026). Under trees the aerial cannot show the kerb and the LiDAR ground points that
reach the road are fewer (74 % of canopy cells hold no ground point against 48 % in the open, tile 3126252) and darker (ground
returns that are not the only return: median intensity 10 against 15), so the intensity road edge and the reviewer both lose it.
This tool grids a LAZ tile into one canopy-aware grid per 1 km cell (0.5 m cells, the LAZ's own coordinates, which are the GDA2020
MGA56 frame even where the header says GDA94: datum card, P-0244):
    h  ground height (float32, nan = no ground point)          io / iu  mean intensity of open-sky / under-canopy ground returns
    v  canopy: a vegetation point (class 3-5) 2 m or more above the ground in the cell
and draws the LiDAR panel a reviewer needs beside the aerial (hillshade of the ground, asphalt dark, canopy outlined).

    python3 kerbcanopy.py grid <out_dir> file.laz [...]
    python3 kerbcanopy.py --selftest
"""
import os, sys
import numpy as np

RES, N = 0.5, 2000
NOG = 255
NO_SHIFT = (0.0, 0.0)   # m: the grids are read unshifted. 28 GDA94-headed tiles measured in the GDA2020 frame against true centrelines
# (datum card, P-0244). A 0.48 E / 1.42 N slip seen against Parramatta and Canterbury-Bankstown kerb truth was in those council files
# (GDA94 numbers served as 7856 / 4326), never in the LiDAR: read council truth through its registry datum entry


def grid(paths, out):
    import laspy
    acc = {}
    for p in paths:
        with laspy.open(p) as f:
            for ch in f.chunk_iterator(4_000_000):
                X, Y, Z = np.asarray(ch.x), np.asarray(ch.y), np.asarray(ch.z)
                C = np.asarray(ch.classification); NR = np.asarray(ch.number_of_returns); I = np.asarray(ch.intensity).astype(np.float64)
                ci, cj = (X // 1000).astype(int), (Y // 1000).astype(int)
                for a, b in set(zip(ci.tolist(), cj.tolist())):
                    m = (ci == a) & (cj == b)
                    k = ((((Y[m] - b * 1000) / RES).astype(int).clip(0, N - 1)) * N + ((X[m] - a * 1000) / RES).astype(int).clip(0, N - 1))
                    A = acc.setdefault((a, b), {q: np.zeros(N * N) for q in ("hs", "hc", "io", "co", "iu", "cu", "vz")})
                    c, nr, z, i = C[m], NR[m], Z[m], I[m]
                    g = c == 2
                    A["hs"] += np.bincount(k[g], z[g], N * N); A["hc"] += np.bincount(k[g], None, N * N)
                    o, u = g & (nr == 1), g & (nr > 1)
                    A["io"] += np.bincount(k[o], i[o], N * N); A["co"] += np.bincount(k[o], None, N * N)
                    A["iu"] += np.bincount(k[u], i[u], N * N); A["cu"] += np.bincount(k[u], None, N * N)
                    v = (c >= 3) & (c <= 5)
                    np.maximum.at(A["vz"], k[v], z[v])
    for (a, b), A in acc.items():
        with np.errstate(all="ignore"):
            h = np.where(A["hc"] > 0, A["hs"] / A["hc"], np.nan).astype(np.float32)
            io = np.where(A["co"] > 0, np.clip(np.round(A["io"] / A["co"]), 0, NOG - 1), NOG).astype(np.uint8)
            iu = np.where(A["cu"] > 0, np.clip(np.round(A["iu"] / A["cu"]), 0, NOG - 1), NOG).astype(np.uint8)
        fn = os.path.join(out, f"{a}_{b}.npz")
        if os.path.exists(fn) and np.isfinite(np.load(fn)["h"]).sum() >= (A["hc"] > 0).sum():
            continue   # a neighbour tile's few edge points must not overwrite the cell's own tile (igrid.py did, 25 KB cells)
        hf = fill(h)
        v = (A["vz"] > 0) & (A["vz"] - hf >= 2.0)
        np.savez_compressed(fn, h=h.reshape(N, N), io=io.reshape(N, N), iu=iu.reshape(N, N),
                            v=np.packbits(v.reshape(N, N)), frame="LAZ coordinates (GDA2020 MGA56 frame, P-0244)")
        print(a, b, flush=True)


def fill(h):
    """Ground height with holes filled from the nearest ground cell (for heights above ground and the hillshade)."""
    from scipy.ndimage import distance_transform_edt
    H = h.reshape(N, N) if h.ndim == 1 else h
    bad = ~np.isfinite(H)
    if bad.all():
        return np.zeros(H.size)
    idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
    return H[tuple(idx)].ravel()


def load(path):
    d = np.load(path)
    return dict(h=d["h"], io=d["io"], iu=d["iu"], v=np.unpackbits(d["v"])[: N * N].reshape(N, N).astype(bool))


class Grids:
    """Canopy-aware grids of a folder, read at GDA2020 MGA56 points (the frame kerblot and the review crops use)."""

    def __init__(self, d, frame_shift=NO_SHIFT):
        self.d, self.sh, self.mem = d, frame_shift, {}

    def cell(self, i, j):
        if (i, j) not in self.mem:
            fn = os.path.join(self.d, f"{i}_{j}.npz")
            if os.path.exists(fn):
                g = load(fn); g["hf"] = fill(g["h"]).reshape(N, N); self.mem[(i, j)] = g
            else:
                self.mem[(i, j)] = None
        return self.mem[(i, j)]

    def sample(self, key, X, Y):
        """Values of grid key at GDA2020 points (nan where no grid; 'io'/'iu' 255 = no ground point stays 255)."""
        X = np.asarray(X, float) - self.sh[0]; Y = np.asarray(Y, float) - self.sh[1]
        out = np.full(X.shape, np.nan)
        I, J = np.floor(X / 1000).astype(int), np.floor(Y / 1000).astype(int)
        for i, j in set(zip(I.ravel().tolist(), J.ravel().tolist())):
            g = self.cell(i, j)
            if g is None:
                continue
            k = (I == i) & (J == j)
            c = ((X[k] - i * 1000) / RES).astype(int).clip(0, N - 1); r = ((Y[k] - j * 1000) / RES).astype(int).clip(0, N - 1)
            out[k] = g[key][r, c]
        return out


def panel(G, cx, cy, size=60.0, px=720):
    """LiDAR panel (PIL RGB) centred on GDA2020 MGA (cx, cy), north up like the aerial crop: ground hillshade (kerb steps show as
    thin light/dark lines) times ground brightness (asphalt dark), canopy edge in green, no-ground cells left grey. None with no grid."""
    from PIL import Image
    xs = cx - size / 2 + (np.arange(px) + 0.5) * size / px
    ys = cy + size / 2 - (np.arange(px) + 0.5) * size / px
    X, Y = np.meshgrid(xs, ys)
    pad = 2.0
    xg = np.arange(cx - size / 2 - pad, cx + size / 2 + pad, RES) + RES / 2
    yg = np.arange(cy + size / 2 + pad, cy - size / 2 - pad, -RES) - RES / 2
    XG, YG = np.meshgrid(xg, yg)
    H = G.sample("hf", XG, YG)
    if np.isnan(H).all():
        return None
    H = np.where(np.isfinite(H), H, np.nanmedian(H))
    dy, dx = np.gradient(H, RES)
    az, alt = np.radians(315), np.radians(35)
    hs = np.sin(alt) + np.cos(alt) * (np.cos(az) * -dy * 6 + np.sin(az) * -dx * 6)
    hs = hs / np.sqrt(1 + 36 * (dx * dx + dy * dy))
    I = G.sample("io", XG, YG); U = G.sample("iu", XG, YG)
    I = np.where(I < 255, I, np.where(U < 255, U * 1.3, np.nan))
    from scipy.ndimage import gaussian_filter
    ok = np.isfinite(I)
    w = gaussian_filter(ok.astype(float), 1.0); s = gaussian_filter(np.where(ok, I, 0.0), 1.0)
    br = np.where(w > 0.15, s / np.maximum(w, 1e-6), np.nan)
    br = np.clip((br - 3) / 30.0, 0.08, 1.0)
    V = G.sample("v", XG, YG) > 0.5
    base = np.clip(0.35 + 0.65 * hs, 0, 1) * np.where(np.isfinite(br), 0.25 + 0.75 * br, 0.55)
    from scipy.ndimage import binary_dilation
    hole = ~binary_dilation(np.isfinite(G.sample("h", XG, YG)), iterations=2)   # roofs and dense cover: no ground within 1 m
    base = np.where(hole, 0.62, base)
    rgb = np.dstack([base, base, base])
    from scipy.ndimage import binary_erosion
    edge = V & ~binary_erosion(V, iterations=1)
    rgb[edge] = [0.1, 0.8, 0.2]
    gi = ((yg[0] - Y) / RES).astype(int).clip(0, len(yg) - 1); gj = ((X - xg[0]) / RES).astype(int).clip(0, len(xg) - 1)
    return Image.fromarray((rgb[gi, gj] * 255).astype(np.uint8))


def selftest():
    import tempfile
    h = np.full((N, N), np.nan, np.float32)
    h[:, :1000] = 10.0; h[:, 1000:] = 10.15                      # a 150 mm kerb step at x = 500 m, road (dark) to the west
    io = np.full((N, N), 30, np.uint8); io[:, :1000] = 8; io[::2, ::3] = NOG
    v = np.zeros((N, N), bool); v[995:1010, 995:1010] = True       # a 7.5 m tree over the kerb
    with tempfile.TemporaryDirectory() as d:
        np.savez_compressed(os.path.join(d, "300_6200.npz"), h=h, io=io, iu=np.full((N, N), NOG, np.uint8), v=np.packbits(v))
        G = Grids(d)
        x = np.array([300499.0, 300501.0, 299999.0]); y = np.full(3, 6200500.0)
        assert list(G.sample("h", x, y)[:2]) == [np.float32(10.0), np.float32(10.15)] and np.isnan(G.sample("h", x, y)[2])
        assert G.sample("v", np.array([300500.0]), np.array([6200500.0]))[0] == 1
        im = panel(G, 300500.0, 6200500.0, 20.0, 200)
        a = np.asarray(im).astype(int)
        assert im.size == (200, 200) and a[100, 20].sum() < a[100, 180].sum(), "asphalt west of the kerb must draw darker"
        assert (a[:, :, 1] > a[:, :, 0] + 100).any(), "canopy edge drawn"
        assert panel(G, 290000.0, 6200500.0) is None
    print("kerbcanopy selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        selftest()
    elif sys.argv[1] == "grid":
        os.makedirs(sys.argv[2], exist_ok=True); grid(sys.argv[3:], sys.argv[2])
