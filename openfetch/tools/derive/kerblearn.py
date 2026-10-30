#!/usr/bin/env python3
"""Kerb photo model that builds on itself round after round (replaces the settings search in kerbtune.py).

Usage:
  python3 kerblearn.py data out                  (fetch every box, fit the offset of the new councils' kerbs to the photo)
  python3 kerblearn.py run out result.json [best.pt mine.npz]   (one round variant; settings in KERB_CFG)

What makes each round learn from the one before (research notes in docs/handoffs/kerbs-photo-model.md):
1 a U-Net on an ImageNet ResNet encoder instead of a small network trained from zero;
2 each round fine-tunes the best model so far (best.pt), never a fresh start;
3 the best model's mistakes on the training boxes (mine.npz: missed kerb and extra line points, each miss sorted into a probable
  cause) are fed back as extra training chips, most of them of the cause named in KERB_CFG["focus"] (hard-example mining);
4 an optional thin-line loss (skeleton recall, Kirchhoff et al. ECCV 2024) that rewards unbroken kerb lines;
5 training boxes in three councils (Northern Beaches, Canterbury-Bankstown, Woollahra), Parramatta never seen;
6 the threshold and the keep-or-drop decision use check boxes inside the training councils, so held-out boxes stay unseen.
The result says, per probable cause, how much council kerb the model found on the check and held-out boxes, plus the share of whole
kerb lines found, so the log can say what each round learnt.
"""
import sys, os, json, time
import numpy as np
from scipy import ndimage
import kerbphoto as kp
import kerbtidy

_trace = kp.vectorise
kp.vectorise = lambda mask, tr: [l for l in kerbtidy.tidy(_trace(mask, tr)) if l.length >= kp.MIN_LEN]

kp.COUNCILS.update({
    "cb": ("https://services2.arcgis.com/Ax17MufLaTdpFneh/arcgis/rest/services/Kerb_Condition_1_5/FeatureServer/0/query",
           (0.0, 0.0), "FID"),
    "wo": ("https://maps.woollahra.nsw.gov.au/server/rest/services/basemap/basemap_eng_assets/MapServer/43/query", (0.0, 0.0),
           "OBJECTID"),
})
TRAIN = kp.TRAIN + [("cb1", "cb", 318000, 6245000), ("cb2", "cb", 317000, 6246000), ("cb3", "cb", 326000, 6244000),
                    ("wo1", "wo", 338000, 6249000), ("wo2", "wo", 337000, 6250000)]
VAL = [("nbcheck", "nb", 342000, 6269000), ("cbcheck", "cb", 320000, 6246000), ("wocheck", "wo", 339000, 6250000)]
HOLD = kp.HOLD
FIT = {"cb", "wo"}
SIX = "https://portal.spatial.nsw.gov.au/server/rest/services/"
CONTEXT = {"roads": SIX + "NSW_Transport_Theme_multiCRS/FeatureServer/5/query", "water": SIX + "NSW_Water_Theme_multiCRS/FeatureServer/6/query"}
TYPES = ("under trees", "in shadow", "cars or clutter", "faint kerb", "clear kerb")
CFG = {"encoder": "resnet34", "minutes": 150, "chip": 192, "batch": 12, "lr": 1e-3, "pw": 4.0, "skel": 0.0, "mine": 0.0,
       "focus": "", **json.loads(os.environ.get("KERB_CFG") or "{}")}
kp.CFG.update(CFG)
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
CELL, NEAR, POS, IGN, TOL = kp.CELL, kp.NEAR, 0.3, 0.6, 1.0


