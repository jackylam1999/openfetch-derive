#!/usr/bin/env python3
"""Kerb lines from the NSW 7 cm aerial photos (NSW Imagery, Spatial Services, CC BY 4.0) with a small U-Net trained on council kerbs.

Usage:
  python3 kerbphoto.py fetch NAME council x0 y0 out    (1 km box at E x0 N y0: photo at 0.1 m, council kerbs, cadastre lots)
  python3 kerbphoto.py train model.pt out NAME...      (train on the named boxes)
  python3 kerbphoto.py predict model.pt out NAME       (writes out/NAME_derived.geojson)
  python3 kerbphoto.py pilot                           (the whole pilot: fetch, train, predict and score the held-out boxes)

Everything is in GDA2020 MGA56 (EPSG:7856). The photos sit SHIFT m off the cadastre and council lines, so each photo is moved
by SHIFT before use. The model sees the photo (RGB) and the cadastre lot mask; label = within POS m of a council kerb, cells
POS..IGN m away are not scored, cells over 60 m from any council kerb are not scored (the council layer may be incomplete there).
Kerbs are never inside a lot: probabilities more than 0.5 m inside a lot are dropped. Lines are thinned at 0.2 m, joined, and
pieces under MIN_LEN m dropped. Scored with compare_kerbs.py (1 m tolerance).
"""
import sys, os, json, time, io, urllib.request, urllib.parse
import numpy as np
from scipy import ndimage

IMG = ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={},{},{},{}&bboxSR=7856"
       "&imageSR=7856&size=4000,4000&format=jpg&f=image")
COUNCILS = {
    "nb": ("https://maps.northernbeaches.nsw.gov.au/arcgis/rest/services/Assets/MapServer/12/query", (0.0, 0.0)),
    "parra": ("https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/2/query",
              (0.48, 1.42)),
}
LOTS = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query"
HDR = {"User-Agent": "Mozilla/5.0 openfetch-derive"}
CELL, MARGIN, SIZE = 0.1, 50, 1000
SHIFT = tuple(float(v) for v in os.environ.get("KERB_SHIFT", "0.5,0.6").split(","))  # (east, north) m to move the photo
POS, IGN, NEAR, MIN_LEN, THRESH = 0.3, 0.6, 60.0, 4.0, float(os.environ.get("KERB_THRESH", "0.5"))
CHIP, BATCH = 192, 12
STEPS = int(os.environ.get("KERB_STEPS", "3500"))
TRAIN = [("pw1", "nb", 342000, 6268000), ("pw2", "nb", 341000, 6269000), ("pw3", "nb", 343000, 6276000),
         ("pw4", "nb", 344000, 6277000)]
HOLD = [("monavale", "nb", 342000, 6272000), ("newport", "nb", 343000, 6274000), ("parramatta", "parra", 315000, 6256000)]


def get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=120).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def query(url, box, sr=7856, fields="OBJECTID"):
    feats, off = [], 0
    while True:
        q = {"geometry": ",".join(map(str, box)), "geometryType": "esriGeometryEnvelope", "inSR": sr, "outSR": sr,
             "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "true", "f": "geojson",
             "resultOffset": off, "resultRecordCount": 1000, "orderByFields": "OBJECTID"}
        d = json.loads(get(url + "?" + urllib.parse.urlencode(q)))
        got = [f for f in d.get("features", []) if f.get("geometry")]
        feats += got; off += len(d.get("features", []))
        if len(d.get("features", [])) < 1000 and not d.get("exceededTransferLimit"):
            return feats


