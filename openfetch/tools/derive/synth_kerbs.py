#!/usr/bin/env python3
"""Synthetic ground points with known kerbs, to test kerbs.py without real data.

Usage: python3 tools/derive/synth_kerbs.py out.laz truth.geojson lots.geojson [--density 6] [--noise 0.03] [--seed 1]
300 m box of 8 m roads between blocks with 6 m rounded kerb returns. Ground: sloping plane, road 0.15 m below the verge at the
kerb face with a 0.1 m crown, 4 m driveway laybacks (0.03 m step), houses (no ground points) and trees (70% of ground points
lost under the crown). Truth = the kerb faces; lots = blocks less a 3.5 m verge. Class 2 only.
"""
import sys, json
import numpy as np
import laspy
from scipy import ndimage
from shapely.geometry import LineString, Polygon, box as sbox, mapping
from shapely.ops import unary_union
from shapely import contains_xy


def main():
    a = sys.argv[1:]
    opt = lambda k, d: float(a[a.index(k) + 1]) if k in a else d
    density, noise, seed = opt("--density", 6.0), opt("--noise", 0.03), int(opt("--seed", 1))
    rng = np.random.default_rng(seed)
    X0, Y0, S, W = 553000.0, 6880000.0, 300.0, 8.0
    area = sbox(X0, Y0, X0 + S, Y0 + S)
    xs = [X0 + 20, X0 + 120, X0 + 210, X0 + 290]; ys = [Y0 + 30, Y0 + 150, Y0 + 270]
    cl = [LineString([(x, Y0 - 50), (x + rng.uniform(-15, 15), Y0 + S + 50)]) for x in xs]
    cl += [LineString([(X0 - 50, y), (X0 + S + 50, y + rng.uniform(-10, 10))]) for y in ys]
    blocks = area.difference(unary_union(cl).buffer(W / 2, cap_style=2))
    blocks = [b.buffer(-6).buffer(6) for b in getattr(blocks, "geoms", [blocks]) if b.area > 50]
    road = area.difference(unary_union(blocks))
    c = 0.1; n = int(S / c)
    gx, gy = np.meshgrid(X0 + (np.arange(n) + 0.5) * c, Y0 + (np.arange(n) + 0.5) * c)
    inroad = contains_xy(road, gx, gy)
    d = ndimage.distance_transform_edt(inroad) * c
    lay = np.zeros_like(inroad)
    lays = []
    for b in blocks:
        ring = b.exterior
        for t in rng.uniform(0, ring.length, int(ring.length / 25)):
            seg = LineString([ring.interpolate(t).coords[0], ring.interpolate(min(t + 4, ring.length)).coords[0]])
            lays.append(seg.buffer(1.0))
    laym = contains_xy(unary_union(lays), gx, gy) & inroad & (d < 1.0)
    npts = int(S * S * density)
    x = rng.uniform(X0, X0 + S, npts); y = rng.uniform(Y0, Y0 + S, npts)
    i = ((y - Y0) / c).astype(int).clip(0, n - 1); j = ((x - X0) / c).astype(int).clip(0, n - 1)
    z = 12 + 0.02 * (x - X0) - 0.01 * (y - Y0) + rng.normal(0, noise, npts)
    r = inroad[i, j]
    z[r] += -0.15 + 0.10 * np.minimum(d[i, j][r], W / 2) / (W / 2)
    z[laym[i, j]] += 0.12 * (1 - d[i, j][laym[i, j]])
    keep = np.ones(npts, bool)
    houses = []
    for b in blocks:
        inner = b.buffer(-8)
        for k in range(12):
            if inner.is_empty:
                break
            px, py = rng.uniform(*inner.bounds[0::2]), rng.uniform(*inner.bounds[1::2])
            if contains_xy(inner, px, py):
                houses.append(sbox(px - 6, py - 5, px + 6, py + 5))
    if houses:
        keep &= ~contains_xy(unary_union(houses), x, y)
    for k in range(60):
        tx, ty = rng.uniform(X0, X0 + S, 2)
        under = (x - tx) ** 2 + (y - ty) ** 2 < 9
        keep &= ~(under & (rng.random(npts) < 0.7))
    x, y, z = x[keep], y[keep], z[keep]
    hdr = laspy.LasHeader(point_format=1, version="1.2"); hdr.scales = [0.001] * 3; hdr.offsets = [X0, Y0, 0]
    las = laspy.LasData(hdr); las.x, las.y, las.z = x, y, z; las.classification = np.full(len(x), 2, np.uint8)
    las.write(a[0])
    truth = road.boundary.intersection(area.buffer(-0.01))
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(g), "properties": {}}
               for g in getattr(truth, "geoms", [truth])]}, open(a[1], "w"))
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(b.buffer(-3.5)), "properties": {}}
               for b in blocks]}, open(a[2], "w"))
    print(f"{len(x)} points, {truth.length:.0f} m of kerb -> {a[0]}", file=sys.stderr)


if __name__ == "__main__":
    main()
