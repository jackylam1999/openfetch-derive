"""sidestat.py sides.json : why each aerial side read fails (too few reads, two levels, spread) and metres"""
import json, sys, numpy as np, collections
S = json.load(open(sys.argv[1])); c = collections.Counter(); m = collections.Counter(); ex = collections.defaultdict(list)
for i, s in enumerate(S):
    k = np.array(s["k"]); n = len(s["P"])
    if len(k) < max(4, 0.5 * n): w = "few reads"
    else:
        ks = np.sort(k); g = np.diff(ks)
        if g.max() > 1.2 and min(int(np.argmax(g)) + 1, len(ks) - int(np.argmax(g)) - 1) >= max(2, 0.15 * len(ks)): w = "two levels"
        else:
            q1, q3 = np.percentile(k, [25, 75]); w = "spread" if q3 - q1 > 1.5 else "ok"
    c[w] += 1; m[w] += 2 * n; ex[w].append(i)
for w in c: print(f"{w:12s} sides {c[w]:4d}  m {m[w]:6d}")
json.dump(ex, open(sys.argv[1].replace(".json", ".cls.json"), "w"))
