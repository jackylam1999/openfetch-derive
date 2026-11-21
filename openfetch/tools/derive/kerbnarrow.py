"""Narrow terrace streets (scenario 14, 21 Nov 2026, case P-0243). kerbgrid puts a ring side at the road-class half width from
the street centreline (fh 6: 4.5 m). On a terrace street the whole road reserve is only 9-10 m, so 4.5 m is the property line:
the drawn kerb runs along the house fronts, 2-4 m behind the real kerb, and under the terrace roofs that lean over the footpath on
the aerial (KN17: about 1 ring in 9 odd in suburbs 21-40). The intensity road gate could not see it (no footpath band).

Rule, for every ring side: the road reserve is the lot-free interval (NSW cadastre) that holds the street centreline, measured
from lot front to lot front, not from the centreline alone (generalised centrelines sit off-centre). Where the side lies within
FRONT m in front of the lot front, or up to INSIDE m inside it, there is no room for a footpath behind it. There the kerb is the
LiDAR ground step (gutter below footpath, at least STEP m) inside [lot front + 0.75, mid-reserve - 1.5 or lot front + 6]:
seen on SEEN of the 20 m windows, the side moves onto the median step; not seen, the side is cut (no width fallback: most such
sides are 5-7 m lanes with no kerb) and the ring becomes open pieces whose ends are the corners of the kept sides.

    python3 kerbnarrow.py rings.geojson(lon/lat closed lines) ground_dir lots_dir roads_dir out.geojson
    python3 kerbnarrow.py --selftest

ground_dir: <x>_<y>.npz per 1 km cell (GDA2020 / MGA56), either 'g' float32 heights at 0.5 m (x0, y0) or 'z' int16 cm at 0.25 m.
lots_dir / roads_dir: NSW cadastre and road centreline json per cell (as kerbgrid's inputs), coordinates in EPSG 7856.
"""
import glob, json, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, shape
from shapely.strtree import STRtree

FRONT, INSIDE = 1.0, 3.0     # m: the rule fires for a side from 1 m in front of the lot front to 3 m inside it
STEP = 0.06                  # m: smallest gutter drop that counts as a kerb
SEEN = 0.5                   # share of a side's 20 m windows that must show the step, or the side is cut
TURN = 35.0                  # degrees over 4 stations: a corner between sides
LANE_FH, SKIP_FH = 7, (8, 9, 10, 11, 12)
T = np.arange(-6.0, 12.01, 0.25)
T2 = np.arange(-6.0, 30.01, 0.25)


class Ground:
    def __init__(self, d):
        self.d, self.c = d, {}

    def _get(self, i, j):
        if (i, j) not in self.c:
            fn = os.path.join(self.d, f"{i}_{j}.npz")
            g = None
            if os.path.exists(fn):
                f = np.load(fn)
                if "g" in f.files:
                    g = (f["g"].astype(float), 0.5)
                elif "z" in f.files:
                    z = f["z"]
                    g = (np.where(z > -32768, z / 100.0, np.nan), 0.25)
            self.c[(i, j)] = g
        return self.c[(i, j)]

    def at(self, X, Y):
        X, Y = np.asarray(X, float), np.asarray(Y, float)
        out = np.full(X.shape, np.nan)
        ci, cj = np.floor(X / 1000).astype(int), np.floor(Y / 1000).astype(int)
        for key in set(zip(ci.ravel().tolist(), cj.ravel().tolist())):
            g = self._get(*key)
            if g is None:
                continue
            a, r = g
            n = a.shape[0]
            m = (ci == key[0]) & (cj == key[1])
            ii = ((X[m] - key[0] * 1000) / r).astype(int).clip(0, n - 1)
            jj = ((Y[m] - key[1] * 1000) / r).astype(int).clip(0, n - 1)
            out[m] = a[jj, ii]
        return out


def stations(ring, step=2.0):
    """Points every `step` m round a closed ring with outward normals (the ring is made counter-clockwise first)."""
    ring = np.asarray(ring, float)
    if not Polygon(ring).exterior.is_ccw:
        ring = ring[::-1]
    L = LineString(ring)
    d = np.linspace(0, L.length, max(4, int(L.length / step)), endpoint=False)
    pts = np.array([L.interpolate(x).coords[0] for x in d])
    a = np.array([L.interpolate((x + 1) % L.length).coords[0] for x in d])
    b = np.array([L.interpolate((x - 1) % L.length).coords[0] for x in d])
    t = a - b
    t /= np.linalg.norm(t, axis=1)[:, None]
    return pts, np.c_[t[:, 1], -t[:, 0]]


