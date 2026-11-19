import glob, time, os, sys, numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from scipy import ndimage
SRC = glob.glob("/kaggle/input/**/train_*.npz", recursive=True); print(len(SRC), SRC[:3], flush=True)
dev = "cuda" if torch.cuda.is_available() else "cpu"; print(dev, flush=True)
HOLD = ("carlton", "northmelb"); MIN = 100
def blk(a, b): return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))
class UNet(nn.Module):
    def __init__(s, arch="resnet34"):
        super().__init__(); import torchvision
        r = getattr(torchvision.models, arch)(weights="IMAGENET1K_V1")
        s.l0 = nn.Sequential(r.conv1, r.bn1, r.relu); s.l1 = nn.Sequential(r.maxpool, r.layer1); s.l2, s.l3, s.l4 = r.layer2, r.layer3, r.layer4
        s.d4 = blk(512 + 256, 256); s.d3 = blk(256 + 128, 128); s.d2 = blk(128 + 64, 64); s.d1 = blk(64 + 64, 48); s.d0 = blk(48 + 3, 32); s.o = nn.Conv2d(32, 1, 1)
    def forward(s, x):
        def up(a, b): return torch.cat([F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False), b], 1)
        e0 = s.l0(x); e1 = s.l1(e0); e2 = s.l2(e1); e3 = s.l3(e2); e4 = s.l4(e3)
        d = s.d4(up(e4, e3)); d = s.d3(up(d, e2)); d = s.d2(up(d, e1)); d = s.d1(up(d, e0)); d = s.d0(up(d, x)); return s.o(d)
MEAN = torch.tensor([0.485, 0.456, 0.406], device=dev)[None, :, None, None]; STD = torch.tensor([0.229, 0.224, 0.225], device=dev)[None, :, None, None]
TR, VA = [], []
for f in sorted(SRC):
    z = np.load(f); name = os.path.basename(f)[6:-4]
    road = z["road"]; edge = (ndimage.distance_transform_edt(road) <= 6) & (ndimage.distance_transform_edt(1 - road) <= 6)   # within 1.5 m of a kerb
    item = (z["img"], road, z["valid"], edge.astype(np.uint8), name)
    (VA if name in HOLD else TR).append(item); print(name, flush=True)
rng = np.random.default_rng(0); P = 256
def batch(D, n):
    X, Y, W = [], [], []
    while len(X) < n:
        img, road, val, edge, _ = D[rng.integers(len(D))]; H, Wd = road.shape; r, c = rng.integers(0, H - P), rng.integers(0, Wd - P)
        v = val[r:r + P, c:c + P]
        if v.mean() < 0.5: continue
        a, y, e = img[r:r + P, c:c + P], road[r:r + P, c:c + P], edge[r:r + P, c:c + P]
        k = rng.integers(4); a, y, v, e = (np.rot90(t, k) for t in (a, y, v, e))
        if rng.random() < .5: a, y, v, e = a[:, ::-1], y[:, ::-1], v[:, ::-1], e[:, ::-1]
        X.append(np.ascontiguousarray(a)); Y.append(np.ascontiguousarray(y)); W.append(np.ascontiguousarray(v * (1 + 4 * e)))
    x = torch.from_numpy(np.stack(X)).to(dev).permute(0, 3, 1, 2).float() / 255
    x = x * torch.empty(n, 1, 1, 1, device=dev).uniform_(.85, 1.15) + torch.empty(n, 1, 1, 1, device=dev).uniform_(-.05, .05)
    return (x - MEAN) / STD, torch.from_numpy(np.stack(Y)).to(dev)[:, None].float(), torch.from_numpy(np.stack(W)).to(dev)[:, None].float()
def val(m):
    m.eval(); I = U = 0
    with torch.no_grad():
        for img, road, v, e, _ in VA:
            for r in range(0, 4800 - 512, 640):
                for c in range(0, 4800 - 512, 640):
                    x = (torch.from_numpy(img[r:r + 512, c:c + 512].copy()).to(dev).permute(2, 0, 1)[None].float() / 255 - MEAN) / STD
                    p = (torch.sigmoid(m(x))[0, 0] > .5).cpu().numpy(); y = road[r:r + 512, c:c + 512] > 0; vv = (v[r:r + 512, c:c + 512] > 0) & (e[r:r + 512, c:c + 512] > 0)
                    I += (p & y & vv).sum(); U += ((p | y) & vv).sum()
    m.train(); return I / max(U, 1)
m = UNet().to(dev); opt = torch.optim.AdamW(m.parameters(), 3e-4, weight_decay=1e-4)
total = None; t0 = time.time(); it = 0; best = 0; L = []
sched_T = MIN * 60
while time.time() - t0 < sched_T:
    frac = (time.time() - t0) / sched_T
    for g in opt.param_groups: g["lr"] = 3e-4 * 0.5 * (1 + np.cos(np.pi * frac)) + 1e-6
    x, y, w = batch(TR, 24)
    lo = (F.binary_cross_entropy_with_logits(m(x), y, reduction="none") * w).sum() / w.sum()
    opt.zero_grad(); lo.backward(); opt.step(); L.append(lo.item()); it += 1
    if it % 500 == 0:
        iou = val(m); print(it, round(time.time() - t0), round(float(np.mean(L[-500:])), 4), "edge-band IoU", round(float(iou), 4), flush=True)
        if iou > best: best = iou; torch.save(m.state_dict(), "/kaggle/working/unet.pt")
print("done", it, best)
