import json, numpy as np, sys
B = ['carlton','northmelb','kensington','eastmelb','parkville']
def load(b):
    R = json.load(open(f'../data/{b}/m.json'))
    return [r for r in R if r['w'] is not None and r['c'] is not None and r['c'] < 16 and r['road']]
ALL = {b: load(b) for b in B}
def sides(R):
    g = {}
    for r in R: g.setdefault((r['b'], r['road']), []).append(r)
    return g
def feats(G, smax_frac=0.35, cov=0.4):
    W = np.median([r['w'] for r in G])
    s = [r['s'] for r in G if r.get('s') and r['s'] < min(8, smax_frac * W)]
    t = [x for r in G for x in r.get('t', []) if x < 0.45 * W]
    return W, (np.median(s) if len(s) >= max(5, cov * len(G)) else None), (np.median(t) if len(t) >= 3 else None)
def predict(W, s, t, P):
    if s is not None:
        d = P['K'] * s
        if P.get('tree') and t is not None and t > d + P['tree']: d = t + P['tadd']
        return float(np.clip(d, 1.0, 7.0))
    if P.get('fallback') == 'tree' and t is not None: return float(np.clip(t + P['tadd2'], 1, 7))
    return None
def evaluate(P, quiet=False):
    tot = {}
    for b in B:
        E = []; cov = 0; n = 0
        for k, G in sides(ALL[b]).items():
            T = [r['d'] for r in G if r['d'] is not None and 0.5 < r['d'] < 9]
            if len(T) < 5: continue
            n += len(T); W, s, t = feats(G, P.get('smax', .35), P.get('cov', .4)); d = predict(W, s, t, P)
            if d is None: continue
            cov += len(T); E += [abs(x - d) for x in T]
        E = np.array(E); tot[b] = (cov / n, np.mean(E < 1), np.mean(E < 1.5), np.mean(E < 2))
        if not quiet: print(f"  {b:11s} covered {cov/n:.2f}  <1m {np.mean(E<1):.2f} <1.5m {np.mean(E<1.5):.2f} <2m {np.mean(E<2):.2f}  >3m {np.mean(E>3):.3f}")
    return tot
if __name__ == "__main__":
    for P in [dict(K=2.17), dict(K=2.17, smax=.3, cov=.5), dict(K=2.17, tree=1.0, tadd=0.8), dict(K=2.17, tree=1.0, tadd=0.5, fallback='tree', tadd2=0.3)]:
        print(P); evaluate(P)
