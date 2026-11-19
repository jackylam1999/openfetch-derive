import sys, json, numpy as np, torch
sys.path.insert(0, sys.argv[1]); from unet import UNet, predict
from chunks import chunks
S, box = sys.argv[1], sys.argv[2]
m = UNet(); m.load_state_dict(torch.load(f"{S}/unet.pt", map_location="cpu")); torch.set_num_threads(4)
z = np.load(f"{S}/train_{box}.npz"); x0, y1, res = z["origin"]
import os
pf = f"{S}/prob_{box}.npy"
prob = np.load(pf) if os.path.exists(pf) and len(sys.argv) > 3 else predict(m, z["img"]); np.save(pf, prob.astype(np.float16))
rows = json.load(open(f"{S}/meas/{box}.json")); H, W = prob.shape
OFF = np.arange(0.25, 15, 0.25)
def kerb(r):
    p = np.array([r["x"], r["y"]]); n = np.array([r["nx"], r["ny"]]); hi = min(r["w"] / 2 + 1.0, 15) if r["w"] else 15
    pts = p[None] + n[None] * OFF[:, None]; c = ((pts[:, 0] - x0) / res).astype(int); rr = ((y1 - pts[:, 1]) / res).astype(int)
    if c.min() < 0 or rr.min() < 0 or c.max() >= W or rr.max() >= H: return None
    v = prob[rr, c].astype(float); run = np.convolve(v, np.ones(4) / 4, "full")[3:]   # mean of next 1 m
    for j, o in enumerate(OFF):
        if o > hi: return None
        if run[j] > 0.5: return o
    return None
k = [kerb(r) for r in rows]
E1 = np.array([abs(a - r["d"]) for a, r in zip(k, rows) if a is not None and r["d"] is not None and r["w"] and 7.5 < r["w"] < 65 and r["d"] < 12])
print(box, "per sample: n", len(E1), "within1", np.mean(E1 < 1).round(3), "within2", np.mean(E1 < 2).round(3), "med", np.median(E1).round(2))
# per chunk median (side-ish)
C = chunks(rows, n=15); E2 = []; S2 = []
for c in C:
    a = [k[i] for i in c if k[i] is not None]; d = [rows[i]["d"] for i in c if rows[i]["d"] is not None]
    if len(a) < len(c) * 0.5 or len(d) < len(c) * 0.5 or np.ptp(d) > 1.0: continue
    E2.append(abs(np.median(a) - np.median(d))); S2.append(np.percentile(a, 75) - np.percentile(a, 25))
E2 = np.array(E2); S2 = np.array(S2)
print(box, "per 30 m chunk: n", len(E2), "within1", np.mean(E2 < 1).round(3), "within2", np.mean(E2 < 2).round(3), "med", np.median(E2).round(2))
for q in (0.5, 1.0):
    s = S2 <= q; print(f"  chunks with IQR<={q}: kept {s.mean():.2f} within1 {np.mean(E2[s] < 1):.3f} within2 {np.mean(E2[s] < 2):.3f}")
