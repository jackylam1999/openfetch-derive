#!/usr/bin/env python3
"""Gap-repair net (kerbs-lidar-rounds.md NEXT 3, after Batra et al. CVPR 2019): a small second network learns to finish broken kerb
lines. 46% of the missed kerb length sits in stretches up to 40 m, and kerbfill.py (both ends seen, along a lot frontage) added
nothing on real output. Trained only on council kerbs with pieces cut out, so it never sees the photo model's output.

Usage (KERB_CFG with context 1 and lidar 1):
  python kerbgap.py cache kp_dir gap_dir           (0.4 m rasters per NSW box with LiDAR)
  python kerbgap.py train gap_dir minutes
  python kerbgap.py test kp_dir gap_dir lines_dir thresh   (reads <box>_derived_<thresh>.geojson; prints old and repaired scores)

Input (0.4 m cells): kerb lines, lot mask, distance to the road centreline, LiDAR height step, slope, has-LiDAR. Output: the whole kerb.
Only pieces that touch a drawn line are added, so the net can finish a line but not start one.
"""
import sys, os, json, glob, time
import numpy as np
from scipy import ndimage
import kerblearn as kl
import kerbphoto as kp
import compare_kerbs as ck
from shapely.geometry import mapping, box as sbox

K, CELL, CHIP = 4, 0.4, 256
TOUCH, MIN_NEW = 2.5, 3.0  # m: a new piece must come this close to a drawn line, and be at least this long


def cache(a):
    src, gd = a; os.makedirs(gd, exist_ok=True)
    for nm, *_ in kl.TRAIN + kl.NEW + kl.VAL + kl.HOLD:
        p = f"{gd}/{nm}.npz"
        if os.path.exists(p) or not os.path.exists(f"{src}/{nm}_dem.npy"):
            continue
        m, tr, rgb, lot, lab, road = kl.labels(src, nm)
        inp = kl.inputs(src, nm, lot); n = lab.shape[0] // K * K
        kb = (lab[:n, :n] == 3).reshape(n // K, K, n // K, K).max((1, 3))
        np.savez_compressed(p, kerb=kb, x=np.asarray(inp[:n:K, :n:K][..., [0, 1, 3, 4, 5]]), seen=lab[:n:K, :n:K] > 0)
        print(nm, kb.shape, kb.sum(), flush=True)


def net_():
    import torch
    from torch import nn

    def blk(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(True), nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(True))

    class U(nn.Module):
        def __init__(s, w=32):
            super().__init__()
            c = [w, w * 2, w * 4, w * 8, w * 8]
            s.d = nn.ModuleList([blk(6, c[0])] + [blk(c[i], c[i + 1]) for i in range(4)])
            s.u = nn.ModuleList([blk(c[i + 1] + c[i], c[i]) for i in range(4)])
            s.o = nn.Conv2d(w, 1, 1)

        def forward(s, x):
            f = []
            for i, d in enumerate(s.d):
                x = d(x if i == 0 else nn.functional.max_pool2d(x, 2)); f.append(x)
            for i in range(3, -1, -1):
                x = s.u[i](torch.cat([nn.functional.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False), f[i]], 1))
            return s.o(x)
    return U()


def stack(line, x):
    return np.stack([line.astype(np.float32), x[..., 0] > 0, x[..., 1] / 250, x[..., 2] / 255, x[..., 3] / 255, x[..., 4] / 255], 0).astype(np.float32)


