"""twolev.py sides.json com-kerbs.json : for two-level sides, error vs council kerb of near level, far level, median (per side, metres)"""
import json, sys, warnings, numpy as np; warnings.filterwarnings("ignore")
import shapely
from shapely.geometry import shape, LineString
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
S = json.load(open(sys.argv[1])); cls = json.load(open(sys.argv[1].replace(".json", ".cls.json")))
K = [transform(TO, shape(f["geometry"])).buffer(0) for f in json.load(open(sys.argv[2]))["features"] if f["geometry"]]
KT = STRtree(K)
def levels(k):
    ks = np.sort(k); g = int(np.argmax(np.diff(ks))); return ks[:g + 1], ks[g + 1:]
rows = []
for i in cls.get("two levels", []):
    s = S[i]; P = np.array(s["P"]); N = np.array(s["N"]); tr = []
    for p, n in zip(P, N):
        ray = LineString([p + n * .3, p + n * 14]); tt = [np.hypot(*(q - p)) for g in [K[int(j)] for j in KT.query(ray)] for q in shapely.get_coordinates(ray.intersection(g.boundary))]
        tr.append(min(tt) if tt else np.nan)
    tr = np.array(tr)
    if np.isfinite(tr).mean() < .5: continue
    T = np.nanmedian(tr); a, b = levels(np.array(s["k"]))
    rows.append((i, len(P) * 2, T, np.median(a) - T, np.median(b) - T, np.median(s["k"]) - T, len(a), len(b)))
for r in rows: print("side %4d %3d m truth %.1f  near %+.1f  far %+.1f  median %+.1f  (n %d/%d)" % r)
r = np.array([x[3:6] for x in rows]) if rows else np.zeros((0, 3))
if len(r): print("within 1 m: near %.2f far %.2f median %.2f ; within 3 m: near %.2f far %.2f median %.2f" % tuple([np.mean(np.abs(r[:, j]) < 1) for j in range(3)] + [np.mean(np.abs(r[:, j]) < 3) for j in range(3)]))