def split_sides(pts):
    """Side number per station, -1 on corners (a turn of more than TURN degrees over 4 stations)."""
    n = len(pts)
    h = np.arctan2(*(np.roll(pts, -2, 0) - pts).T[::-1])
    dh = np.degrees(np.angle(np.exp(1j * (np.roll(h, -1) - h))))
    c = np.abs(np.convolve(np.r_[dh, dh[:4]], np.ones(4), "valid")[:n])
    cut = c > TURN
    lab, s = np.zeros(n, int), 0
    for i in range(n):
        if cut[i] and (i == 0 or not cut[i - 1]):
            s += 1
        lab[i] = -1 if cut[i] else s
    if not cut.any():
        lab[:] = 0
    return lab


def centre_dist(pts, nrm, streets, reach=25.0):
    """Distance along each outward normal to the first street centreline (lanes and paths skipped), NaN if none."""
    g, fh = streets
    tree = STRtree(g)
    D = np.full(len(pts), np.nan)
    for k, (p, n) in enumerate(zip(pts, nrm)):
        ray = LineString([p + n * 0.5, p + n * reach])
        for i in tree.query(ray):
            if fh[int(i)] == LANE_FH:
                continue
            x = ray.intersection(g[int(i)])
            for q in getattr(x, "geoms", [x]):
                if q.geom_type == "Point":
                    d = float(np.hypot(*(np.array(q.coords[0]) - p)))
                    D[k] = d if np.isnan(D[k]) else min(D[k], d)
    return D


def reserve(lots, pts, nrm, D):
    """Near (A) and far (B) lot front along each outward normal: the lot-free interval holding the centreline."""
    tree = STRtree(lots)
    X = pts[:, 0, None] + nrm[:, 0, None] * T2[None]
    Y = pts[:, 1, None] + nrm[:, 1, None] * T2[None]
    q = shapely.points(X.ravel(), Y.ravel())
    inl = np.zeros(len(q), bool)
    a, _ = tree.query(q, predicate="intersects")
    inl[a] = True
    inl = inl.reshape(X.shape)
    A, B = np.full(len(pts), np.nan), np.full(len(pts), np.nan)
    for k in range(len(pts)):
        free = ~inl[k]
        i0 = int(np.argmin(abs(T2 - (D[k] if np.isfinite(D[k]) else 4.5))))
        if not free[i0]:
            c = np.where(free)[0]
            if not len(c):
                continue
            i0 = c[np.argmin(abs(c - i0))]
        i = i0
        while i > 0 and free[i - 1]:
            i -= 1
        j = i0
        while j < len(T2) - 1 and free[j + 1]:
            j += 1
        if i > 0:
            A[k] = T2[i]
        if j < len(T2) - 1:
            B[k] = T2[j] + 0.25
    return A, B


def zprof(ground, pts, nrm):
    """Ground height along each outward normal, median of three parallel lines 0.25 m apart (sparse ground points)."""
    zs = []
    for dx in (-0.25, 0.0, 0.25):
        X = pts[:, 0, None] + nrm[:, 0, None] * T[None] + nrm[:, 1, None] * dx
        Y = pts[:, 1, None] + nrm[:, 1, None] * T[None] - nrm[:, 0, None] * dx
        zs.append(ground.at(X, Y))
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return np.nanmedian(np.array(zs), axis=0)