def fetch(name, council, x0, y0, out):
    from PIL import Image
    from shapely.geometry import shape, mapping
    from shapely.affinity import translate
    os.makedirs(out, exist_ok=True)
    X0, Y0, W = x0 - MARGIN, y0 - MARGIN, SIZE + 2 * MARGIN
    n = int(round(W / CELL)); rgb = np.zeros((n, n, 3), np.uint8)
    for tx in range(0, W, 400):
        for ty in range(0, W, 400):
            b = get(IMG.format(X0 + tx, Y0 + ty, X0 + tx + 400, Y0 + ty + 400))
            if b[:2] != b"\xff\xd8":
                print(f"{name}: no photo at {X0 + tx},{Y0 + ty}", file=sys.stderr); continue
            a = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))
            r0 = n - (ty + 400) * 10; c0 = tx * 10
            rr, cc = slice(max(r0, 0), min(r0 + 4000, n)), slice(c0, min(c0 + 4000, n))
            rgb[rr, cc] = a[rr.start - r0:rr.stop - r0, :cc.stop - c0]
    rgb = ndimage.shift(rgb, (-SHIFT[1] / CELL, SHIFT[0] / CELL, 0), order=1, mode="nearest")
    np.save(f"{out}/{name}_rgb.npy", rgb)
    url, (dx, dy) = COUNCILS[council]
    pad = 3
    kerbs = []
    for f in query(url, (X0 - dx - pad, Y0 - dy - pad, X0 + W - dx + pad, Y0 + W - dy + pad)):
        kerbs.append({"type": "Feature", "geometry": mapping(translate(shape(f["geometry"]), dx, dy)), "properties": {}})
    lots = query(LOTS, (X0, Y0, X0 + W, Y0 + W), fields="lotidstring")
    json.dump({"type": "FeatureCollection", "features": kerbs}, open(f"{out}/{name}_kerbs.geojson", "w"))
    json.dump({"type": "FeatureCollection", "features": lots}, open(f"{out}/{name}_lots.geojson", "w"))
    json.dump({"x0": X0, "y0": Y0, "w": W, "box": [x0, y0, x0 + SIZE, y0 + SIZE]}, open(f"{out}/{name}_meta.json", "w"))
    print(f"{name}: photo {n}x{n}, {len(kerbs)} council kerbs, {len(lots)} lots", file=sys.stderr)


def rasters(out, name):
    import rasterio.features as rf
    from affine import Affine
    from shapely.geometry import shape
    m = json.load(open(f"{out}/{name}_meta.json")); n = int(round(m["w"] / CELL))
    tr = Affine(CELL, 0, m["x0"], 0, -CELL, m["y0"] + m["w"])
    rgb = np.load(f"{out}/{name}_rgb.npy", mmap_mode="r")
    burn = lambda p, lines: (rf.rasterize(((shape(f["geometry"]), 1) for f in json.load(open(p))["features"]), out_shape=(n, n),
                                          transform=tr, all_touched=lines, dtype=np.uint8) if json.load(open(p))["features"]
                             else np.zeros((n, n), np.uint8))
    lot = burn(f"{out}/{name}_lots.geojson", False)
    return m, tr, rgb, lot, (lambda: burn(f"{out}/{name}_kerbs.geojson", True))


