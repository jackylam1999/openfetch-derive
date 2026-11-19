"""Vicmap aerial (AERIAL_WM_256) resampled to an MGA55 grid. mosaic(x0, y0, x1, y1, res, z) -> (H, W, 3) uint8, row 0 = north."""
import io, os, urllib.request, numpy as np, concurrent.futures as cf, time
from PIL import Image
from pyproj import Transformer
R = 20037508.342789244
CACHE = os.environ.get("AER_CACHE", os.path.expanduser("~/.cache/openfetch-aerial"))
TOM = Transformer.from_crs(7855, 3857, always_xy=True).transform
def path(z, x, y): return f"{CACHE}/{z}_{x}_{y}.jpg"
def fetch(k):
    z, x, y = k; fn = path(z, x, y)
    if os.path.exists(fn): return
    u = f"https://base.maps.vic.gov.au/wmts/AERIAL_WM_256/EPSG:3857:256/{z}/{x}/{y}.png"
    for i in range(5):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "openfetch-derive"}), timeout=60).read()
            Image.open(io.BytesIO(b)).convert("RGB").save(fn, quality=92); return
        except Exception as e:
            if i == 4: print("fail", k, e, flush=True)
            time.sleep(2 * (i + 1))
def mosaic(x0, y0, x1, y1, res=0.25, z=19, workers=12):
    os.makedirs(CACHE, exist_ok=True)
    xs = x0 + (np.arange(int((x1 - x0) / res)) + 0.5) * res; ys = y1 - (np.arange(int((y1 - y0) / res)) + 0.5) * res
    size = 2 * R / 2 ** z; out = np.zeros((len(ys), len(xs), 3), np.uint8)
    for r0 in range(0, len(ys), 1024):
        X, Y = np.meshgrid(xs, ys[r0:r0 + 1024]); mx, my = TOM(X.ravel(), Y.ravel())
        fx = (mx + R) / size; fy = (R - my) / size; tx = np.floor(fx).astype(int); ty = np.floor(fy).astype(int)
        ks = sorted(set(zip(tx.tolist(), ty.tolist())))
        with cf.ThreadPoolExecutor(workers) as ex: list(ex.map(fetch, [(z, a, b) for a, b in ks]))
        px = np.clip(((fx - tx) * 256).astype(int), 0, 255); py = np.clip(((fy - ty) * 256).astype(int), 0, 255)
        o = np.zeros((X.size, 3), np.uint8); kk = tx.astype(np.int64) * 10**7 + ty
        order = np.argsort(kk, kind="stable"); kk_s = kk[order]; cuts = np.flatnonzero(np.diff(kk_s)) + 1
        for grp in np.split(order, cuts):
            a, b = tx[grp[0]], ty[grp[0]]; fn = path(z, a, b)
            if os.path.exists(fn): o[grp] = np.asarray(Image.open(fn))[py[grp], px[grp]]
        out[r0:r0 + 1024] = o.reshape(X.shape + (3,))
    return out
