#!/usr/bin/env python3
"""Kerb photo model that builds on itself round after round (replaces the settings search in kerbtune.py).

GPU (Kaggle, kerb-learn/kaggle/): runs on CUDA when there is one; KERB_STEPS_PER_MIN fixes the training length in steps (minutes x
rate, 21 = a 4-core CPU runner) so GPU rounds compare with CPU ones.

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
import kerbvic

_trace = kp.vectorise
kp.vectorise = lambda mask, tr: [l for l in kerbtidy.tidy(_trace(mask, tr)) if l.length >= kp.MIN_LEN]

kp.COUNCILS.update({
    "cb": ("https://services2.arcgis.com/Ax17MufLaTdpFneh/arcgis/rest/services/Kerb_Condition_1_5/FeatureServer/0/query",
           (0.0, 0.0), "FID"),
    "wo": ("https://maps.woollahra.nsw.gov.au/server/rest/services/basemap/basemap_eng_assets/MapServer/43/query", (0.0, 0.0),
           "OBJECTID"),
})
BOXES = json.load(open(os.environ.get("KERB_BOXES") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                     "../../../kerb-learn/boxes.json")))
ROLE = lambda r: [(b["name"], b["council"], b["x"], b["y"]) for b in BOXES["boxes"] if b["role"] == r]
TRAIN, VAL, HOLD = ROLE("train"), ROLE("check"), ROLE("hold")
SCEN = {b["name"]: b["scenario"] for b in BOXES["boxes"]}
CO = {b["name"]: b["council"] for b in BOXES["boxes"]}
SIX = "https://portal.spatial.nsw.gov.au/server/rest/services/"
LGA = SIX + "NSW_Administrative_Boundaries_Theme_multiCRS/FeatureServer/8/query"
CONTEXT = {"roads": SIX + "NSW_Transport_Theme_multiCRS/FeatureServer/5/query", "water": SIX + "NSW_Water_Theme_multiCRS/FeatureServer/6/query"}
TYPES = ("under trees", "in shadow", "cars or clutter", "faint kerb", "clear kerb")
CFG = {"encoder": "resnet34", "minutes": 150, "chip": 192, "batch": 12, "lr": 1e-3, "pw": 4.0, "skel": 0.0, "mine": 0.0,
       "focus": "", "seed": 0, "tta": 0, "jitter": 0, **json.loads(os.environ.get("KERB_CFG") or "{}")}
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


WEAK = 1.05


def unweak(out, nm):
    """Undo an align() shift the photo barely supports (edge gain under WEAK): in the Melbourne CBD tall buildings pulled the lines
    1.9 m for a 2% gain (30 Oct 2026). The council's own position is kept instead. Runs once per box (marks the align file)."""
    from shapely.geometry import shape, mapping
    from shapely.affinity import translate
    p = f"{out}/{nm}_align.json"; a = json.load(open(p))
    if a["edge_gain"] >= WEAK or a.get("undone") or not (a["dx"] or a["dy"]):
        return
    fs = json.load(open(f"{out}/{nm}_kerbs.geojson"))["features"]
    for f in fs:
        f["geometry"] = mapping(translate(shape(f["geometry"]), -a["dx"], -a["dy"]))
    json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{nm}_kerbs.geojson", "w"))
    a["undone"] = True; json.dump(a, open(p, "w"))