def unet():
    import torch.nn as nn, torch

    def blk(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class U(nn.Module):
        def __init__(s, c=(16, 32, 64, 128)):
            super().__init__()
            s.d = nn.ModuleList([blk(4, c[0])] + [blk(c[i], c[i + 1]) for i in range(3)])
            s.u = nn.ModuleList([nn.ConvTranspose2d(c[i + 1], c[i], 2, 2) for i in range(3)])
            s.b = nn.ModuleList([blk(2 * c[i], c[i]) for i in range(3)])
            s.o = nn.Conv2d(c[0], 1, 1)

        def forward(s, x):
            k = []
            for i, d in enumerate(s.d):
                x = d(x if i == 0 else nn.functional.max_pool2d(x, 2)); k.append(x)
            for i in (2, 1, 0):
                x = s.b[i](torch.cat([s.u[i](x), k[i]], 1))
            return s.o(x)
    return U()


def stack(rgb, lot):
    x = np.concatenate([rgb.astype(np.float32) / 255 - 0.45, lot[..., None].astype(np.float32) - 0.5], -1)
    return np.ascontiguousarray(x.transpose(2, 0, 1))


def train(a):
    import torch
    torch.set_num_threads(os.cpu_count())
    path, out, names = a[0], a[1], a[2:]
    rng = np.random.default_rng(1); data = []
    for nm in names:
        m, tr, rgb, lot, kb = rasters(out, nm)
        dk = ndimage.distance_transform_edt(~kb().astype(bool)).astype(np.float32) * CELL
        y = (dk <= POS).astype(np.uint8)
        w = ((dk <= POS) | (dk > IGN)) & (dk <= NEAR)
        dl = ndimage.distance_transform_edt(lot == 0) * CELL
        road = (lot == 0) & (dl <= 20)
        pos_c = np.argwhere(y[::8, ::8] > 0) * 8; road_c = np.argwhere(road[::8, ::8] & (dk[::8, ::8] <= NEAR)) * 8
        data.append((np.asarray(rgb), lot, y, w, pos_c, road_c))
        print(f"{nm}: {len(pos_c)} kerb, {len(road_c)} street chip centres", file=sys.stderr)
    net = unet(); opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, total_steps=STEPS)
    h = CHIP // 2; t0 = time.time()
    for step in range(STEPS):
        xs, ys, ws = [], [], []
        for _ in range(BATCH):
            rgb, lot, y, w, pc, rc = data[rng.integers(len(data))]
            cs = pc if rng.random() < 0.6 else rc
            r, c = cs[rng.integers(len(cs))] + rng.integers(-40, 41, 2)
            r, c = int(np.clip(r, h, y.shape[0] - h)), int(np.clip(c, h, y.shape[1] - h))
            sl = (slice(r - h, r + h), slice(c - h, c + h))
            img = rgb[sl].astype(np.float32) * rng.uniform(0.8, 1.2) + rng.uniform(-20, 20)
            x = stack(np.clip(img, 0, 255), lot[sl]); yy, ww = y[sl][None].astype(np.float32), w[sl][None].astype(np.float32)
            k = int(rng.integers(4)); fl = rng.random() < 0.5
            x, yy, ww = (np.rot90(v, k, (1, 2)) for v in (x, yy, ww))
            if fl:
                x, yy, ww = (v[:, :, ::-1] for v in (x, yy, ww))
            xs.append(x.copy()); ys.append(yy.copy()); ws.append(ww.copy())
        X, Y, Wt = (torch.from_numpy(np.stack(v)) for v in (xs, ys, ws))
        lo = net(X)
        bce = torch.nn.functional.binary_cross_entropy_with_logits(lo, Y, weight=Wt * (1 + 4 * Y), reduction="sum") / Wt.sum()
        p = torch.sigmoid(lo) * Wt
        dice = 1 - (2 * (p * Y).sum() + 1) / (p.sum() + (Y * Wt).sum() + 1)
        loss = bce + dice
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if step % 200 == 0 or step == STEPS - 1:
            print(f"step {step} loss {loss.item():.3f} ({time.time() - t0:.0f} s)", file=sys.stderr, flush=True)
    torch.save(net.state_dict(), path)


def prob(net, rgb, lot):
    import torch
    n = rgb.shape[0]; P = np.zeros((n, n), np.float32); C = np.zeros((n, n), np.float32)
    t, s = 512, 448
    win = np.outer(*(2 * [np.minimum(np.arange(t) + 1, t - np.arange(t)).clip(max=32) / 32])).astype(np.float32)
    starts = list(range(0, n - t, s)) + [n - t]
    with torch.no_grad():
        for r in starts:
            for c in starts:
                if lot[r:r + t, c:c + t].all():
                    continue
                x = torch.from_numpy(stack(np.asarray(rgb[r:r + t, c:c + t]), lot[r:r + t, c:c + t])[None])
                P[r:r + t, c:c + t] += torch.sigmoid(net(x))[0, 0].numpy() * win; C[r:r + t, c:c + t] += win
    return P / np.maximum(C, 1e-6)


