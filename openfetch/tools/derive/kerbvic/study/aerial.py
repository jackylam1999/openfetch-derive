"""Vic aerial (Vicmap Basemaps AERIAL_WM_256, look-only for review, Jacky 19 Nov 2026) resampled onto an MGA55 window."""
import io, math, os, urllib.request, numpy as np
from PIL import Image
from pyproj import Transformer
R = 20037508.342789244; Z = 20; CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aerial_cache")
TOM = Transformer.from_crs(7855, 3857, always_xy=True).transform
def tile(x, y):
    os.makedirs(CACHE, exist_ok=True); fn = os.path.join(CACHE, f"{Z}_{x}_{y}.png")
    if not os.path.exists(fn):
        u = f"https://base.maps.vic.gov.au/wmts/AERIAL_WM_256/EPSG:3857:256/{Z}/{x}/{y}.png"
        open(fn, "wb").write(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "openfetch-derive review"}), timeout=60).read())
    return np.asarray(Image.open(fn).convert("RGB"))
def window(x0, y0, x1, y1, res=0.15):
    xs = np.arange(x0, x1, res); ys = np.arange(y0, y1, res); X, Y = np.meshgrid(xs, ys)
    mx, my = TOM(X.ravel(), Y.ravel()); size = 2 * R / 2 ** Z
    fx = (mx + R) / size; fy = (R - my) / size; tx = np.floor(fx).astype(int); ty = np.floor(fy).astype(int)
    out = np.zeros((X.size, 3), np.uint8)
    for k in set(zip(tx.tolist(), ty.tolist())):
        m = (tx == k[0]) & (ty == k[1]); t = tile(*k)
        out[m] = t[np.clip(((fy[m] - k[1]) * 256).astype(int), 0, 255), np.clip(((fx[m] - k[0]) * 256).astype(int), 0, 255)]
    return out.reshape(X.shape + (3,)), (xs[0], xs[-1], ys[0], ys[-1])
