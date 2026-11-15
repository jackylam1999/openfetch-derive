import sys, json
sys.path.insert(0, sys.argv[1])
import numpy as np, shapely
import kerbaudit as ka
from shapely.geometry import LineString, box, Point
from shapely.strtree import STRtree
from pyproj import Transformer
S = "/tmp/claude-0/-home-user/17bc20c6-45f6-5bb3-8440-d43306115c12/scratchpad/k"
tr = Transformer.from_crs(4326, 7856, always_xy=True).transform
L = [LineString([tr(*c) for c in f["geometry"]["coordinates"]]) for f in json.load(open(S + "/gap-v1.json"))["features"]]
R = [LineString(t) for t in ka.read_kerbs(S + "/in/nsw-traced-raw.json") if len(t) > 1]; RT = STRtree(R)
st = [(g, fh) for g, fh in ka.load_roads(S + "/in/roads") if fh not in ka.SKIP_FH]; SG = [g for g, _ in st]; ST = STRtree(SG)
def feats(g, b=None):
    n = max(2, int(g.length) + 1); P = shapely.points([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, n)])
    if b is not None:
        P = P[shapely.contains(b, P)]; n = len(P)
        if n < 2: return (0, 0.0, 1.0)
    seen = np.zeros(n, bool)
    for k in RT.query(g.buffer(1.5)): seen |= shapely.distance(P, R[int(k)]) < 1.5
    # longest unseen run (ring: wrap)
    s2 = seen if b is not None else np.concatenate([seen, seen]); run = best = 0
    for v in s2:
        run = 0 if v else run + 1; best = max(best, run)
    best = min(best, n)
    near = ST.nearest(P); off = shapely.distance(P, np.asarray(SG, object)[near])
    jump = 0.0
    for i in range(0, n - 30, 5):
        w = slice(i, i + 30)
        if len(set(near[w].tolist())) == 1: jump = max(jump, off[w].max() - off[w].min())
    return best, round(float(jump), 1), round(float(seen.mean()), 2)
T = STRtree(L)
for fn in ("review/verdicts-fresh.json", "review/verdicts-old.json"):
    pl = {p["id"]: p for p in json.load(open(S + "/review/places-" + ("fresh" if "fresh" in fn else "old") + ".json"))}
    for v in json.load(open(S + "/" + fn)):
        if v["verdict"] in ("BLANK",): continue
        p = pl[v["id"]]; b = box(p["x"] - 35, p["y"] - 35, p["x"] + 35, p["y"] + 35)
        F = [feats(L[int(k)], b) for k in T.query(b)]
        if F: print(v["id"], v["verdict"], "unseen_run", max(f[0] for f in F), "jump", max(f[1] for f in F), "seen", min(f[2] for f in F))
