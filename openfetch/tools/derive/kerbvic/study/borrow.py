import json, sys, numpy as np
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic")
import mbdem
dem = mbdem.Dem("../run/brunswick/dem"); R = json.load(open("../data/brunswick/m.json")); g = {}
for r in R:
    if r['w'] is None or r['c'] is None or r['c'] > 31 or r['w'] > 69 or not r['road']: continue
    g.setdefault((r['b'], r['road']), []).append(r)
def prof(G, reach):
    P = np.array([[r['x'], r['y']] for r in G]); N = np.array([[r['nx'], r['ny']] for r in G]); t = np.arange(0, reach + 1e-6, .25)
    H = dem.height(P[:, 0][:, None] + N[:, 0][:, None] * t, P[:, 1][:, None] + N[:, 1][:, None] * t)
    H = H - np.nanmedian(H[:, (t >= .3) & (t <= 1)], axis=1)[:, None]; ok = np.isfinite(H).all(axis=1)
    return (t, np.median(H[ok], axis=0)) if ok.sum() >= 6 else (None, None)
def valley_at(t, p, x, tol=0.75, dip=0.02):
    best = -1
    for i in np.flatnonzero(abs(t - (x + mbdem.GUT_K)) <= tol):
        left = p[(t >= .3) & (t < t[i])].max() if ((t >= .3) & (t < t[i])).any() else p[i]; best = max(best, min(left, p[i:].max()) - p[i])
    return best >= dip
S = {}
for k, G in g.items():
    if len(G) < 6: continue
    W = np.median([r['w'] for r in G]); P = np.array([[r['x'], r['y']] for r in G]); N = np.array([[r['nx'], r['ny']] for r in G])
    S[k] = (G, W, mbdem.side_width(dem, P, N, np.array([r['w'] for r in G]) / 2))
ok = bad = rej = 0; E = []
for k, (G, W, d) in S.items():
    if d is None: continue
    st = [v[2] for j, v in S.items() if j != k and j[1] == k[1] and v[2] is not None and abs(v[1] - W) < 2]
    if len(st) < 2: continue
    b = float(np.median(st)); t, p = prof(G, W / 2)
    if t is None or not valley_at(t, p, b): rej += 1; continue
    E.append(abs(b - d))
E = np.array(E)
print("held-out measured sides: borrowed+gated", len(E), "rejected by gate", rej, "<1m %.2f <1.5m %.2f >3m %.3f" % (np.mean(E < 1), np.mean(E < 1.5), np.mean(E > 3)))
un = [k for k, v in S.items() if v[2] is None]; got = 0
for k in un:
    G, W, _ = S[k]; st = [v[2] for j, v in S.items() if j[1] == k[1] and v[2] is not None and abs(v[1] - W) < 2]
    if len(st) < 2: continue
    t, p = prof(G, W / 2)
    if t is not None and valley_at(t, p, float(np.median(st))): got += 1
print("unmeasured sides", len(un), "recovered by gated borrowing", got)
