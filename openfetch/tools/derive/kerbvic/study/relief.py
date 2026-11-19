import json, sys, numpy as np
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic"); import mbdem
def relief_width(dem, P, N, reach_m, dmin=1.0, dmax=7.0, deep=0.03, need=0.4, iqr=1.0, half=5.0):
    reach = float(np.nanmedian(reach_m))
    if reach < dmin + 1.5: return None
    t = np.arange(-half, reach + half + 1e-6, 0.25)
    X = P[:, 0][:, None] + N[:, 0][:, None] * t; Y = P[:, 1][:, None] + N[:, 1][:, None] * t
    H = dem.height(X, Y)
    k = int(half / 0.25); w = np.ones(2 * k + 1) / (2 * k + 1)
    vals = []
    for h in H:
        if not np.isfinite(h).all(): continue
        sm = np.convolve(h, w, mode="same"); rel = h - sm
        win = (t >= dmin + mbdem.GUT_K) & (t <= min(dmax + mbdem.GUT_K, reach - 0.75))
        idx = np.flatnonzero(win)
        if not len(idx): continue
        i = idx[np.argmin(rel[idx])]
        if rel[i] <= -deep: vals.append(t[i] - mbdem.GUT_K)
    if len(vals) < max(6, need * len(P)): return None
    q1, q2, q3 = np.percentile(vals, [25, 50, 75])
    return float(q2) if q3 - q1 <= iqr else None
if __name__ == "__main__":
    dem = mbdem.Dem(sys.argv[2]); R = json.load(open(sys.argv[1])); g = {}
    for r in R:
        if r['w'] is None or r['c'] is None or r['c'] > 31 or r['w'] > 69 or r['w'] < 7.5 or not r['road']: continue
        g.setdefault((r['b'], r['road']), []).append(r)
    out = []
    for k, G in g.items():
        if len(G) < 6: continue
        W = np.median([r['w'] for r in G]); P = np.array([[r['x'], r['y']] for r in G]); N = np.array([[r['nx'], r['ny']] for r in G])
        a = mbdem.side_width(dem, P, N, np.full(len(G), W / 2)); b = relief_width(dem, P, N, np.full(len(G), W / 2))
        s = [r['s'] for r in G if r.get('s') and 0.5 < r['s'] < min(8, .35 * W)]
        o = 2.17 * np.median(s) if len(s) >= max(5, .4 * len(G)) else None
        out.append((len(G), W, a, b, o))
    n = len(out); print("sides", n, "valley", sum(x[2] is not None for x in out), "relief", sum(x[3] is not None for x in out), "either", sum(x[2] is not None or x[3] is not None for x in out))
    for j, nm in ((2, "valley"), (3, "relief")):
        B = [(x[j], x[4]) for x in out if x[j] is not None and x[4] is not None]; E = np.array([a - b for a, b in B])
        print(nm, "vs osm", len(B), "<1m %.2f <1.5m %.2f >3m %.3f med %.2f" % (np.mean(abs(E) < 1), np.mean(abs(E) < 1.5), np.mean(abs(E) > 3), np.median(E)))
    B = [(x[2], x[3]) for x in out if x[2] is not None and x[3] is not None]; E = np.array([a - b for a, b in B]); print("valley vs relief", len(B), "<0.5 %.2f <1 %.2f" % (np.mean(abs(E) < .5), np.mean(abs(E) < 1)))