def data(a):
    """Fetch what is missing: photo, council kerbs moved onto the photo edge (align), lots, the council's area, roads, water.
    The photos are kept as JPEG (about 1/15 of the raw size) so the shared cache stays small: each job unpacks them once
    (GitHub refused the 4.9 GB raw cache after ~20 downloads, 30 Oct 2026)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    out = a[0]

    def one(box):
        nm, co, x, y = box
        jpg, raw = f"{out}/{nm}_rgb.jpg", f"{out}/{nm}_rgb.npy"
        if not os.path.exists(raw) and os.path.exists(jpg):
            np.save(raw, np.asarray(Image.open(jpg).convert("RGB")))
        if not os.path.exists(f"{out}/{nm}_meta.json"):
            (kerbvic.fetch if co in kerbvic.LGA_NAME else kp.fetch)(nm, co, x, y, out)
        if not os.path.exists(jpg):
            Image.fromarray(np.load(raw)).save(jpg, quality=95)
        if not os.path.exists(f"{out}/{nm}_align.json"):
            align(out, nm)
        unweak(out, nm)
        if not os.path.exists(f"{out}/{nm}_lga.geojson"):
            m = json.load(open(f"{out}/{nm}_meta.json")); b = (m["x0"], m["y0"], m["x0"] + m["w"], m["y0"] + m["w"])
            fs = [f for f in kp.query(LGA, b, fields="OBJECTID,lganame") if f["properties"]["lganame"] == BOXES["lga"][co]]
            json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{nm}_lga.geojson", "w"))
        rp = f"{out}/{nm}_roads.geojson"
        if co not in kerbvic.LGA_NAME and not os.path.exists(f"{out}/{nm}_water.geojson") or "functionhierarchy" not in open(rp).read(4000):
            m = json.load(open(f"{out}/{nm}_meta.json")); b = (m["x0"], m["y0"], m["x0"] + m["w"], m["y0"] + m["w"])
            for k, url in CONTEXT.items():
                fs = kp.query(url, b, fields="OBJECTID,functionhierarchy" if k == "roads" else "OBJECTID")
                json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{nm}_{k}.geojson", "w"))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        only = os.environ.get("KERB_COUNCILS")  # e.g. "com" or "villawood": fetch only these councils' or boxes' data
        list(ex.map(one, [t for t in TRAIN + VAL + HOLD if not only or {t[0], t[1]} & set(only.split(","))]))


def lot_side(lots, l):
    """+1 if the lots are on the left of line l, -1 if on the right (vote over points every 2 m, 1.5 m out)."""
    from shapely.geometry import Point
    v = 0
    for t in np.arange(0.5, max(l.length - 0.5, 0.6), 2.0):
        a, b = l.interpolate(max(t - 0.5, 0)), l.interpolate(min(t + 0.5, l.length))
        dx, dy = b.x - a.x, b.y - a.y; k = np.hypot(dx, dy)
        if not k:
            continue
        p = l.interpolate(t); L, R = Point(p.x - dy / k * 1.5, p.y + dx / k * 1.5), Point(p.x + dy / k * 1.5, p.y - dx / k * 1.5)
        v += len(lots.query(L, predicate="intersects")) > 0
        v -= len(lots.query(R, predicate="intersects")) > 0
    return 1 if v >= 0 else -1


def reference(out, nm):
    """The kerb line the model learns and is scored against is the kerb face (kerbs-method.md R4): each council's lines are moved
    toward the lots by that council's measured gutter offset (BOXES["gutter"], metres). The fetched lines stay in _kerbs0."""
    from shapely.geometry import shape, mapping
    from shapely.strtree import STRtree
    k0, k = f"{out}/{nm}_kerbs0.geojson", f"{out}/{nm}_kerbs.geojson"
    if not os.path.exists(k0):
        os.replace(k, k0)
    fc = json.load(open(k0)); d = BOXES["gutter"].get(CO[nm], 0)
    if d:
        lots = STRtree([shape(f["geometry"]) for f in json.load(open(f"{out}/{nm}_lots.geojson"))["features"]])
        for f in fc["features"]:
            g = shape(f["geometry"]); parts = [p.offset_curve(d * lot_side(lots, p)) for p in getattr(g, "geoms", [g])]
            f["geometry"] = mapping(parts[0] if len(parts) == 1 else type(g)(
                [q for p in parts for q in getattr(p, "geoms", [p]) if not q.is_empty]))
    json.dump(fc, open(k, "w"))


