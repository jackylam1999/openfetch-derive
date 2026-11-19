import sys, os, numpy as np, pickle
sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive"); sys.path.insert(0, "/home/user/openfetch-derive/openfetch/tools/derive/kerbvic")
import kerblot as kl, mbdem
kl.EPSG, kl.C_MAX, kl.RAY, kl.NARROW_JOIN_FH, kl.SHORT_SIDE, kl.MITRE, kl.SAME_STREET_SPREAD = 7855, 31.0, 70.0, (6,), 30.0, True, 1.0
p = sys.argv[1]; x, y = float(sys.argv[2]), float(sys.argv[3]); cells = sys.argv[4]
kl.GUTTER = mbdem.Dem(p + "/dem")
om = kl.mitre_parts
def mp(P, N, D, CID, fan=25.0):
    if np.min(np.hypot(P[:, 0] - x, P[:, 1] - y)) < 12:
        pickle.dump((P, N, D, CID), open(sys.argv[5], "wb"))
    return om(P, N, D, CID, fan)
kl.mitre_parts = mp
open("/tmp/claude-0/-home-user/5914eee7-ef98-5e38-b0e7-54f4cc67f6ea/scratchpad/vk/cells1.txt", "w").write(cells + "\n")
kl.main([f"{p}/lots", f"{p}/roads", f"{p}/empty.geojson", f"{p}/empty.geojson", f"{p}/bld", "/tmp/claude-0/-home-user/5914eee7-ef98-5e38-b0e7-54f4cc67f6ea/scratchpad/vk/cells1.txt", "/dev/null", "--sidewalks", f"{p}/sidewalks.geojson", "--no-borrow"])