def find_step(Z, lo, hi):
    """Strongest outward drop (footpath above gutter) of a window of profiles inside [lo, hi]: (position, drop) or (nan, drop)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = np.nanmedian(Z[:, (T >= lo - 1) & (T <= hi + 1)], axis=1)[:, None]
        P = np.nanmedian(Z - ref, axis=0)
        xs, ds = [], []
        for x in np.arange(lo, hi + 0.01, 0.25):
            a, b = P[(T >= x - 1.0) & (T < x)], P[(T >= x + 0.25) & (T < x + 1.25)]
            if np.sum(~np.isnan(a)) < 2 or np.sum(~np.isnan(b)) < 2:
                continue
            xs.append(x)
            ds.append(np.nanmedian(a) - np.nanmedian(b))
    if not ds or max(ds) < STEP:
        return (np.nan, max(ds) if ds else 0.0)
    xs, ds = np.array(xs), np.array(ds)
    top = ds >= ds.max() - 0.01                     # a clean step gives a short plateau of equal drops: take its middle
    return (float(xs[top].mean()) + 0.125, float(ds.max()))


def narrow(ring, ground, lots, streets):
    """(pieces, actions): the ring unchanged as one piece when no side is on a lot front; else moved sides and/or open pieces."""
    pts, nrm = stations(ring)
    sl = split_sides(pts)
    D = centre_dist(pts, nrm, streets)
    A, B = reserve(lots, pts, nrm, D)
    Z = zprof(ground, pts, nrm)
    shift, keep, acts = np.zeros(len(pts)), np.ones(len(pts), bool), []
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for s in sorted(set(sl) - {-1}):
            idx = np.where(sl == s)[0]
            if len(idx) < 8:
                continue
            a = np.nanmedian(A[idx])
            if not np.isfinite(a) or a < -FRONT or a > INSIDE:
                continue
            pos = []
            for w in range(0, max(1, len(idx) - 4), 5):
                ii = idx[w:w + 10]
                aa, bb = np.nanmedian(A[ii]), np.nanmedian(B[ii])
                if not (np.isfinite(aa) and np.isfinite(bb)) or aa < -FRONT:
                    pos.append(np.nan)
                    continue
                pos.append(find_step(Z[ii], aa + 0.75, min((aa + bb) / 2 - 1.5, aa + 6.0, 10.5))[0])
            pos = np.array(pos)
            seen = float(np.mean(np.isfinite(pos)))
            if seen >= SEEN:
                shift[idx] = float(np.nanmedian(pos))
                acts.append({"action": "moved", "len_m": len(idx) * 2, "by_m": round(float(np.nanmedian(pos)), 2), "seen": round(seen, 2)})
            else:
                keep[idx] = False
                acts.append({"action": "cut", "len_m": len(idx) * 2, "reserve_m": round(float(np.nanmedian(B[idx] - A[idx])), 1), "seen": round(seen, 2)})
    if not acts:
        return [np.asarray(ring, float)], acts
    sm = np.convolve(np.r_[shift[-3:], shift, shift[:3]], np.ones(7) / 7, "valid")
    sh = np.where(shift != 0, shift, sm)    # corners ramp between their two sides' shifts
    P = pts + nrm * sh[:, None]
    if keep.all():
        q = Polygon(P).buffer(0)
        if q.geom_type != "Polygon":
            q = max(q.geoms, key=lambda g: g.area)
        q = q.buffer(-3).buffer(3).simplify(0.3)
        return [np.array(q.exterior.coords)], acts
    m = len(P)
    start = int(np.argmin(keep))
    pieces, cur = [], []
    for i in [(start + k) % m for k in range(m)]:
        if keep[i]:
            cur.append(P[i])
        elif cur:
            pieces.append(np.array(cur))
            cur = []
    if cur:
        pieces.append(np.array(cur))
    return [np.array(LineString(p).simplify(0.3).coords) for p in pieces if len(p) >= 5], acts


def load_lots(d, cells):
    out, seen = [], set()
    for i, j in cells:
        fn = os.path.join(d, f"{i * 1000}_{j * 1000}.json")
        if not os.path.exists(fn):
            continue
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            k = pr.get("objectid", pr.get("OBJECTID"))
            if k in seen or not f.get("geometry"):
                continue
            seen.add(k)
            g = shape(f["geometry"]).buffer(0)
            out += [q for q in getattr(g, "geoms", [g]) if q.area > 5]
    return out


def load_streets(d, cells):
    g, fh, seen = [], [], set()
    for i, j in cells:
        fn = os.path.join(d, f"{i * 1000}_{j * 1000}.json")
        if not os.path.exists(fn):
            continue
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            k = pr.get("objectid", pr.get("OBJECTID"))
            if k in seen or not f.get("geometry") or pr.get("roadontype") in (2, 3) or pr.get("functionhierarchy") in SKIP_FH:
                continue
            seen.add(k)
            s = shape(f["geometry"])
            for q in getattr(s, "geoms", [s]):
                g.append(q)
                fh.append(pr.get("functionhierarchy"))
    return g, fh


def main(a):
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    rings, gd, ld, rd, out = a[:5]
    ground = Ground(gd)
    feats, cnt = [], {"rings": 0, "changed": 0, "moved_sides": 0, "cut_sides": 0, "cut_m": 0, "km_in": 0.0, "km_out": 0.0}
    for f in json.load(open(rings))["features"]:
        c = np.array(f["geometry"]["coordinates"], float)
        x, y = to(c[:, 0], c[:, 1])
        ring = np.c_[x, y]
        cells = {(int(px // 1000) + u, int(py // 1000) + v) for px, py in ring for u in (-1, 0, 1) for v in (-1, 0, 1)}
        pieces, acts = narrow(ring, ground, load_lots(ld, cells), load_streets(rd, cells))
        cnt["rings"] += 1
        cnt["changed"] += bool(acts)
        cnt["moved_sides"] += sum(x["action"] == "moved" for x in acts)
        cnt["cut_sides"] += sum(x["action"] == "cut" for x in acts)
        cnt["cut_m"] += sum(x["len_m"] for x in acts if x["action"] == "cut")
        cnt["km_in"] += LineString(ring).length / 1000
        for k, p in enumerate(pieces):
            cnt["km_out"] += LineString(p).length / 1000
            pr = dict(f["properties"], narrow=acts, piece=k) if acts else dict(f["properties"])
            lon, lat = back(p[:, 0], p[:, 1])
            feats.append({"type": "Feature", "properties": pr, "geometry": {"type": "LineString", "coordinates": [[round(u, 7), round(v, 7)] for u, v in zip(lon, lat)]}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    cnt["km_in"], cnt["km_out"] = round(cnt["km_in"], 2), round(cnt["km_out"], 2)
    print("RESULT", json.dumps(cnt))


class _FakeGround:
    """Synthetic street running east along y = 0 (centreline), block to the south (y < 0)."""
    def __init__(self, kerb_y=None, step=0.12):
        self.k, self.s = kerb_y, step

    def at(self, X, Y):
        Y = np.asarray(Y, float)
        z = 10.0 + 0.0 * Y
        if self.k is not None:
            z = np.where(Y < self.k, z + self.s, z)     # footpath (towards the lots) stands above the gutter
        return z


def selftest():
    # terrace street: lots from y = -4.5 down, centreline y = 0, kerb at y = -3.0; a 100 x 60 m block whose north side sits on the
    # lot front (the class half width of 4.5 m); the other three sides face wide streets (lots 10 m from the line)
    blk = lambda top: np.array([(0, -60), (100, -60), (100, top), (0, top), (0, -60)], float)
    lots = [Polygon([(4, -56), (96, -56), (96, -4.5), (4, -4.5)])]
    streets = ([LineString([(-50, 0), (150, 0)]), LineString([(-50, -66), (150, -66)]), LineString([(-6, -100), (-6, 50)]),
                LineString([(106, -100), (106, 50)])], [6, 6, 6, 6])
    far = [Polygon([(-50, 4.5), (150, 4.5), (150, 30), (-50, 30)]), Polygon([(-50, -110), (150, -110), (150, -72), (-50, -72)]),
           Polygon([(-50, -100), (-12, -100), (-12, 50), (-50, 50)]), Polygon([(112, -100), (150, -100), (150, 50), (112, 50)])]
    pieces, acts = narrow(blk(-4.5), _FakeGround(-3.0), lots + far, streets)
    assert len(pieces) == 1 and [a["action"] for a in acts] == ["moved"], acts            # north side on the lot front: moved
    assert 1.0 <= acts[0]["by_m"] <= 2.0, acts                                            # by about 1.5 m, onto the kerb
    top = LineString(pieces[0]).intersection(LineString([(50, -30), (50, 10)])).bounds[3]
    assert -3.6 <= top <= -2.4, top
    pieces, acts = narrow(blk(-4.5), _FakeGround(None), lots + far, streets)              # a lane: no kerb step anywhere
    assert [a["action"] for a in acts] == ["cut"] and len(pieces) == 1, acts               # north side cut, ring opened
    assert LineString(pieces[0]).length < LineString(blk(-4.5)).length - 80
    pieces, acts = narrow(blk(-3.0), _FakeGround(-3.0), lots + far, streets)              # already on the kerb, 1.5 m before the lots
    assert acts == [] and len(pieces) == 1, acts                                          # untouched
    wide = [Polygon([(4, -56), (96, -56), (96, -8.0), (4, -8.0)])]                    # normal street: kerb 3.5 m in front of lots
    pieces, acts = narrow(blk(-4.5), _FakeGround(-4.5), wide + far, streets)
    assert acts == [] and len(pieces) == 1, acts                                          # untouched
    print("kerbnarrow selftest pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main(sys.argv[1:])