def align(out, name):
    """Move a council's kerbs onto the photo: the shift (within 3 m) that puts the lines on the strongest photo edges."""
    from shapely.geometry import shape, mapping
    from shapely.affinity import translate
    m = json.load(open(f"{out}/{name}_meta.json")); n = int(round(m["w"] / CELL))
    g = np.asarray(np.load(f"{out}/{name}_rgb.npy", mmap_mode="r"), np.float32).mean(-1)
    g = ndimage.gaussian_filter(g, 1.5); G = np.hypot(ndimage.sobel(g, 0), ndimage.sobel(g, 1))
    fs = json.load(open(f"{out}/{name}_kerbs.geojson"))["features"]
    pts = []
    for f in fs:
        l = shape(f["geometry"])
        for p in getattr(l, "geoms", [l]):
            pts += [p.interpolate(t).coords[0] for t in np.arange(0.25, p.length, 1.0)]
    P = np.array(pts)
    P = P[(P[:, 0] > m["x0"] + 5) & (P[:, 0] < m["x0"] + m["w"] - 5) & (P[:, 1] > m["y0"] + 5) & (P[:, 1] < m["y0"] + m["w"] - 5)]
    best = (-1, 0, 0)
    for dx in np.arange(-3, 3.01, 0.1):
        for dy in np.arange(-3, 3.01, 0.1):
            c = (P[:, 0] + dx - m["x0"]) / CELL; r = n - (P[:, 1] + dy - m["y0"]) / CELL
            s = float(ndimage.map_coordinates(G, [r, c], order=1).mean())
            best = max(best, (s, round(dx, 1), round(dy, 1)))
    s0 = float(ndimage.map_coordinates(G, [n - (P[:, 1] - m["y0"]) / CELL, (P[:, 0] - m["x0"]) / CELL], order=1).mean())
    json.dump({"dx": best[1], "dy": best[2], "edge_gain": round(best[0] / max(s0, 1e-6), 3)}, open(f"{out}/{name}_align.json", "w"))
    print(f"{name}: kerbs moved {best[1]} E {best[2]} N (edge strength x{best[0] / max(s0, 1e-6):.2f})", file=sys.stderr)
    for f in fs:
        f["geometry"] = mapping(translate(shape(f["geometry"]), best[1], best[2]))
    json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{name}_kerbs.geojson", "w"))


def data(a):
    out = a[0]
    for nm, co, x, y in TRAIN + VAL + HOLD:
        if not os.path.exists(f"{out}/{nm}_meta.json"):
            kp.fetch(nm, co, x, y, out)
        if co in FIT and not os.path.exists(f"{out}/{nm}_align.json"):
            align(out, nm)
        if not os.path.exists(f"{out}/{nm}_water.geojson"):
            m = json.load(open(f"{out}/{nm}_meta.json")); b = (m["x0"], m["y0"], m["x0"] + m["w"], m["y0"] + m["w"])
            for k, url in CONTEXT.items():
                fs = kp.query(url, b)
                json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{nm}_{k}.geojson", "w"))


def context(out, nm, lot):
    """Model input besides the photo: the lot mask, and with CFG["context"] the distance to the official road centreline
    (0.1 m steps, up to 25 m) and the official water areas (NSW Transport and Water Themes, Spatial Services, CC BY 4.0)."""
    if not CFG.get("context"):
        return lot[..., None]
    import rasterio.features as rf
    from shapely.geometry import shape
    from affine import Affine
    m = json.load(open(f"{out}/{nm}_meta.json"))
    n = lot.shape[0]; tr = Affine(CELL, 0, m["x0"], 0, -CELL, m["y0"] + m["w"])
    def burn(k, lines):
        fs = [shape(f["geometry"]) for f in json.load(open(f"{out}/{nm}_{k}.geojson"))["features"] if f.get("geometry")]
        return rf.rasterize(((g, 1) for g in fs), out_shape=(n, n), transform=tr, all_touched=lines, dtype=np.uint8) if fs \
            else np.zeros((n, n), np.uint8)
    rd = np.minimum(ndimage.distance_transform_edt(burn("roads", True) == 0), 250).astype(np.uint8)
    return np.stack([lot, rd, burn("water", False)], -1)


