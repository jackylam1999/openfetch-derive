"""ftang.py base.pt train_dir out.pt minutes : CPU fine-tune of the aerial road U-Net on council crops, half centred on angle bays.
Weight = valid x (1 + 4 x kerb band 1.5 m) x (1 + 4 x angle-bay zone). BatchNorm frozen (small CPU batches). Never overwrites base.pt."""
import sys, os, glob, time, numpy as np, torch, torch.nn.functional as F
from scipy import ndimage
sys.path.insert(0, "/tmp/claude-0/w/derive/openfetch/tools/derive/kerbvic"); from unet import UNet, MEAN, STD
base, td, out, MIN = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
assert os.path.abspath(out) != os.path.abspath(base)
torch.set_num_threads(4); D = []
for f in sorted(glob.glob(f"{td}/train_*.npz")):
    z = np.load(f); road = z["road"]
    edge = (ndimage.distance_transform_edt(road) <= 6) & (ndimage.distance_transform_edt(1 - road) <= 6)
    D.append((z["img"], road, z["valid"], edge.astype(np.uint8), z["ang"], np.argwhere(z["ang"] > 0)))
rng = np.random.default_rng(0); P, B = 256, 8
def batch():
    X, Y, W = [], [], []
    while len(X) < B:
        img, road, val, edge, ang, aw = D[rng.integers(len(D))]; H, Wd = road.shape
        if len(X) % 2 == 0 and len(aw):
            r, c = aw[rng.integers(len(aw))]; r, c = int(np.clip(r - P // 2, 0, H - P)), int(np.clip(c - P // 2, 0, Wd - P))
        else:
            r, c = rng.integers(0, H - P), rng.integers(0, Wd - P)
        v = val[r:r + P, c:c + P]
        if v.mean() < .5: continue
        a, y, e, g = img[r:r + P, c:c + P], road[r:r + P, c:c + P], edge[r:r + P, c:c + P], ang[r:r + P, c:c + P]
        k = rng.integers(4); a, y, v, e, g = (np.rot90(t, k) for t in (a, y, v, e, g))
        if rng.random() < .5: a, y, v, e, g = (t[:, ::-1] for t in (a, y, v, e, g))
        X.append(np.ascontiguousarray(a)); Y.append(np.ascontiguousarray(y)); W.append(np.ascontiguousarray(v * (1 + 4 * e) * (1 + 4 * g)))
    x = torch.from_numpy(np.stack(X)).permute(0, 3, 1, 2).float() / 255
    x = x * torch.empty(B, 1, 1, 1).uniform_(.85, 1.15) + torch.empty(B, 1, 1, 1).uniform_(-.05, .05)
    return (x - MEAN) / STD, torch.from_numpy(np.stack(Y))[:, None].float(), torch.from_numpy(np.stack(W))[:, None].float()
m = UNet(); m.load_state_dict(torch.load(base, map_location="cpu")); m.train()
for mod in m.modules():
    if isinstance(mod, torch.nn.BatchNorm2d): mod.eval(); [p.requires_grad_(False) for p in mod.parameters()]
opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], 5e-5, weight_decay=1e-4)
t0 = time.time(); it = 0; L = []
while time.time() - t0 < MIN * 60:
    x, y, w = batch(); lo = (F.binary_cross_entropy_with_logits(m(x), y, reduction="none") * w).sum() / w.sum()
    opt.zero_grad(); lo.backward(); opt.step(); L.append(lo.item()); it += 1
    if it % 50 == 0: print(it, round(time.time() - t0), round(float(np.mean(L[-50:])), 4), flush=True); torch.save(m.state_dict(), out)
torch.save(m.state_dict(), out); print("done", it)
