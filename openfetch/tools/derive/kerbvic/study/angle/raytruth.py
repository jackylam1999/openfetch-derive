"""raytruth.py sides.json com-kerbs.json bays.geojson : per ray, true kerb offset (first CoM kerb polygon hit) vs aerial read, split angle / parallel / none"""
import json, sys, warnings, numpy as np, collections; warnings.filterwarnings("ignore")
import shapely
from shapely.geometry import shape, LineString
from shapely.ops import transform
from shapely.strtree import STRtree
from scipy.spatial import cKDTree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
S = json.load(open(sys.argv[1]))
allP = np.vstack([np.array(s["P"]) for s in S]); lo, hi = allP.min(0) - 50, allP.max(0) + 50
K = []
for f in json.load(open(sys.argv[2]))["features"]:
    if not f["geometry"]: continue
    g = transform(TO, shape(f["geometry"]))
    b = g.bounds
    if b[2] < lo[0] or b[0] > hi[0] or b[3] < lo[1] or b[1] > hi[1]: continue
    K.append(g.buffer(0))
KT = STRtree(K)
bp = np.array([TO(*f["geometry"]["coordinates"]) for f in json.load(open(sys.argv[3]))["features"] if f["geometry"]])
dd, _ = cKDTree(bp).query(bp, 2); ka = cKDTree(bp[dd[:, 1] < 3.3]); kp = cKDTree(bp[dd[:, 1] >= 3.3])
R = collections.defaultdict(list); BZ = collections.defaultdict(list)
for s in S:
    P = np.array(s["P"]); N = np.array(s["N"]); V = np.array(s["prof"]); t = s["t0"] + .25 * np.arange(V.shape[1])
    for p, n, v in zip(P, N, V):
        if (v < 0).any(): continue
        ray = LineString([p + n * 0.3, p + n * 14])
        hits = [K[int(i)] for i in KT.query(ray)]
        tt = [LineString([p, q]).length for g in hits for q in [np.array(x) for x in shapely.get_coordinates(ray.intersection(g.boundary))]]
        if not tt: continue
        tr = min(tt)
        q = p + n * (tr + 2.5)
        c = "angle" if ka.query(q)[0] < 4 else ("parallel" if kp.query(q)[0] < 4 else "none")
        run = np.convolve(v, np.ones(4) / 4, "full")[3:]; far = np.array([np.median(v[i:i + 10]) for i in range(len(t))])
        j = np.flatnonzero((run > .5) & (far > .5) & (t >= .75))
        R[c].append(t[j[0]] - tr if len(j) else np.nan)
        BZ[c].append(np.interp(tr + np.arange(-2, 8.01, 0.5), t, v, left=np.nan, right=np.nan))
for c in R:
    e = np.array(R[c]); ok = np.isfinite(e); ee = e[ok]
    print(f"{c:9s} rays {len(e):5d} read {ok.mean():.2f}  |err|<1 {np.mean(np.abs(ee)<1):.2f}  read beyond kerb >2m {np.mean(ee>2):.2f}  inside <-2m {np.mean(ee<-2):.2f}  median {np.median(ee):+.2f}")
    print("   prob at kerb-2..+8 m:", " ".join(f"{x:.2f}" for x in np.nanmean(np.array(BZ[c]), 0)))
    if len(sys.argv) > 4: np.save(sys.argv[4] + c + ".npy", np.array(BZ[c]))