def vectorise(mask, tr):
    from skimage.morphology import skeletonize, remove_small_objects
    from shapely.geometry import LineString
    from shapely.ops import linemerge
    sk = skeletonize(remove_small_objects(mask, 20))
    ys, xs = np.nonzero(sk)
    idx = -np.ones(sk.shape, np.int64); idx[ys, xs] = np.arange(len(ys))
    segs = []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ok = (ys + dy < sk.shape[0]) & (xs + dx >= 0) & (xs + dx < sk.shape[1])
        j = np.where(ok, idx[np.clip(ys + dy, 0, sk.shape[0] - 1), np.clip(xs + dx, 0, sk.shape[1] - 1)], -1)
        for a, b in zip(np.flatnonzero(j >= 0), j[j >= 0]):
            segs.append(LineString([tr * (xs[a] + 0.5, ys[a] + 0.5), tr * (xs[b] + 0.5, ys[b] + 0.5)]))
    if not segs:
        return []
    m = linemerge(segs)
    return [l.simplify(0.15) for l in getattr(m, "geoms", [m]) if l.length >= MIN_LEN]


def predict(a):
    import torch
    from shapely.geometry import mapping
    torch.set_num_threads(os.cpu_count())
    net = unet(); net.load_state_dict(torch.load(a[0])); net.eval()
    out, nm = a[1], a[2]
    m, tr, rgb, lot, _ = rasters(out, nm)
    P = prob(net, rgb, lot)
    deep = ndimage.distance_transform_edt(lot > 0) * CELL > 0.5
    P[deep] = 0
    np.save(f"{out}/{nm}_prob.npy", (P * 255).astype(np.uint8))
    vec(out, nm, P, tr, THRESH)


def vec(out, nm, P, tr, th):
    from shapely.geometry import mapping
    from affine import Affine
    P2 = P.reshape(P.shape[0] // 2, 2, P.shape[1] // 2, 2).max((1, 3))
    ls = vectorise(P2 >= th, tr * Affine.scale(2))
    feats = [{"type": "Feature", "geometry": mapping(l), "properties": {"length": round(l.length, 1)}} for l in ls]
    json.dump({"type": "FeatureCollection", "features": feats}, open(f"{out}/{nm}_derived.geojson", "w"))


def score(out, nm, th):
    import subprocess
    b = json.load(open(f"{out}/{nm}_meta.json"))["box"]
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, f"{here}/compare_kerbs.py", f"{out}/{nm}_derived.geojson", f"{out}/{nm}_kerbs.geojson",
                        *map(str, b), "--png", f"{out}/{nm}_{th}.png"], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def pilot(a):
    out = a[0] if a else "kp"
    for nm, co, x, y in TRAIN + HOLD:
        if not os.path.exists(f"{out}/{nm}_meta.json"):
            fetch(nm, co, x, y, out)
    if not os.path.exists(f"{out}/model.pt"):
        train([f"{out}/model.pt", out] + [t[0] for t in TRAIN])
    res = {}
    for nm, *_ in HOLD:
        predict([f"{out}/model.pt", out, nm])
        m, tr, rgb, lot, _ = rasters(out, nm)
        P = np.load(f"{out}/{nm}_prob.npy").astype(np.float32) / 255
        for th in (0.3, 0.4, 0.5, 0.6):
            vec(out, nm, P, tr, th); res[f"{nm}@{th}"] = score(out, nm, th)
            os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
        print(nm, json.dumps({k: v for k, v in res.items() if k.startswith(nm)}), file=sys.stderr, flush=True)
    json.dump(res, open(f"{out}/scores.json", "w"), indent=1)
    print("SCORES", json.dumps(res))


if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    if c == "fetch":
        fetch(a[0], a[1], int(a[2]), int(a[3]), a[4])
    else:
        {"train": train, "predict": predict, "pilot": pilot}[c](a)