def inside(out, nm, n, tr):
    """True inside the box's council (the official LGA area): outside it nothing is trained, drawn or scored."""
    import rasterio.features as rf
    from shapely.geometry import shape
    fs = [shape(f["geometry"]) for f in json.load(open(f"{out}/{nm}_lga.geojson"))["features"]]
    if not fs:
        return np.ones((n, n), bool)
    return rf.rasterize(((g, 1) for g in fs), out_shape=(n, n), transform=tr, dtype=np.uint8).astype(bool)


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


def DEV():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def NIN():
    return 6 if CFG.get("context") else 4


def load(net, path):
    """Load saved weights; a model saved with fewer input layers gets the new ones at zero, so it starts out unchanged."""
    import torch
    sd, own = torch.load(path, map_location="cpu"), net.state_dict()
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
    ins = inside(out, nm, K.shape[0], tr); lab[~ins] = 0; road &= ins
    blank = np.asarray(rgb).max(-1) <= 3  # photo tiles the server refused: no labels where there is no picture
    lab[blank] = 0; road &= ~blank
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
    seed = CFG["seed"] or int(time.time()); rng = np.random.default_rng(seed); torch.manual_seed(seed); data = []
    for nm in names:
        m, tr, rgb, lot, lab, road = labels(out, nm)
        data.append((np.asarray(rgb), context(out, nm, lot), lab, pools(nm, lab, road, mine)))
        print(f"{nm}: " + ", ".join(f"{len(v)} {k}" for k, v in data[-1][-1].items()), file=sys.stderr)
    net = model(pretrained=init is None)
    if init:
        load(net, init)
    net = net.to(DEV())
    opt = torch.optim.AdamW(net.parameters(), CFG["lr"], weight_decay=1e-4)
    h = CFG["chip"] // 2; t0 = time.time(); step = 0; seen = {}
    rate = float(os.environ.get("KERB_STEPS_PER_MIN") or 0)
    while (done := step / (CFG["minutes"] * rate) if rate else (time.time() - t0) / (CFG["minutes"] * 60)) < 1:
        for g in opt.param_groups:
            g["lr"] = CFG["lr"] * min(1, done / 0.05) * 0.5 * (1 + np.cos(np.pi * done))
        xs, ys = [], []
        for _ in range(CFG["batch"]):
            (rgb, inp, lab, pl), kind = pick(rng, data)
            seen[kind] = seen.get(kind, 0) + 1
            cs = pl[kind] if len(pl.get(kind, ())) else pl["kerb"]
            z = rng.uniform(0.8, 1.25) if CFG["jitter"] else 1.0
            hz = int(round(h * z))
            r, c = cs[rng.integers(len(cs))] + rng.integers(-40, 41, 2)
            r, c = int(np.clip(r, hz, lab.shape[0] - hz)), int(np.clip(c, hz, lab.shape[1] - hz))
            sl = (slice(r - hz, r + hz), slice(c - hz, c + hz))
            lo, hi, off = (0.65, 1.35, 40) if CFG["jitter"] else (0.75, 1.25, 25)
            img = rgb[sl].astype(np.float32) * rng.uniform(lo, hi, 3) + rng.uniform(-off, off)
            ip, lb = inp[sl], lab[sl]
            if hz != h:
                f = h / hz
                img = ndimage.zoom(img, (f, f, 1), order=1)[:2 * h, :2 * h]
                ip, lb = ndimage.zoom(ip, (f, f, 1), order=0)[:2 * h, :2 * h], ndimage.zoom(lb, f, order=0)[:2 * h, :2 * h]
            x, y = stack(np.clip(img, 0, 255), ip), lb[None]
            k = int(rng.integers(4))
            x, y = np.rot90(x, k, (1, 2)), np.rot90(y, k, (1, 2))
            if rng.random() < 0.5:
                x, y = x[:, :, ::-1], y[:, :, ::-1]
            xs.append(x.copy()); ys.append(y.copy())
        L = torch.from_numpy(np.stack(ys)).to(DEV())
        Y, W, S = ((L == 2) | (L == 3)).float(), (L > 0).float(), (L == 3).float()
        lo = net(torch.from_numpy(np.stack(xs)).to(DEV()))
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


