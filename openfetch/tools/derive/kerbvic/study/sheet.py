import json, os, sys, random, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic"); import mbdem
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
R, rings_p, out = sys.argv[1], sys.argv[2], sys.argv[3]; k = int(sys.argv[4]) if len(sys.argv) > 4 else 12; seed = int(sys.argv[5]) if len(sys.argv) > 5 else 1
dem = mbdem.Dem(R + "/dem"); F = json.load(open(rings_p))["features"]; random.seed(seed); pick = random.sample(F, min(k, len(F)))
AT = [tuple(map(float, l.split())) for l in open(os.environ["AT"])] if os.environ.get("AT") else None
if AT:
    from shapely.geometry import shape as _sh, Point as _P
    from shapely.ops import transform as _tf
    G = [(_tf(TO, _sh(f["geometry"])), f) for f in F]
    pick = [min(G, key=lambda g: g[0].distance(_P(*a)))[1] for a in AT]
lots = json.load(open(R + "/lots/lots.json"))["features"]
sw = [np.array([TO(*p) for p in f["geometry"]["coordinates"]]) for f in json.load(open(R + "/sidewalks.geojson"))["features"]]
import os
os.makedirs(out, exist_ok=True); tag = sys.argv[6] if len(sys.argv) > 6 else "x"
for n, f in enumerate(pick):
    fig, ax = plt.subplots(1, 1, figsize=(7, 7))
    c = np.array([TO(*p) for p in f["geometry"]["coordinates"]]); cx, cy = c.mean(axis=0)
    # a 70 m window on one ring corner region (close-up): centre on a random vertex
    vx, vy = AT[n] if AT else c[random.randrange(len(c))]; h = 35
    xs = np.arange(vx - h, vx + h, 0.5); ys = np.arange(vy - h, vy + h, 0.5); X, Y = np.meshgrid(xs, ys)
    Z = dem.height(X.ravel(), Y.ravel()).reshape(X.shape)
    gy, gx = np.gradient(Z, 0.5); hs = np.clip(0.5 + (gx - gy) * 2.5, 0, 1)
    from scipy.ndimage import uniform_filter
    rel = Z - uniform_filter(np.nan_to_num(Z, nan=np.nanmean(Z)), 21)
    ax.imshow(np.clip(rel, -0.15, 0.15), cmap="RdBu_r", extent=(xs[0], xs[-1], ys[0], ys[-1]), origin="lower", alpha=0.9)
    for L in lots:
        g = L["geometry"]; polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for p in polys:
            a = np.array(p[0])
            if abs(a[:, 0].mean() - vx) < 80 and abs(a[:, 1].mean() - vy) < 80: ax.plot(a[:, 0], a[:, 1], color="k", lw=0.4)
    for a in sw:
        if abs(a[:, 0].mean() - vx) < 120 and abs(a[:, 1].mean() - vy) < 120: ax.plot(a[:, 0], a[:, 1], color="#0a0", lw=0.8, ls="--")
    ax.plot(c[:, 0], c[:, 1], color="#f0f", lw=1.6); ax.set_xlim(vx - h, vx + h); ax.set_ylim(vy - h, vy + h); ax.set_aspect("equal")
    ax.set_title(f"{tag}{n + 1:02d}: magenta = our kerb; blue = low ground (gutters); black = lot lines; green dashed = OSM path. 70 m across", fontsize=7)
    ax.set_xticks([]); ax.set_yticks([]); plt.tight_layout(); plt.savefig(os.path.join(out, f"{tag}{n + 1:02d}.png"), dpi=80); plt.close(fig)
    open(os.path.join(out, "key.txt"), "a").write(f"{tag}{n + 1:02d} {f['properties']['id']} {vx:.1f} {vy:.1f}\n")
