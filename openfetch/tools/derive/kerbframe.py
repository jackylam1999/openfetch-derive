"""Measure which datum frame LiDAR intensity grids are really in (P-0244, 21 Nov 2026).
For every 2 km tile it fits the offset between the asphalt (road mask of the grids) and the state road centrelines: along each
centreline, the asphalt run that holds the centreline gives a centre; centre = -(normal . shift) is solved by least squares.
The centrelines MUST come from NSW_Transport_Theme_multiCRS (true GDA2020); the layer without multiCRS is GDA94 numbers labelled 7856
and sits 0.46 E / 1.44 N off (that is the slip this tool was written to find).
Result 21 Nov 2026 (43 tiles of the 40 NSW suburbs, true centrelines): the 28 GDA94-headed tiles median 0.06 E / 0.08 N, the 15
GDA2020 tiles 0.30 E / 0.00 N (each tile within +-0.5 m), so the GDA94 headers are wrong and nothing should be shifted. With the plain
centrelines every tile read about 0.5 E / 1.45 N: that is the plain layer's own slip. A tile that reads over 1 m is a frame to check.

    python3 kerbframe.py <igrid_dir> <roads_dir_of_json_files> [tile_ids_file]
"""
import sys, os, glob, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def fit(rows):
    R = np.array(rows); A = -R[:, :2]; c = R[:, 2]
    sol = np.linalg.lstsq(A, c, rcond=None)[0]
    for _ in range(3):
        res = c - A @ sol
        k = np.abs(res) < 2.5 * np.median(np.abs(res)) + 0.3
        sol = np.linalg.lstsq(A[k], c[k], rcond=None)[0]
    return sol


def selftest():
    rng = np.random.default_rng(1)
    th = rng.uniform(0, np.pi, 600)
    n = np.c_[np.cos(th), np.sin(th)]
    s = np.array([0.5, 1.4])
    rows = np.c_[n, -(n @ s) + rng.normal(0, 0.3, 600)]
    f = fit(rows)
    assert abs(f[0] - 0.5) < 0.1 and abs(f[1] - 1.4) < 0.1, f
    print("kerbframe selftest pass")
    return 0


def main(gdir, rdir, tiles):
    import kerblot as kl, kerbroad as krd, kerbnet as kn, kerbaudit as ka
    from shapely.geometry import shape
    roads, seen, over = [], set(), []
    for fn in sorted(glob.glob(rdir + "/*.json")):
        for f in json.load(open(fn))["features"]:
            pr = f.get("properties") or {}
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if pr.get("roadontype") in (2, 3):
                over += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
            oid = pr.get("OBJECTID", pr.get("objectid"))
            if oid in seen:
                continue
            seen.add(oid)
            for q in getattr(g, "geoms", [g]):
                if q.geom_type == "LineString" and q.length > 0:
                    fh = pr.get("functionhierarchy")
                    if fh == kl.LANE_FH and pr.get("roadnametype") not in kl.LANE_TYPES:
                        fh = kl.NARROW_ST
                    roads.append((q, fh))
    cal = [g for g, fh in kn.on_ground(roads, over) if fh not in ka.SKIP_FH and fh != kl.LANE_FH]
    R = krd.Road(gdir, cal)
    t = np.arange(-9, 9.01, 0.25)
    rows = {}
    for g in cal:
        for s in np.arange(5, g.length - 5, 6.0):
            x, y = g.interpolate(s).coords[0]
            tile = f"{int(x // 1000) // 2 * 2}{int(y // 1000) // 2 * 2}"
            a = np.array(g.interpolate(s - 2).coords[0]); b = np.array(g.interpolate(s + 2).coords[0])
            d = b - a; L = np.hypot(*d)
            if L < 1:
                continue
            d /= L; nrm = np.array([-d[1], d[0]])
            P = np.array([x, y])[None, :] + t[:, None] * nrm[None, :]
            m = R.at(P[:, 0], P[:, 1])
            if np.isnan(m).any():
                continue
            r = m > 0.5; z = len(t) // 2
            if not r[z]:
                continue
            lo = hi = z
            while lo > 0 and r[lo - 1]: lo -= 1
            while hi < len(t) - 1 and r[hi + 1]: hi += 1
            if lo == 0 or hi == len(t) - 1 or not 5 <= t[hi] - t[lo] <= 15:
                continue
            rows.setdefault(tile, []).append((nrm[0], nrm[1], (t[lo] + t[hi]) / 2))
    for tile, v in sorted(rows.items()):
        if len(v) >= 80 and (tiles is None or tile in tiles):
            s = fit(v); print(tile, "E %.2f N %.2f  n=%d" % (-s[0], -s[1], len(v)))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    main(a[0], a[1], set(open(a[2]).read().split()) if len(a) > 2 else None)
