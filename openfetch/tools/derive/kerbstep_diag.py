"""Which kerbstep.py test drops the council kerb in missed stretches? usage: python kerbstep_diag.py kp_dir step_dir box"""
import sys, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import compare_kerbs as ck
import kerbstep as ks
from shapely.geometry import box as sbox

src, sd, nm = sys.argv[1:4]
ks.FLAT, ks.AWAY = float(sys.argv[4]), float(sys.argv[5]); ks.LOTPAD = None if sys.argv[6] == 'none' else float(sys.argv[6])
m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
D, R = ck.lines(f"{sd}/{nm}_derived.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
dem = np.load(f"{src}/{nm}_dem.npy"); n = dem.shape[0]
ks.DIAG = True; tr, up, ok, nr, nc, parts = ks.grids(src, nm, D)
x0, y0 = kl.BX[nm]
cl = ks.burn(f"{src}/{nm}_roads.geojson", n, tr, True); dist = ndimage.distance_transform_edt(~cl) * ks.G
lot = ks.burn(f"{src}/{nm}_lots.geojson", n, tr)
xy = ck.samples(R); miss = ck.dist(xy, D) > 1; xy = xy[miss]
c, r = ~tr * (xy[:, 0], xy[:, 1]); r, c = np.clip(r.astype(int), 0, n - 1), np.clip(c.astype(int), 0, n - 1)
M = lambda a: ndimage.maximum_filter(a, 9)[r, c]  # anywhere within 1 m
print(nm, "missed samples", len(xy), "BX", (x0, y0), "box", m["box"])
print(" has ground", np.isfinite(dem)[r, c].mean().round(3))
print(" dist to centreline m: pct 10/50/90", np.percentile(dist[r, c], [10, 50, 90]).round(1))
print(" in lot", lot[r, c].mean().round(3), " lot within 1 m", M(lot.astype(np.uint8)).mean().round(3))
print(" max up within 1 m: pct 10/50/90", np.percentile(M(up), [10, 50, 90]).round(3))
print(" signed: max -up within 1 m pct 50/90", np.percentile(M(-up), [50, 90]).round(3))
for k, v in parts.items():
    print(" ", k, "within 1 m", M(v.astype(np.uint8)).mean().round(3), " with up>=.04", M((v & (up >= .04)).astype(np.uint8)).mean().round(3))
print(" ok within 1 m", M(ok.astype(np.uint8)).mean().round(3), " ok&up>=.04", M((ok & (up >= .04)).astype(np.uint8)).mean().round(3))
K = ok & (up >= .06); print(" candidate cells (up>=.06)", int(K.sum()), " of which within 1 m of any council kerb", round(float((ndimage.distance_transform_edt(~ks.burn_lines(R, n, tr)) * ks.G <= 1)[K].mean()), 3))
