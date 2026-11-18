import numpy as np
from ev2 import ALL, B, sides, feats
K = 2.17
def wbin(W): return int(round(W / 2.0))
def chain(R, arche=True):
    S = sides(R); F = {k: feats(G) for k, G in S.items()}
    street = {}
    for k, (W, s, t) in F.items():
        if s is not None: street.setdefault(k[1], []).append((W, K * s))
    arch = {}
    for k, (W, s, t) in F.items():
        if s is not None: arch.setdefault(wbin(W), []).append(K * s)
    out = {}
    for k, (W, s, t) in F.items():
        if s is not None: out[k] = (np.clip(K * s, 1, 7), 'side'); continue
        st = [d for w, d in street.get(k[1], []) if abs(w - W) < 3]
        if st: out[k] = (np.clip(np.median(st), 1, 7), 'street'); continue
        a = arch.get(wbin(W), [])
        if arche and len(a) >= 4 and np.subtract(*np.percentile(a, [75, 25])) < 1.5: out[k] = (np.median(a), 'arch'); continue
    return S, out
for b in B:
    S, out = chain(ALL[b]); E = {}; n = 0
    for k, G in S.items():
        T = [r['d'] for r in G if r['d'] is not None and 0.5 < r['d'] < 9]
        if len(T) < 5: continue
        n += len(T)
        if k in out: E.setdefault(out[k][1], []).extend(abs(x - out[k][0]) for x in T)
    line = f"{b:11s} "
    for tier in ('side', 'street', 'arch'):
        e = np.array(E.get(tier, []))
        if len(e): line += f"{tier}: share {len(e)/n:.2f} <1m {np.mean(e<1):.2f} <2m {np.mean(e<2):.2f} >3m {np.mean(e>3):.3f} | "
    print(line)