def prob(net, rgb, inp, ins=None, tta=None):
    """Kerb probability per pixel. tta (default CFG["tta"]): average the model over flips and a half turn of each window."""
    import torch
    tta = CFG["tta"] if tta is None else tta
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
                x = torch.from_numpy(stack(np.asarray(rgb[r:r + t, c:c + t]), inp[r:r + t, c:c + t])[None]).to(DEV())
                p = torch.sigmoid(net(x))
                for d in ((2,), (3,), (2, 3)) if tta else ():
                    p += torch.sigmoid(net(x.flip(d))).flip(d)
                P[r:r + t, c:c + t] += p[0, 0].cpu().numpy() / (4 if tta else 1) * win; C[r:r + t, c:c + t] += win
    P /= np.maximum(C, 1e-6)
    P[ndimage.distance_transform_edt(lot > 0) * CELL > 0.5] = 0
    if inp.shape[-1] > 2:
        P[inp[..., 2] > 0] = 0
    if ins is not None:
        P[~ins] = 0
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


SCALES = ("main roads", "collector roads", "local streets", "lanes and access")


def scale(out, nm, on, tr):
    """Road type of the nearest official road centreline for each kerb point (NSW functionhierarchy: 1-3 main, 4-5 collector,
    6 local, 7 and up lanes, transitways and unnamed access)."""
    from scipy.spatial import cKDTree
    from shapely.geometry import shape
    P, C = [], []
    for f in json.load(open(f"{out}/{nm}_roads.geojson"))["features"]:
        h = (f.get("properties") or {}).get("functionhierarchy")
        if not f.get("geometry") or h is None:
            continue
        g = shape(f["geometry"]); k = 0 if h <= 3 else 1 if h <= 5 else 2 if h == 6 else 3
        for t in np.arange(0, g.length + 1, 2.0):
            p = g.interpolate(min(t, g.length)); P.append((p.x, p.y)); C.append(k)
    if not P:
        return np.full(len(on), -1)
    xy = np.column_stack([tr.c + (on[:, 1] + 0.5) * CELL, tr.f - (on[:, 0] + 0.5) * CELL])
    return np.asarray(C)[cKDTree(P).query(xy)[1]]