def cut(rng, k):
    """Kerb chip with pieces hidden the way the photo model loses them: 1-6 holes 4-80 m wide (a third are wide), small shifts and a few
    false dashes. Returns the broken chip and the mask of what was hidden."""
    r, c = np.nonzero(k); g = np.ones(k.shape, bool); yy, xx = np.ogrid[:k.shape[0], :k.shape[1]]
    for _ in range(rng.integers(1, 7)):
        if len(r):
            i = rng.integers(len(r)); rad = np.exp(rng.uniform(np.log(2), np.log(40))) / CELL
            g &= (yy - r[i]) ** 2 + (xx - c[i]) ** 2 > rad ** 2
    b = np.roll(k & g, rng.integers(-1, 2, 2), (0, 1))
    for _ in range(rng.integers(0, 4)):
        p, q = rng.integers(10, k.shape[0] - 10, 2); d = rng.uniform(0, np.pi); s = rng.integers(5, 30)
        t = np.arange(s); rr = np.clip((p + t * np.sin(d)).astype(int), 0, k.shape[0] - 1); cc = np.clip((q + t * np.cos(d)).astype(int), 0, k.shape[1] - 1)
        b[rr, cc] = True
    return b, k & ~g


def train(a):
    import torch
    gd, minutes = a[0], float(a[1]); rng = np.random.default_rng(7); torch.manual_seed(7)
    names = [t[0] for t in kl.TRAIN + kl.NEW if os.path.exists(f"{gd}/{t[0]}.npz")]
    D = [(lambda z: (z["kerb"], z["x"], z["seen"], np.argwhere(z["kerb"])))(np.load(f"{gd}/{nm}.npz")) for nm in names]
    print(len(D), "boxes", flush=True)
    net = net_().to("cuda"); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-4); t0 = time.time(); step = 0; h = CHIP // 2
    while (done := (time.time() - t0) / (minutes * 60)) < 1:
        for g in opt.param_groups:
            g["lr"] = 1e-3 * min(1, done / 0.05) * 0.5 * (1 + np.cos(np.pi * done))
        X, Y, W = [], [], []
        for _ in range(16):
            k, x, seen, on = D[rng.integers(len(D))]
            r, c = on[rng.integers(len(on))] + rng.integers(-60, 61, 2)
            r, c = int(np.clip(r, h, k.shape[0] - h)), int(np.clip(c, h, k.shape[1] - h)); sl = (slice(r - h, r + h), slice(c - h, c + h))
            kk, xx, ss = k[sl], x[sl], seen[sl]
            t = rng.integers(4); kk, xx, ss = np.rot90(kk, t), np.rot90(xx, t), np.rot90(ss, t)
            if rng.random() < 0.5:
                kk, xx, ss = kk[:, ::-1], xx[:, ::-1], ss[:, ::-1]
            b, hid = cut(rng, kk.copy())
            X.append(stack(b, xx)); Y.append(ndimage.binary_dilation(kk, iterations=1)[None]); W.append((ss * (1 + 4 * ndimage.binary_dilation(hid, iterations=3)))[None])
        x = torch.from_numpy(np.stack(X)).to("cuda"); y = torch.from_numpy(np.stack(Y).astype(np.float32)).to("cuda"); w = torch.from_numpy(np.stack(W).astype(np.float32)).to("cuda")
        l = torch.nn.functional.binary_cross_entropy_with_logits(net(x), y, weight=w, pos_weight=torch.tensor(4.0).to("cuda"))
        opt.zero_grad(); l.backward(); opt.step(); step += 1
        if step % 500 == 0:
            print(step, round(float(l), 4), round((time.time() - t0) / 60, 1), flush=True); torch.save(net.state_dict(), f"{gd}/gap.pt")
    torch.save(net.state_dict(), f"{gd}/gap.pt"); print("trained", step, flush=True)


def prob(net, line, x):
    import torch
    n = line.shape[0]; P = np.zeros((n, n), np.float32); C = np.zeros((n, n), np.float32); t, s = 512, 384
    win = np.outer(*(2 * [np.minimum(np.arange(t) + 1, t - np.arange(t)).clip(max=64) / 64])).astype(np.float32)
    st = list(range(0, n - t, s)) + [n - t]
    with torch.inference_mode():
        for r in st:
            for c in st:
                b = torch.from_numpy(stack(line[r:r + t, c:c + t], x[r:r + t, c:c + t])[None]).to("cuda")
                P[r:r + t, c:c + t] += torch.sigmoid(net(b))[0, 0].cpu().numpy() * win; C[r:r + t, c:c + t] += win
    return P / np.maximum(C, 1e-6)


