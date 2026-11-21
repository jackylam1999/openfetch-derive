"""fewwhy.py sides.json : for 'few reads' sides, why each ray found no kerb"""
import json, sys, numpy as np, collections
S = json.load(open(sys.argv[1])); cls = json.load(open(sys.argv[1].replace(".json", ".cls.json")))
c = collections.Counter(); per = collections.Counter()
for i in cls.get("few reads", []):
    s = S[i]; V = np.array(s["prof"]); t = s["t0"] + 0.25 * np.arange(V.shape[1]); sc = collections.Counter()
    for v in V:
        if (v < 0).any(): sc["no aerial"] += 1; continue
        run = np.convolve(v, np.ones(4) / 4, "full")[3:]
        far = np.array([np.median(v[q:q + 10]) for q in range(len(t))])
        a = np.flatnonzero(run > 0.5)
        if not len(a): sc["never road"] += 1; continue
        b = np.flatnonzero((run > 0.5) & (far > 0.5))
        if not len(b): sc["road but short (<2.5 m)"] += 1; continue
        if t[b[0]] < 0.75: sc["road at lot front"] += 1; continue
        sc["road past reach"] += 1
    w = sc.most_common(1)[0][0]; c[w] += 1; per[w] += 2 * len(V)
for w in c: print(f"{w:26s} sides {c[w]:4d} m {per[w]}")
