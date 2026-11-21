"""h3.py sides.json [com-kerbs.json] : two-level sides whose levels form contiguous runs along the side (stepped kerb) vs interleaved;
per-sample error vs council kerb of per-run level vs whole-side median"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
S = json.load(open(sys.argv[1])); cls = json.load(open(sys.argv[1].replace(".json", ".cls.json")))
truth = len(sys.argv) > 2
if truth:
    import shapely
    from shapely.geometry import shape, LineString
    from shapely.ops import transform
    from shapely.strtree import STRtree
    from pyproj import Transformer
    TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
    K = [transform(TO, shape(f["geometry"])).buffer(0) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]]; KT = STRtree(K)
def read(v, t):
    run = np.convolve(v, np.ones(4) / 4, "full")[3:]; far = np.array([np.median(v[q:q + 10]) for q in range(len(t))])
    j = np.flatnonzero((run > .5) & (far > .5) & (t >= .75)); return t[j[0]] if len(j) else np.nan
E = {"run": [], "median": []}; nc = ni = 0
for i in cls.get("two levels", []):
    s = S[i]; P = np.array(s["P"]); N = np.array(s["N"]); V = np.array(s["prof"]); t = s["t0"] + .25 * np.arange(V.shape[1])
    r = np.array([read(v, t) if (v >= 0).all() else np.nan for v in V]); ok = np.isfinite(r)
    ks = np.sort(r[ok]); g = int(np.argmax(np.diff(ks))); cut = (ks[g] + ks[g + 1]) / 2
    lab = np.where(ok, (r > cut).astype(int), -1)
    idx = np.flatnonzero(ok); L = lab[idx]
    Lf = np.array([np.bincount(L[max(0, q - 1):q + 2]).argmax() for q in range(len(L))])
    ch = int(np.sum(Lf[1:] != Lf[:-1])); runs = np.split(np.arange(len(Lf)), np.flatnonzero(np.diff(Lf)) + 1)
    contig = ch <= 2 and min(len(x) for x in runs) >= 3
    nc += contig; ni += not contig
    if not truth or not contig: continue
    lev = {0: np.median(r[ok][Lf == 0]), 1: np.median(r[ok][Lf == 1])}; med = np.median(r[ok])
    for q, p, n in zip(range(len(idx)), P[idx], N[idx]):
        ray = LineString([p + n * .3, p + n * 14]); tt = [np.hypot(*(c - p)) for gg in [K[int(j)] for j in KT.query(ray)] for c in shapely.get_coordinates(ray.intersection(gg.boundary))]
        if not tt: continue
        tr = min(tt); E["run"].append(lev[Lf[q]] - tr); E["median"].append(med - tr)
print("two-level sides: contiguous runs", nc, "interleaved", ni)
for k, e in E.items():
    if e: e = np.array(e); print(f"{k:7s} samples {len(e)} within 1 m {np.mean(np.abs(e)<1):.2f} within 3 m {np.mean(np.abs(e)<3):.2f}")
