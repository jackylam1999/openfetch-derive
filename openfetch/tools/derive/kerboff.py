"""Short misses drawn 1-2 m off (kerbshort.py "off"): is the drawn line or the council line on the kerb? The LiDAR step fit (kerbstep.py)
judges: median fitted step at the council sample vs at the nearest point of the drawn line.  usage: python kerboff.py kp_dir step_dir box"""
import sys, json
import numpy as np
from scipy import ndimage
import compare_kerbs as ck
import kerbstep as ks
from shapely.geometry import Point, box as sbox
from shapely.ops import nearest_points

src, sd, nm = sys.argv[1:4]
m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
D, R = ck.lines(f"{sd}/{nm}_derived.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
ks.AWAY = 0; tr, up, ok, nr, nc = ks.grids(src, nm, D)
U = ndimage.maximum_filter(up, 3)  # strongest step within 0.25 m
xy = ck.samples(R); d = ck.dist(xy, D); s = (d > 1) & (d <= 2.5); xy = xy[s]; d = d[s]
from shapely.strtree import STRtree
t = STRtree(D); inv = ~tr; a, b = [], []
for x, y in xy[::4]:
    p = Point(x, y); q = nearest_points(p, D[t.nearest(p)])[1]
    for (X, Y), out in (((x, y), a), ((q.x, q.y), b)):
        c, r = inv * (X, Y); out.append(U[int(np.clip(r, 0, U.shape[0] - 1)), int(np.clip(c, 0, U.shape[1] - 1))])
a, b = np.array(a), np.array(b)
print(nm, "council samples 1-2.5 m from a drawn line:", len(xy), "(", round(len(xy) * 0.5 / 1000, 2), "km ), offset median", round(float(np.median(d)), 2))
print("  step at council line: median", round(float(np.median(a)), 3), " >= 4 cm", round(float((a >= .04).mean()), 2))
print("  step at drawn line:   median", round(float(np.median(b)), 3), " >= 4 cm", round(float((b >= .04).mean()), 2))
print("  drawn line has the bigger step", round(float((b > a).mean()), 2))
