import sys, os, numpy as np
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive"); sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic")
import kerblot as kl, mbdem
kl.EPSG, kl.C_MAX, kl.RAY, kl.NARROW_JOIN_FH, kl.SHORT_SIDE = 7855, 31.0, 70.0, (6,), 30.0
p = sys.argv[1]; kl.GUTTER = mbdem.Dem(p + "/dem")
LOG = []; o2 = kl.two_judge
def tj(rays, m, C, W, P, N, ctx):
    g = ctx["gutter"].side_width(P[m], N[m], W[m] / 2); o = kl.sw_width(rays, m, C, W, ctx)
    LOG.append((int(m.sum()), g, o, float(np.nanmedian(C[m])), float(np.nanmedian(W[m]))))
    return o2(rays, m, C, W, P, N, ctx)
kl.two_judge = tj
kl.main([f"{p}/lots", f"{p}/roads", f"{p}/empty.geojson", f"{p}/empty.geojson", f"{p}/bld", f"{p}/cells.txt", "/dev/null", "--sidewalks", f"{p}/sidewalks.geojson", "--no-borrow"])
both = [l for l in LOG if l[1] is not None and l[2] is not None]
d = np.array([l[1] - l[2] for l in both])
print("sides", len(LOG), "gutter", sum(l[1] is not None for l in LOG), "osm", sum(l[2] is not None for l in LOG), "both", len(both), "|g-o|<1 %.2f <1.5 %.2f med %.2f" % (np.mean(abs(d) < 1), np.mean(abs(d) < 1.5), np.median(d)))
for l in [l for l in both if abs(l[1] - l[2]) > 1.5][:20]: print("n=%d g=%.2f o=%.2f C=%.1f W=%.1f" % l)
none = [l for l in LOG if l[1] is None and l[2] is None and l[0] * 2 >= 30]
print("unmeasured long sides", len(none)); W = np.array([l[4] for l in none]); print("W pct", np.percentile(W, [10, 25, 50, 75, 90]).round(1), "W>=69:", np.mean(W >= 69))