def analyse(out, nm, lab, rgb, tr, n, keep=False):
    """Found share per probable cause and road type, 250 m site tiles passing the bar, extra line length."""
    import rasterio.features as rf
    from shapely.geometry import shape
    fs = json.load(open(f"{out}/{nm}_derived.geojson"))["features"]
    D = rf.rasterize(((shape(f["geometry"]), 1) for f in fs), out_shape=(n, n), transform=tr, all_touched=True, dtype=np.uint8) \
        if fs else np.zeros((n, n), np.uint8)
    dD = ndimage.distance_transform_edt(D == 0).astype(np.float32) * CELL
    core = np.zeros((n, n), bool); mg = int(kp.MARGIN / CELL); core[mg:n - mg, mg:n - mg] = True
    on = np.argwhere((lab == 3) & core); on = on[::5]
    hit = dD[on[:, 0], on[:, 1]] <= TOL
    tiles, ok, q = 0, 0, int(250 / CELL)
    ti = ((on[:, 0] - mg) // q) * 4 + (on[:, 1] - mg) // q
    for i in range(16):
        k = ti == i
        if k.sum() * 5 * CELL < 50:
            continue
        tiles += 1; ok += hit[k].mean() >= 0.85 and float(np.median(dD[on[k][:, 0], on[k][:, 1]][hit[k]])) <= 0.3
    ty = causes(rgb, on)
    res = {"tiles": [int(ok), tiles], "types": {TYPES[i]: [int((ty == i).sum()), round(float(hit[ty == i].mean()), 3) if (ty == i).any() else None]
                     for i in range(len(TYPES))}}
    sc = scale(out, nm, on, tr)
    res["scales"] = {SCALES[i]: [int((sc == i).sum()), round(float(hit[sc == i].mean()), 3) if (sc == i).any() else None]
                     for i in range(len(SCALES))}
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


def evaluate(net, out, tta):
    """Score the check and held-out boxes at every threshold (the check boxes pick it). Per box: found / precise / offset, found
    by cause and road type, whole lines, 250 m site tiles. Scenario score = mean over scenarios of the mean box F1 (R5)."""
    sc, keep, boxes, by = {}, {}, {}, {}
    for nm, *_ in VAL + HOLD:
        m, tr, rgb, lot, lab, road = labels(out, nm)
        P = prob(net, rgb, context(out, nm, lot), inside(out, nm, lab.shape[0], tr), tta); keep[nm] = (tr, lab)
        for th in kp.THRESHS:
            kp.vec(out, nm, P, tr, th); sc.setdefault(th, {})[nm] = kp.score(out, nm, th)
            os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
    th = max(kp.THRESHS, key=lambda t: np.mean([f1(sc[t][v[0]]) for v in VAL]))
    for nm, *_ in VAL + HOLD:
        tr, lab = keep.pop(nm); rgb = np.load(f"{out}/{nm}_rgb.npy", mmap_mode="r")
        os.replace(f"{out}/{nm}_derived_{th}.geojson", f"{out}/{nm}_derived.geojson")
        an = analyse(out, nm, lab, rgb, tr, lab.shape[0])[0]
        os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
        boxes[nm] = {**sc[th][nm], **an, "whole_lines": whole(out, nm, th), "f1": round(f1(sc[th][nm]), 3), "scenario": SCEN[nm],
                     "role": "hold" if nm in dict(h[:2] for h in HOLD) else "check"}
        by.setdefault(SCEN[nm], []).append(boxes[nm]["f1"])
    t = [sum(b["tiles"][i] for b in boxes.values()) for i in (0, 1)]
    mean = lambda v: round(float(np.mean(v)), 3)
    return {"thresh": th, "val_f1": mean([boxes[v[0]]["f1"] for v in VAL]), "score": mean([boxes[v[0]]["f1"] for v in HOLD]),
            "mean_recall": mean([boxes[v[0]].get("recall", 0) for v in HOLD]),
            "scenario_score": mean([np.mean(v) for v in by.values()]), "scenarios": {k: mean(v) for k, v in by.items()},
            "worst_hold": min(boxes[v[0]]["f1"] for v in HOLD), "site_share": round(t[0] / max(t[1], 1), 3), "boxes": boxes}


def run(a):
    """One variant: fine-tune the given model for CFG minutes (0 = score it as it is), then score it. CFG["eval_tta"] also scores
    the same model with test-time flips switched the other way, so an inference-only change is judged on the same weights."""
    out, res_path = a[0], a[1]
    init = a[2] if len(a) > 2 and os.path.exists(a[2]) else None
    data([out])
    for nm, *_ in TRAIN + VAL + HOLD:
        reference(out, nm)
    t0 = time.time(); info = {"steps": 0}
    if CFG["minutes"]:
        info = train(f"{out}/model.pt", out, [t[0] for t in TRAIN], init, None)[0]
    else:
        import shutil
        shutil.copy(init, f"{out}/model.pt")
    net = model(False); load(net, f"{out}/model.pt"); net = net.to(DEV()).eval()
    ev = {"tta": evaluate(net, out, 1 - CFG["tta"])} if CFG.get("eval_tta") else {}
    res = {"cfg": CFG, "train": info, **evaluate(net, out, CFG["tta"]), "eval": ev, "minutes": round((time.time() - t0) / 60),
           "steps_per_min": float(os.environ.get("KERB_STEPS_PER_MIN") or 0), "device": DEV()}
    json.dump(res, open(res_path, "w"), indent=1)
    print("RESULT", json.dumps({k: res[k] for k in ("thresh", "val_f1", "score", "scenario_score", "site_share")}))


if __name__ == "__main__":
    {"data": data, "run": run}[sys.argv[1]](sys.argv[2:])
