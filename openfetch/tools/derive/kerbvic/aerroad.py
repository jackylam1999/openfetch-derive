"""Road surface read from the Vicmap aerial (Jacky 19 Nov 2026: "If tracing helps you can trace them too") as a footpath-width
measure for kerblot.py where no council ground model exists (the Merri-bek one, mbdem.py, goes first). A U-Net (unet.py, ResNet-34
encoder) trained on City of Melbourne's own carriageway, channel and kerb polygons (roadtrain.py) gives each 0.25 m cell of a 1 km
MGA55 square a road probability, stored as prob_dir/p_<x>_<y>.png (0-255, row 0 north). Along each lot-front sample's ray the kerb
is the first offset where the next metre is road; a side's width is the median of its samples, kept only when at least half read
and they agree (IQR at most AER_IQR). Held-out check 19 Nov 2026: Carlton rings 82% within 1 m of the council's kerbs (93% within
2 m), North Melbourne 82% (95%); OSM lines alone kept 3 and 2 blocks there, this 16 and 12.
    python3 aerroad.py predict prob_dir model.pt cells.txt     (CPU; the same squares the GPU notebook writes)"""
import os, sys
import numpy as np
from PIL import Image
RES, NEED, AER_IQR, DMIN, DMAX, M = 0.25, 0.5, 1.0, 0.75, 9.0, 64


class Road:
    def __init__(s, d):
        s.d, s.c = d, {}

    def cell(s, k):
        if k not in s.c:
            fn = os.path.join(s.d, f"p_{k[0]}_{k[1]}.png")
            s.c[k] = np.asarray(Image.open(fn)) if os.path.exists(fn) else None
        return s.c[k]

    def prob(s, X, Y):
        """road probability 0-1 at MGA55 points, NaN where no square is cached."""
        kx = np.floor(X / 1000).astype(int); ky = np.floor(Y / 1000).astype(int); out = np.full(X.shape, np.nan)
        for k in set(zip(kx.ravel().tolist(), ky.ravel().tolist())):
            a = s.cell(k)
            if a is None:
                continue
            m = (kx == k[0]) & (ky == k[1])
            c = np.clip(((X[m] - k[0] * 1000) / RES).astype(int), 0, a.shape[1] - 1); r = np.clip(((k[1] * 1000 + 1000 - Y[m]) / RES).astype(int), 0, a.shape[0] - 1)
            out[m] = a[r, c] / 255.0
        return out

    def side_width(s, P, N, reach_m):
        reach = float(np.nanmedian(reach_m))
        if not np.isfinite(reach) or reach < DMIN + 1.5:
            return None
        t = np.arange(0.25, min(reach + 1.0, DMAX + 1.0) + 1e-6, RES)
        v = s.prob(P[:, 0][:, None] + N[:, 0][:, None] * t[None, :], P[:, 1][:, None] + N[:, 1][:, None] * t[None, :])
        k = []
        for i in np.flatnonzero(np.isfinite(v).all(1)):
            run = np.convolve(v[i], np.ones(4) / 4, "full")[3:]
            j = np.flatnonzero((run > 0.5) & (t >= DMIN) & (t <= min(reach, DMAX)))
            if len(j):
                k.append(t[j[0]])
        if len(k) < max(4, NEED * len(P)):
            return None
        q1, q2, q3 = np.percentile(k, [25, 50, 75])
        return float(q2) if q3 - q1 <= AER_IQR else None


def predict_cells(out, model_p, cells_p):
    import torch
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from unet import UNet, predict
    from mosaic import mosaic
    torch.set_num_threads(4); os.makedirs(out, exist_ok=True)
    m = UNet(); m.load_state_dict(torch.load(model_p, map_location="cpu"))
    for l in open(cells_p):
        if not l.strip():
            continue
        x, y = map(int, l.split()); fn = os.path.join(out, f"p_{x}_{y}.png")
        if os.path.exists(fn):
            continue
        img = mosaic(x * 1000 - M, y * 1000 - M, x * 1000 + 1000 + M, y * 1000 + 1000 + M, RES, 19)
        p = predict(m, img)[int(M / RES):-int(M / RES), int(M / RES):-int(M / RES)]
        Image.fromarray((np.clip(p, 0, 1) * 255).round().astype(np.uint8)).save(fn); print(fn, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "predict":
        predict_cells(sys.argv[2], sys.argv[3], sys.argv[4])