def model(pretrained=True):
    import torch, torch.nn as nn, torchvision

    def blk(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class U(nn.Module):
        def __init__(s):
            super().__init__()
            e = getattr(torchvision.models, CFG["encoder"])(weights="IMAGENET1K_V1" if pretrained else None, progress=False)
            c1 = nn.Conv2d(NIN(), 64, 7, 2, 3, bias=False)
            with torch.no_grad():
                c1.weight.zero_(); c1.weight[:, :3] = e.conv1.weight
            s.stem = nn.Sequential(c1, e.bn1, e.relu)
            s.enc = nn.ModuleList([nn.Sequential(e.maxpool, e.layer1), e.layer2, e.layer3, e.layer4])
            ch = [64, 64, 128, 256, 512]
            s.full = blk(NIN(), 16)
            s.up = nn.ModuleList([blk(ch[4] + ch[3], 256), blk(256 + ch[2], 128), blk(128 + ch[1], 64), blk(64 + ch[0], 32),
                                  blk(32 + 16, 16)])
            s.out = nn.Conv2d(16, 1, 1)

        def forward(s, x):
            f = [s.full(x), s.stem(x)]
            for e in s.enc:
                f.append(e(f[-1]))
            y = f.pop()
            for u in s.up:
                k = f.pop()
                y = u(torch.cat([nn.functional.interpolate(y, size=k.shape[-2:], mode="bilinear", align_corners=False), k], 1))
            return s.out(y)
    return U()


def NIN():
    return 6 if CFG.get("context") else 4


def load(net, path):
    """Load saved weights; a model saved with fewer input layers gets the new ones at zero, so it starts out unchanged."""
    import torch
    sd, own = torch.load(path), net.state_dict()
    for k, v in sd.items():
        if v.dim() == 4 and own[k].shape[1] > v.shape[1]:
            w = torch.zeros_like(own[k]); w[:, :v.shape[1]] = v; sd[k] = w
    net.load_state_dict(sd)


def stack(rgb, inp):
    sc = np.array([1, 1 / 250, 1], np.float32)[:inp.shape[-1]]
    x = np.concatenate([(rgb.astype(np.float32) / 255 - MEAN) / STD, inp.astype(np.float32) * sc - 0.5], -1)
    return np.ascontiguousarray(x.transpose(2, 0, 1))


def labels(out, nm):
    """0 = not scored, 1 = not kerb but within 1 m, 4 = over 1 m from a kerb, 2 = within POS m of a council kerb, 3 = on the line."""
    m, tr, rgb, lot, kb = kp.rasters(out, nm)
    K = kb().astype(bool)
    dk = ndimage.distance_transform_edt(~K).astype(np.float32) * CELL
    lab = np.zeros(K.shape, np.uint8)
    lab[(dk > IGN) & (dk <= NEAR)] = 1; lab[(dk > TOL) & (dk <= NEAR)] = 4; lab[dk <= POS] = 2; lab[K] = 3
    road = (lot == 0) & (ndimage.distance_transform_edt(lot == 0) * CELL <= 20) & (dk <= NEAR)
    return m, tr, rgb, lot, lab, road


def pools(nm, lab, road, mine):
    p = {"kerb": np.argwhere((lab[::8, ::8] == 2) | (lab[::8, ::8] == 3)) * 8, "street": np.argwhere(road[::8, ::8]) * 8}
    if mine is not None and f"{nm}_miss" in mine:
        ms, fp = mine[f"{nm}_miss"], mine[f"{nm}_fp"]
        p["mistakes"] = np.concatenate([ms[:, :2], fp]) if len(fp) else ms[:, :2]
        p["focus"] = fp if CFG["focus"] == "extra lines" else (
            ms[ms[:, 2] == TYPES.index(CFG["focus"]), :2] if CFG["focus"] in TYPES else np.zeros((0, 2), int))
    return p


def pick(rng, data):
    u, mi = rng.random(), CFG["mine"]
    kind = ("focus" if rng.random() < 0.6 else "mistakes") if u < mi else ("kerb" if u < mi + (1 - mi) * 0.6 else "street")
    ok = [d for d in data if len(d[-1].get(kind, ()))]
    if not ok:
        kind, ok = "kerb", [d for d in data if len(d[-1]["kerb"])]
    return ok[rng.integers(len(ok))], kind


def train(path, out, names, init, mine):
    import torch
    torch.set_num_threads(os.cpu_count())
    rng = np.random.default_rng(int(time.time())); data = []
    for nm in names:
        m, tr, rgb, lot, lab, road = labels(out, nm)
        data.append((np.asarray(rgb), context(out, nm, lot), lab, pools(nm, lab, road, mine)))
        print(f"{nm}: " + ", ".join(f"{len(v)} {k}" for k, v in data[-1][-1].items()), file=sys.stderr)
    net = model(pretrained=init is None)
    if init:
        load(net, init)
    opt = torch.optim.AdamW(net.parameters(), CFG["lr"], weight_decay=1e-4)
    h = CFG["chip"] // 2; t0 = time.time(); step = 0; seen = {}
    while (done := (time.time() - t0) / (CFG["minutes"] * 60)) < 1:
        for g in opt.param_groups:
            g["lr"] = CFG["lr"] * min(1, done / 0.05) * 0.5 * (1 + np.cos(np.pi * done))
        xs, ys = [], []
        for _ in range(CFG["batch"]):
            (rgb, inp, lab, pl), kind = pick(rng, data)
            seen[kind] = seen.get(kind, 0) + 1
            cs = pl[kind] if len(pl.get(kind, ())) else pl["kerb"]
            r, c = cs[rng.integers(len(cs))] + rng.integers(-40, 41, 2)
            r, c = int(np.clip(r, h, lab.shape[0] - h)), int(np.clip(c, h, lab.shape[1] - h))
            sl = (slice(r - h, r + h), slice(c - h, c + h))
            img = rgb[sl].astype(np.float32) * rng.uniform(0.75, 1.25, 3) + rng.uniform(-25, 25)
            x, y = stack(np.clip(img, 0, 255), inp[sl]), lab[sl][None]
            k = int(rng.integers(4))
            x, y = np.rot90(x, k, (1, 2)), np.rot90(y, k, (1, 2))
            if rng.random() < 0.5:
                x, y = x[:, :, ::-1], y[:, :, ::-1]
            xs.append(x.copy()); ys.append(y.copy())
        L = torch.from_numpy(np.stack(ys))
        Y, W, S = ((L == 2) | (L == 3)).float(), (L > 0).float(), (L == 3).float()
        lo = net(torch.from_numpy(np.stack(xs)))
        bce = torch.nn.functional.binary_cross_entropy_with_logits(lo, Y, weight=W * (1 + CFG["pw"] * Y), reduction="sum") / W.sum()
        p = torch.sigmoid(lo) * W
        loss = bce + 1 - (2 * (p * Y).sum() + 1) / (p.sum() + (Y * W).sum() + 1)
        if CFG["skel"]:
            loss = loss + CFG["skel"] * (1 - ((p * S).sum() + 1) / (S.sum() + 1))
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 100 == 0:
            print(f"step {step} loss {loss.item():.3f} ({time.time() - t0:.0f} s)", file=sys.stderr, flush=True)
        step += 1
    torch.save(net.state_dict(), path)
    return {"steps": step, "chips": seen}, {nm: d[:3] for nm, d in zip(names, data)}


def prob(net, rgb, inp):
    import torch
    lot = inp[..., 0]
    n = rgb.shape[0]; P = np.zeros((n, n), np.float32); C = np.zeros((n, n), np.float32)
    t, s = 512, 448
    win = np.outer(*(2 * [np.minimum(np.arange(t) + 1, t - np.arange(t)).clip(max=32) / 32])).astype(np.float32)
    starts = list(range(0, n - t, s)) + [n - t]
    with torch.inference_mode():
        for r in starts:
            for c in starts:
                if lot[r:r + t, c:c + t].all():
                    continue
                x = torch.from_numpy(stack(np.asarray(rgb[r:r + t, c:c + t]), inp[r:r + t, c:c + t])[None])
                P[r:r + t, c:c + t] += torch.sigmoid(net(x))[0, 0].numpy() * win; C[r:r + t, c:c + t] += win
    P /= np.maximum(C, 1e-6)
    P[ndimage.distance_transform_edt(lot > 0) * CELL > 0.5] = 0
    if inp.shape[-1] > 2:
        P[inp[..., 2] > 0] = 0
    return P


def causes(rgb, rc):
    """Probable cause per kerb point, from the photo around it: trees (green over most of 1 m), shadow (dark), cars or clutter
    (strong light-dark mix over 2 m), faint kerb (almost no contrast over 2 m), otherwise a clear kerb."""
    if not len(rc):
        return np.zeros(0, np.int32)
    o1, o2 = np.arange(-5, 6), np.arange(-10, 11, 2)
    def win(o):
        r = np.clip(rc[:, :1, None] + o[None, :, None], 0, rgb.shape[0] - 1)
        c = np.clip(rc[:, 1:, None] + o[None, None, :], 0, rgb.shape[1] - 1)
        return np.asarray(rgb[r, c], np.float32).reshape(len(rc), -1, 3)
    a, b = win(o1), win(o2)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    green = ((2 * G - R - B) / (R + G + B + 1) > 0.05).mean(1)
    lum, lum2 = a.mean(-1).mean(1), b.mean(-1)
    t = np.full(len(rc), 4, np.int32)
    t[lum2.std(1) < 12] = 3
    t[lum2.std(1) > 45] = 2
    t[lum < 60] = 1
    t[green > 0.7] = 0
    return t


def analyse(out, nm, lab, rgb, tr, n, keep=False):
    """Found share per probable cause, whole lines found, and (training boxes) the missed and extra points for the next round."""
    import rasterio.features as rf
    from shapely.geometry import shape
    fs = json.load(open(f"{out}/{nm}_derived.geojson"))["features"]
    D = rf.rasterize(((shape(f["geometry"]), 1) for f in fs), out_shape=(n, n), transform=tr, all_touched=True, dtype=np.uint8) \
        if fs else np.zeros((n, n), np.uint8)
    dD = ndimage.distance_transform_edt(D == 0).astype(np.float32) * CELL
    core = np.zeros((n, n), bool); mg = int(kp.MARGIN / CELL); core[mg:n - mg, mg:n - mg] = True
    on = np.argwhere((lab == 3) & core); on = on[::5]
    hit = dD[on[:, 0], on[:, 1]] <= TOL
    ty = causes(rgb, on)
    res = {"types": {TYPES[i]: [int((ty == i).sum()), round(float(hit[ty == i].mean()), 3) if (ty == i).any() else None]
                     for i in range(len(TYPES))}}
    fp = np.argwhere((D > 0) & core & (lab == 4))[::5]
    res["extra_m"] = round(len(fp) * 5 * CELL)
    if keep:
        return res, np.column_stack([on[~hit], ty[~hit]]).astype(np.int32), fp.astype(np.int32)
    return res, None, None


def whole(out, nm, th):
    """Share of council kerb lines (over 5 m inside the box) with at least 80% of their length found within 1 m."""
    from shapely.geometry import shape, box as sbox
    from shapely.strtree import STRtree
    b = sbox(*json.load(open(f"{out}/{nm}_meta.json"))["box"])
    D = [shape(f["geometry"]) for f in json.load(open(f"{out}/{nm}_derived_{th}.geojson"))["features"]]
    if not D:
        return 0.0
    tree, ok, tot = STRtree(D), 0, 0
    for f in json.load(open(f"{out}/{nm}_kerbs.geojson"))["features"]:
        g = shape(f["geometry"]).intersection(b)
        if g.length < 5:
            continue
        pts = [g.interpolate(t) for t in np.arange(0.25, g.length, 0.5)]
        near = [D[i].distance(p) <= TOL for p, i in zip(pts, tree.nearest(pts))]
        ok += np.mean(near) >= 0.8; tot += 1
    return round(ok / max(tot, 1), 3)


def f1(v):
    return 2 * v.get("recall", 0) * v.get("precision", 0) / max(v.get("recall", 0) + v.get("precision", 0), 1e-6)


def run(a):
    import torch
    out, res_path = a[0], a[1]
    init = a[2] if len(a) > 2 and os.path.exists(a[2]) else None
    mine = np.load(a[3]) if len(a) > 3 and os.path.exists(a[3]) else None
    data([out]); t0 = time.time()
    info, held = train(f"{out}/model.pt", out, [t[0] for t in TRAIN], init, mine)
    net = model(False); load(net, f"{out}/model.pt"); net.eval()
    sc, an, keep = {}, {}, {}
    for nm, *_ in VAL + HOLD:
        m, tr, rgb, lot, lab, road = labels(out, nm)
        P = prob(net, rgb, context(out, nm, lot)); keep[nm] = (tr, lab)
        for th in kp.THRESHS:
            kp.vec(out, nm, P, tr, th); sc.setdefault(th, {})[nm] = kp.score(out, nm, th)
            os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
    th = max(kp.THRESHS, key=lambda t: np.mean([f1(sc[t][v[0]]) for v in VAL]))
    for nm, *_ in VAL + HOLD:
        tr, lab = keep.pop(nm); rgb = np.load(f"{out}/{nm}_rgb.npy", mmap_mode="r")
        os.replace(f"{out}/{nm}_derived_{th}.geojson", f"{out}/{nm}_derived.geojson")
        an[nm] = analyse(out, nm, lab, rgb, tr, lab.shape[0])[0]
        os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
        an[nm]["whole_lines"] = whole(out, nm, th)
    mined = {}
    for nm, (rgb, inp, lab) in held.items():
        tr = kp.rasters(out, nm)[1]
        kp.vec(out, nm, prob(net, rgb, inp), tr, th)
        r, ms, fp = analyse(out, nm, lab, rgb, tr, lab.shape[0], keep=True)
        mined[f"{nm}_miss"], mined[f"{nm}_fp"] = ms, fp
    np.savez_compressed(f"{out}/mine.npz", **mined)
    miss = np.concatenate([v[:, 2] for k, v in mined.items() if k.endswith("_miss")])
    res = {"cfg": CFG, "thresh": th, "train": info, "minutes": round((time.time() - t0) / 60),
           "val_f1": round(float(np.mean([f1(sc[th][v[0]]) for v in VAL])), 3),
           "score": round(float(np.mean([f1(sc[th][v[0]]) for v in HOLD])), 3),
           "mean_recall": round(float(np.mean([sc[th][v[0]].get("recall", 0) for v in HOLD])), 3),
           "boxes": {v[0]: {**sc[th][v[0]], **an[v[0]]} for v in VAL + HOLD},
           "train_misses": {TYPES[i]: int((miss == i).sum()) for i in range(len(TYPES))},
           "train_extra_points": int(sum(len(v) for k, v in mined.items() if k.endswith("_fp"))), "all": sc}
    json.dump(res, open(res_path, "w"), indent=1)
    print("RESULT", json.dumps({k: res[k] for k in ("thresh", "val_f1", "score", "mean_recall", "train_misses")}))


if __name__ == "__main__":
    {"data": data, "run": run}[sys.argv[1]](sys.argv[2:])