def repair(P, line, x, seen, tr, cut_at):
    """New line pieces: strong in the net, off the drawn lines, on the road side, touching a drawn line."""
    near = ndimage.binary_dilation(line, iterations=2)
    new = (P >= cut_at) & ~near & (x[..., 0] == 0) & ndimage.binary_dilation(seen, iterations=10)
    lab, n = ndimage.label(new, np.ones((3, 3)))
    if not n:
        return []
    touch = np.unique(lab[ndimage.binary_dilation(line, iterations=int(TOUCH / CELL) + 2) & new])
    keep = np.isin(lab, touch[touch > 0])
    return [l for l in kp.vectorise(keep, tr) if l.length >= MIN_NEW]


def f1(r):
    return 2 * r["found"] * r["precise"] / max(r["found"] + r["precise"], 1e-6)


def rate(D, R):
    ds, rs = ck.samples(D), ck.samples(R); dd, rd = ck.dist(ds, R), ck.dist(rs, D)
    return {"found": float((rd <= 1).mean()), "precise": float((dd <= 1).mean())}


def test(a):
    import torch
    import rasterio.features as rf
    from affine import Affine
    src, gd, ld, th = a
    net = net_(); net.load_state_dict(torch.load(f"{gd}/gap.pt", map_location="cpu")); net = net.to("cuda").eval()
    res = {}
    for nm, *_ in kl.VAL + kl.HOLD:
        if not os.path.exists(f"{gd}/{nm}.npz"):
            continue
        z = np.load(f"{gd}/{nm}.npz"); x, seen = z["x"], z["seen"]; m = json.load(open(f"{src}/{nm}_meta.json"))
        tr = Affine(CELL, 0, m["x0"], 0, -CELL, m["y0"] + m["w"]); clip = sbox(*m["box"]); n = x.shape[0]
        D, R = ck.lines(f"{ld}/{nm}_derived_{th}.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        line = rf.rasterize(((g, 1) for g in D), out_shape=(n, n), transform=tr, all_touched=True, dtype=np.uint8) > 0
        P = prob(net, line, x); res[nm] = {"role": "hold" if nm in dict(h[:2] for h in kl.HOLD) else "check", "base": rate(D, R)}
        for c in (0.3, 0.5, 0.7, 0.9):
            ls = repair(P, line, x, seen, tr, c); ins = [p for g in ls for q in [g.intersection(clip)] for p in getattr(q, "geoms", [q]) if p.geom_type == "LineString" and p.length > 0]
            res[nm][str(c)] = {**rate(D + ins, R), "added_km": round(sum(l.length for l in ins) / 1000, 2)}
            json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in ins]}, open(f"{gd}/{nm}_new_{c}.geojson", "w"))
        print(nm, {k: (round(v["found"], 3), round(v["precise"], 3), round(f1(v), 3), v.get("added_km")) for k, v in res[nm].items() if isinstance(v, dict)}, flush=True)
    by = {}
    for nm, r in res.items():
        by.setdefault(kl.SCEN[nm], []).append(nm)
    for c in ("base", "0.3", "0.5", "0.7", "0.9"):
        print(c, "scenario score", round(float(np.mean([np.mean([f1(res[n][c]) for n in v]) for v in by.values()])), 3), "check", round(float(np.mean([f1(r[c]) for r in res.values() if r["role"] == "check"])), 3), "held-out", round(float(np.mean([f1(r[c]) for r in res.values() if r["role"] == "hold"])), 3))
    json.dump(res, open(f"{gd}/test_{th}.json", "w"), indent=1)


if __name__ == "__main__":
    {"cache": cache, "train": train, "test": test}[sys.argv[1]](sys.argv[2:])
