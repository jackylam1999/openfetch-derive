"""Selftest (21 Nov 2026, scenario 17 paved corners): a square block whose corner lot is cut back 14 m (splay / paved corner) gets its
kerb corner where the two kerb lines meet when kerblot.SPLAY_FAR is on, and the old 14 m chord when it is off; an acute corner keeps the chord.
    python3 test_splay.py"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import kerblot as kl
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
def corner_cover(poly, D, far):
    kl.SPLAY_FAR = far
    P, N = kl.front_samples(poly)
    nm = np.array([np.degrees(np.arctan2(n[1], n[0])) for n in N])
    CID = np.round(nm / 90).astype(int) % 4
    return unary_union(kl.mitre_parts(P, N, np.full(len(P), D), CID))
sq = Polygon([(0, 0), (80, 0), (80, 70), (10, 70), (0, 60)])            # NW corner cut back 10 m x 10 m (14 m chord)
kerb_corner = Point(-2.0, 71.0)                                          # inside the square kerb corner (kerb 3 m out)
on, off = corner_cover(sq, 3.0, 20.0), corner_cover(sq, 3.0, 0.0)
assert on.buffer(0.01).contains(kerb_corner), "splay corner not squared"
assert not off.buffer(0.01).contains(kerb_corner), "old chord expected when SPLAY_FAR is 0"
ac = Polygon([(0, 0), (80, 0), (80, 70), (0, 25)])                       # acute NW corner (about 30 deg), no cut-back
a_on, a_off = corner_cover(ac, 3.0, 20.0), corner_cover(ac, 3.0, 0.0)
assert abs(a_on.area - a_off.area) < 1.0, "acute corner must not change"
print("test_splay OK")
