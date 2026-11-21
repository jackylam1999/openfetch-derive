"""corner_cap (kerblot --corner-cap, scenario 13 v13, 21 Nov 2026): a wide side meeting a narrow one at a corner tapers, never bulges."""
import sys
import numpy as np
sys.argv = sys.argv[:1]
import kerblot as kl

P = np.array([[x, 0.0] for x in range(-40, 1, 2)] + [[0.0, y] for y in range(2, 41, 2)])   # lot corner at the origin
D = np.r_[np.full(21, 9.4), np.full(20, 3.5)]                                             # 9.4 m wide verge, 3.5 m cross street
o = kl.corner_cap(P, D)
assert np.all(o <= D + 1e-9)
assert o[20] <= 3.5 + 2.0 + 1e-9, o[20]                     # the corner sample no longer reaches 9.4 m into the cross street
assert np.allclose(o[:15], 9.4) and np.allclose(o[21:], 3.5)   # sides away from the corner keep their own widths
for i in range(len(P)):
    for j in range(len(P)):
        if abs(i - j) <= 8:
            assert o[i] <= o[j] + np.hypot(*(P[i] - P[j])) + 1e-6
assert np.allclose(kl.corner_cap(P, np.full(len(P), 4.0)), 4.0)   # one width everywhere: unchanged
print("kerbcorner_test pass")
