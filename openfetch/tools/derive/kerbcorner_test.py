"""kerblot --corner-mitre (scenario 13, 21 Nov 2026): convex kerb corners come from the two kerb offset lines, never a bulge past the
narrower street's kerb, never a cut inside it; concave corners and width steps along one street are unchanged."""
import sys
import numpy as np
sys.argv = sys.argv[:1]
import kerblot as kl
from shapely.geometry import Polygon, Point, box


def build(comp, wfun, mitre):
    kl.CORNER_MITRE = mitre
    P, N = kl.front_samples(comp)
    D = np.array([wfun(p) for p in P])
    return kl.band(comp, P, D)


# 90 deg: 40 m square block, south side 9.4 m wide verge, the rest 3.5 m
sq = box(0, 0, 40, 40)
w = lambda p: 9.4 if p[1] < 0.01 and 0.01 < p[0] < 39.99 else 3.5
old, new = build(sq, w, False), build(sq, w, True)
east_old = old.intersection(box(40, -20, 80, 0)).bounds[2] - 40
east_new = new.intersection(box(40, -20, 80, 0)).bounds[2] - 40
assert east_old > 6.0, east_old                    # the old circle bulges 7-9.4 m into the east street (v13)
assert abs(east_new - 3.5) < 0.15, east_new        # the corner now stops on the east kerb line
assert new.covers(Point(43.4, -9.3)) and new.covers(Point(-3.4, -9.3))   # and reaches the true kerb corner (lot corner + 9.4 S + 3.5 E)
assert abs(new.bounds[1] + 9.4) < 0.15             # south kerb still 9.4 m out
assert new.intersection(box(10, -20, 30, 0)).symmetric_difference(old.intersection(box(10, -20, 30, 0))).area < 0.05   # mid-side unchanged

# width step along one straight street (no corner): unchanged
long_ = box(0, 0, 120, 30)
ws = lambda p: (6.0 if p[0] < 60 else 3.0) if p[1] < 0.01 else 3.5
a, b = build(long_, ws, False), build(long_, ws, True)
mid = box(20, -10, 100, 0)
assert a.intersection(mid).symmetric_difference(b.intersection(mid)).area < 0.05

# 45, 90 and 135 deg interior angles (a right triangle, a splayed corner): out along the corner's bisector the kerb lies between the
# width and MITRE_LIM x the width (an acute corner is rounded off, never a spike)
from shapely.geometry import LineString
for comp in (Polygon([(0, 0), (60, 0), (0, 60)]), Polygon([(0, 0), (50, 0), (60, 10), (60, 50), (0, 50)])):
    cs = list(comp.exterior.coords)[:-1]
    for wv in (3.5, 6.0):
        nb = build(comp, lambda p: wv, True)
        for i, v in enumerate(cs):
            u1 = np.subtract(cs[i - 1], v); u2 = np.subtract(cs[(i + 1) % len(cs)], v)
            bis = -(u1 / np.linalg.norm(u1) + u2 / np.linalg.norm(u2))
            if np.linalg.norm(bis) < 1e-6:
                continue
            bis /= np.linalg.norm(bis)
            ray = LineString([v, tuple(np.add(v, bis * 4 * wv))])
            ext = max(Point(v).distance(Point(c)) for c in ray.intersection(nb).coords)
            assert wv - 0.3 <= ext <= kl.MITRE_LIM * wv + 0.3, (v, wv, ext)

# concave (L-shaped block): the inside corner keeps the circles
L = Polygon([(0, 0), (60, 0), (60, 30), (30, 30), (30, 60), (0, 60)])
wl = lambda p: 4.0
a, b = build(L, wl, False), build(L, wl, True)
inner = Point(30, 30).buffer(8)
assert a.intersection(inner).symmetric_difference(b.intersection(inner)).area < 0.5
kl.CORNER_MITRE = False
print("kerbcorner_test pass")
