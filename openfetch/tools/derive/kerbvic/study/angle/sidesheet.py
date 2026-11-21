"""sidesheet.py sides.json cls out.jpg [n] : aerial crops of sides of one class, kerb reads as dots (red), lot front (cyan)"""
import json, sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/w/derive/openfetch/tools/derive/kerbvic")
from mosaic import mosaic
from PIL import Image, ImageDraw
S = json.load(open(sys.argv[1])); ids = json.load(open(sys.argv[1].replace(".json", ".cls.json")))[sys.argv[2]]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 6; rng = np.random.default_rng(1); ids = sorted(rng.choice(ids, min(n, len(ids)), replace=False).tolist())
tiles = []
for i in ids:
    s = S[i]; P = np.array(s["P"]); N = np.array(s["N"]); c = P.mean(0); sz = 70
    x0, y1 = c[0] - sz / 2, c[1] + sz / 2
    im = Image.fromarray(mosaic(x0, c[1] - sz / 2, c[0] + sz / 2, y1, 0.25, 19)); d = ImageDraw.Draw(im)
    px = lambda q: ((q[0] - x0) / .25, (y1 - q[1]) / .25)
    for p in P: u, v = px(p); d.ellipse([u - 2, v - 2, u + 2, v + 2], fill="cyan")
    V = np.array(s["prof"]); t = s["t0"] + .25 * np.arange(V.shape[1])
    for p, nn, v in zip(P, N, V):
        run = np.convolve(v, np.ones(4) / 4, "full")[3:]; far = np.array([np.median(v[q:q + 10]) for q in range(len(t))])
        j = np.flatnonzero((run > .5) & (far > .5) & (t >= .75))
        if len(j): u, w = px(p + nn * t[j[0]]); d.ellipse([u - 3, w - 3, u + 3, w + 3], fill="red")
    d.text((4, 4), f"side {i}", fill="yellow"); tiles.append(im)
W = 3; h = (len(tiles) + W - 1) // W; out = Image.new("RGB", (280 * W, 280 * h), "white")
for k, im in enumerate(tiles): out.paste(im, (280 * (k % W), 280 * (k // W)))
out.save(sys.argv[3], quality=80); print(ids)
