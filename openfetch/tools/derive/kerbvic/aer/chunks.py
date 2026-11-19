"""Group lot-front rows into chunks (same block, same street, consecutive, <=8 samples); chunk profile = median of its rows' profiles."""
import json, numpy as np
def chunks(rows, n=8):
    out = []; cur = []
    def flush():
        if len(cur) >= 3: out.append(list(cur))
        cur.clear()
    for i, r in enumerate(rows):
        if cur:
            p = rows[cur[-1]]
            if r["b"] != p["b"] or r["road"] != p["road"] or r["road"] is None or abs(r["v"] - p["v"]) > 2.5 or r["nx"] * p["nx"] + r["ny"] * p["ny"] < 0.95 or len(cur) >= n:
                flush()
        if r["road"] is not None and r["w"] is not None: cur.append(i)
    flush(); return out
def load(box, S):
    rows = json.load(open(f"{S}/meas/{box}.json")); pr = np.load(f"{S}/meas/{box}_pr.npy").astype(np.float32)
    C = chunks(rows); X = []; meta = []
    for c in C:
        d = [rows[i]["d"] for i in c if rows[i]["d"] is not None]
        td = float(np.median(d)) if len(d) >= max(2, len(c) // 2) and np.ptp(d) < 1.0 else None
        X.append(np.median(pr[c], 0)); meta.append({"box": box, "idx": c, "d": td, "w": float(np.median([rows[i]["w"] for i in c])), "cls": rows[c[0]]["cls"]})
    return np.array(X), meta
