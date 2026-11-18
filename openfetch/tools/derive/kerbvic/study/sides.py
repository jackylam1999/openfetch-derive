import json, sys, numpy as np
def sides(rows):
    out = {}
    for r in rows:
        if r["w"] is None or r["c"] is None or r["c"] > 16 or r["road"] is None: continue
        k = (r["b"], r["road"]); out.setdefault(k, []).append(r)
    res = []
    for k, R in out.items():
        if len(R) < 5: continue
        d = [r["d"] for r in R if r["d"] is not None and 0.5 < r["d"] < 9]
        t = [x for r in R for x in r.get("t", [])]
        res.append({"k": list(k), "n": len(R), "len": 2 * len(R), "d": float(np.median(d)) if len(d) >= 0.6 * len(R) else None,
                    "dsp": float(np.subtract(*np.percentile(d, [75, 25]))) if len(d) >= 3 else None,
                    "w": float(np.median([r["w"] for r in R])), "c": float(np.median([r["c"] for r in R])), "cls": R[0]["cls"], "div": R[0]["div"],
                    "t": t, "rows": R})
    return res
if __name__ == "__main__":
    for p in sys.argv[1:]:
        S = sides(json.load(open(p)))
        G = [s for s in S if s["d"] is not None]
        print(p.split("/")[-2], "sides", len(S), "with truth", len(G), "len", sum(s["len"] for s in G))
        d = np.array([s["d"] for s in G]); w = np.array([s["w"] for s in G]); c = np.array([s["c"] for s in G])
        print(" truth d pct", np.percentile(d, [10, 25, 50, 75, 90]).round(2))
        for lo, hi in [(0, 12), (12, 18), (18, 22), (22, 27), (27, 33), (33, 45)]:
            m = (w >= lo) & (w < hi)
            if m.sum(): print(f"  W {lo}-{hi}: n={m.sum()} d med={np.median(d[m]):.2f} iqr={np.subtract(*np.percentile(d[m],[75,25])):.2f} d/W={np.median(d[m]/w[m]):.3f}")
        nt = [s for s in G if len(s["t"]) >= 3]
        e = np.array([np.median(s["t"]) - s["d"] for s in nt])
        print(" tree sides", len(nt), "tree-minus-kerb pct", np.percentile(e, [10, 25, 50, 75, 90]).round(2) if len(e) else None)
