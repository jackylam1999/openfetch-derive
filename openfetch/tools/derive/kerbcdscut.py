#!/usr/bin/env python3
"""Cuts for cul-de-sac kerbs (kerbcds.py, scenario 9 round 11, 21 Nov 2026): a drawn line keeps only the stretches the road is seen
beside. Two checks, each cutting only the flagged stretch (cut, don't drop; pieces under kerbcds.MIN_LEN m go):
  paving (H10)  NSW aerial photo colour of the 1-4 m road-side band against the stem's own road colour, learnt 8-35 m from the
                junction (the tip stretch of a centreline can itself run into bush). A stretch of PAVE_RUN m or more where under
                PAVE_MATCH of the band matches, with canopy (green or dark) under PAVE_CAN, is not beside paving: cut. Under canopy
                nothing is cut (the photo cannot see the road there).
  rise   (H12a', CDS_OFF=rise; failed round 13) walking out from the stem, the first LiDAR kerb rise (RISE, islands skipped, holes neither road
                nor edge, as kerbstate S12 H9); a stretch of OFF_RUN m or more lying over OFF_MAX m from it is cut. No rise, no cut.
  ends   (H12b, CDS_ENDS=1; failed gate 3 round 13) a flagged stretch is cut only where it reaches an open end of the line, never mid-line or across a closure (KN24:
                a cut with no real end reads as a hook; pack 4 r04/r10).
  offset  (H4, default CDS_OFF=intensity) LiDAR ground intensity (KN11 igrids, 0.5 m, 255 = no ground): walk from the stem out through each sample; road =
                intensity within ROAD_MAD MADs of the stem's own intensity; the edge is the first 1 m that is not road. A stretch of
                OFF_RUN m or more lying more than OFF_MAX m from that edge is cut. Only where igrids exist.

    python3 kerbcdscut.py --selftest
"""
import os, json, io, urllib.request, itertools
import numpy as np
from shapely.geometry import LineString, Point

IMG = ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={},{},{},{}&bboxSR=7856"
       "&imageSR=7856&size={},{}&format=jpg&f=image")
SHIFT = (0.5, 0.6)       # m (east, north) the photo sits off the cadastre (kerbphoto.SHIFT)
PX_M = 4                 # photo pixels per metre
STEP = 2.0               # m between checked samples
PAVE_K, PAVE_MAD = 3.0, 10.0
PAVE_MATCH, PAVE_CAN, PAVE_RUN = 0.3, 0.3, 12.0
ROAD_MAD, OFF_MAX, OFF_RUN = 2.5, 3.0, 6.0
OFF_MODE = os.environ.get("CDS_OFF", "intensity")      # rise: LiDAR kerb rise walk (H12a'); intensity: the round-11 walk (holes = road)
RISE = tuple(float(v) for v in os.environ.get("CDS_RISE", "0.10,0.35").split(","))      # m: the kerb rise walking out (kerbstate S12 H9: 6-9 cm joints inside the carriageway stopped the walk)
ENDS_ONLY = os.environ.get("CDS_ENDS", "0") == "1"  # H12b: trim inward from a line's open ends only, never mid-line or a closure


class Photo:
    """NSW aerial photo of one box in MGA56 (cached as .npy), sampled at points."""

    def __init__(self, cache, fetch=None):
        self.cache, self.fetch = cache, fetch or self._get

    def _get(self, b, n):
        u = IMG.format(b[0] - SHIFT[0], b[1] - SHIFT[1], b[2] - SHIFT[0], b[3] - SHIFT[1], n, n)
        from PIL import Image
        req = urllib.request.Request(u, headers={"User-Agent": "openfetch-derive"})
        return np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("RGB"), float)

    def box(self, b):
        n = int((b[2] - b[0]) * PX_M); fn = os.path.join(self.cache, "%d_%d_%d.npy" % (b[0], b[1], n)) if self.cache else None
        if fn and os.path.exists(fn):
            im = np.load(fn)
        else:
            im = self.fetch(b, n)
            if fn:
                os.makedirs(self.cache, exist_ok=True); np.save(fn, im.astype(np.uint8))
        return lambda xy: _at(im, b, xy)


def _at(im, b, xy):
    n = im.shape[0]; s = (b[2] - b[0]) / n
    c = ((xy[:, 0] - b[0]) / s).astype(int); r = ((b[3] - xy[:, 1]) / s).astype(int)
    ok = (c >= 0) & (c < n) & (r >= 0) & (r < n); out = np.full((len(xy), 3), np.nan); out[ok] = im[r[ok], c[ok]]
    return out


def canopy(p):
    return ((p[:, 1] > p[:, 0] + 6) & (p[:, 1] > p[:, 2] + 6)) | (p.sum(1) < 150)


def stem_stretch(stem, tip, a=8.0, b=35.0):
    """Points along the stem a..b m from its junction end (the tip stretch may itself run past the paving)."""
    e = stem.project(tip); j0, js = (0.0, 1) if e > stem.length / 2 else (stem.length, -1)
    hi = max(a + 1, min(b, stem.length - 15))
    return [np.array(stem.interpolate(j0 + js * t).coords[0]) for t in np.arange(a, hi, 0.5)]


def samples(L):
    """(distance, point, unit normal) every STEP m along L; the normal's side is chosen in toward()."""
    out = []
    for t in np.arange(STEP / 2, L.length, STEP):
        q = np.array(L.interpolate(t).coords[0]); g = np.array(L.interpolate(min(L.length, t + 1)).coords[0]) - np.array(L.interpolate(max(0, t - 1)).coords[0])
        n = np.array([-g[1], g[0]]) / max(np.linalg.norm(g), 1e-9); out.append((t, q, n))
    return out


def toward(stem, q, n):
    c = np.array(stem.interpolate(stem.project(Point(q))).coords[0])
    return (n if n @ (c - q) >= 0 else -n), float(np.linalg.norm(c - q)), c


def paving_flags(L, stem, tip, photo):
    """True at samples of L not beside paving (H10), False elsewhere and under canopy; None when no road colour can be learnt."""
    pts = stem_stretch(stem, tip); rng = np.random.default_rng(0)
    if not pts:
        return None
    ref = np.vstack([p + rng.uniform(-1.2, 1.2, (12, 2)) for p in pts]); u = L.union(stem).bounds
    x0, y0 = int(np.floor(u[0] - 10)), int(np.floor(u[1] - 10)); side = int(np.ceil(max(u[2] - x0, u[3] - y0) + 10))
    b = (x0, y0, x0 + side, y0 + side)
    at = photo.box(b); rp = at(ref); rp = rp[np.isfinite(rp).all(1)]; rp = rp[~canopy(rp)]
    if len(rp) < 50:
        return None
    med = np.median(rp, 0); mad = np.maximum(1.4826 * np.median(np.abs(rp - med), 0), PAVE_MAD); out = []
    for t, q, n in samples(L):
        n, _, _ = toward(stem, q, n)
        band = np.array([q + n * d + np.array([-n[1], n[0]]) * w for d in np.arange(1, 4.01, 0.5) for w in (-0.8, 0, 0.8)])
        p = at(band); p = p[np.isfinite(p).all(1)]
        if not len(p):
            out.append(False); continue
        cn = canopy(p); mt = (np.abs(p[~cn] - med) <= PAVE_K * mad).all(1)
        out.append(bool(cn.mean() < PAVE_CAN and len(mt) and mt.mean() < PAVE_MATCH))
    return np.array(out)


def offset_flags(L, stem, tip, inten, cal=None):
    """True at samples of L lying more than OFF_MAX m from the intensity road edge walked out from the stem (H4, as canopy h4lib:
    road = within ROAD_MAD MADs of the 1 km cell's own centreline intensity, cal; holes count as road; the edge is the first 1 m
    whose 1 m mean is under half road, from 1.5 m out); None without intensity."""
    cal = cal or (lambda xy: _cal_of(inten(np.array(stem_stretch(stem, tip, 2.0, 60.0)))))
    if cal(np.array(stem.coords[:1])) is None:
        return None
    out = []
    for t, q, n in samples(L):
        n, dq, c = toward(stem, q, n); ms = cal(c[None, :])
        if dq < 1.5 or ms is None:
            out.append(False); continue
        m, s = ms; u = (q - c) / dq; tt = np.arange(0, dq + 6, 0.25); i = inten(c + np.outer(tt, u))
        rc = np.where(np.isfinite(i) & (i < 255), (np.abs(i - m) <= ROAD_MAD * s).astype(float), np.nan)
        with np.errstate(all="ignore"):
            sm = np.nan_to_num(np.array([np.nanmean(rc[max(0, k - 2):k + 3]) for k in range(len(rc))]), nan=1.0)
        e = next((tt[k] for k in range(6, len(sm) - 4) if np.all(sm[k:k + 4] < 0.5)), None)
        out.append(bool(e is not None and abs(dq - e) > OFF_MAX))
    return np.array(out)


def _cal_of(v):
    v = v[np.isfinite(v) & (v < 255)]
    if len(v) < 20:
        return None
    m = float(np.median(v)); return m, max(2.0, 1.4826 * float(np.median(np.abs(v - m))))


def cell_cal(roads, inten, fh_max=7):
    """(median, MAD) of ground intensity along every centreline (fh <= fh_max, on the ground) in a point's 1 km cell, 1 m apart."""
    from shapely.geometry import box
    from shapely.strtree import STRtree
    G = [r["g"] for r in roads if (r.get("fh") or 9) <= fh_max and r.get("on", 1) == 1]; tr = STRtree(G); mem = {}

    def at(xy):
        i, j = int(xy[0, 0] // 1000), int(xy[0, 1] // 1000)
        if (i, j) not in mem:
            fr = box(i * 1000, j * 1000, i * 1000 + 1000, j * 1000 + 1000); pts = []
            for k in tr.query(fr):
                g = G[int(k)].intersection(fr)
                for l in getattr(g, "geoms", [g]):
                    if l.length > 0:
                        pts += [l.interpolate(d).coords[0] for d in np.arange(0, l.length, 1.0)]
            mem[(i, j)] = _cal_of(inten(np.array(pts))) if pts else None
        return mem[(i, j)]
    return at


def rise_flags(L, stem, tip, ground):
    """True at samples of L lying more than OFF_MAX m from the first LiDAR kerb rise (RISE within about 1.5 m, from 2 m out; a rise
    that falls back 6 cm within 1.5-2.5 m is an island and skipped) walking out from the stem (H12a': holes are neither road nor
    edge; no rise within the walk, no flag)."""
    out = []
    for t, q, n in samples(L):
        n, dq, c = toward(stem, q, n)
        if dq < 1.5:
            out.append(False); continue
        u = (q - c) / dq; tt = np.arange(0, dq + 6, 0.25); H = ground.height(c[0] + u[0] * tt, c[1] + u[1] * tt); e = None
        for i in range(8, len(H) - 10):
            lo, hi = H[i - 4:i], H[i + 2:i + 6]
            if np.isfinite(lo).sum() >= 2 and np.isfinite(hi).sum() >= 2 and RISE[0] <= np.nanmedian(hi) - np.nanmedian(lo) <= RISE[1]:
                back = H[i + 6:i + 10]
                if np.isfinite(back).sum() >= 2 and np.nanmedian(back) - np.nanmedian(hi) <= -0.06:
                    continue
                e = tt[i] + 0.25; break
        out.append(bool(e is not None and abs(dq - e) > OFF_MAX))
    return np.array(out)


def cut(L, flags, run, min_len):
    """L without its flagged stretches of `run` m or more (ENDS_ONLY: only those reaching an end of L); pieces under min_len m
    dropped."""
    if flags is None or not flags.any():
        return [L]
    S = samples(L); bad = np.zeros(len(S), bool); k = 0
    for v, g in itertools.groupby(flags):
        g = len(list(g))
        if v and g * STEP >= run and (not ENDS_ONLY or k == 0 or k + g == len(flags)):
            bad[k:k + g] = True
        k += g
    if not bad.any():
        return [L]
    out = []
    for v, g in itertools.groupby(enumerate(bad), key=lambda z: z[1]):
        g = list(g)
        if v:
            continue
        a = max(0.0, S[g[0][0]][0] - STEP / 2) if g[0][0] > 0 else 0.0
        b = min(L.length, S[g[-1][0]][0] + STEP / 2) if g[-1][0] < len(S) - 1 else L.length
        if b - a >= min_len:
            out.append(LineString([L.interpolate(x).coords[0] for x in np.arange(a, b, 0.5)] + [L.interpolate(b).coords[0]]))
    return out


def apply(pieces, stem, tip, photo, inten, min_len, cal=None, ground=None):
    """Both cuts in turn on every piece (as coordinate lists, kerbcds.one's output); returns pieces and cut metres per check."""
    got, cm = [], {"paving": 0.0, "offset": 0.0}
    for q in pieces:
        Ls = [LineString(q)]
        for name, fn, run in (("paving", lambda L: paving_flags(L, stem, tip, photo) if photo else None, PAVE_RUN),
                              ("offset", lambda L: (rise_flags(L, stem, tip, ground) if ground is not None else None) if OFF_MODE == "rise"
                               else (offset_flags(L, stem, tip, inten, cal) if inten else None), OFF_RUN)):
            nxt = []
            for L in Ls:
                ps = cut(L, fn(L), run, min_len); cm[name] += L.length - sum(p.length for p in ps); nxt += ps
            Ls = nxt
        got += [list(L.coords) for L in Ls]
    return got, {k: round(v, 1) for k, v in cm.items()}


def igrids(d):
    """Sampler over KN11 intensity grids (<easting km>_<northing km>.npz, key i, 0.5 m, rows from the south)."""
    mem = {}

    def at(xy):
        xy = np.asarray(xy, float); out = np.full(len(xy), np.nan)
        I, J = np.floor(xy[:, 0] / 1000).astype(int), np.floor(xy[:, 1] / 1000).astype(int)
        for i, j in set(zip(I.tolist(), J.tolist())):
            if (i, j) not in mem:
                fn = os.path.join(d, f"{i}_{j}.npz"); mem[(i, j)] = np.load(fn)["i"] if os.path.exists(fn) else None
            g = mem[(i, j)]
            if g is None:
                continue
            k = (I == i) & (J == j)
            c = ((xy[k, 0] - i * 1000) / 0.5).astype(int).clip(0, 1999); r = ((xy[k, 1] - j * 1000) / 0.5).astype(int).clip(0, 1999)
            out[k] = g[r, c]
        return out
    return at


def selftest():
    stem = LineString([(0, -60), (0, 0)]); tip = Point(0, 0)
    L = LineString([(-7, -60), (-7, 10)])                                   # kerb 7 m west of the stem, 70 m long

    def photo_fetch(b, n):                                                  # asphalt (90) up to y = -15, grass (green) past it
        s = (b[2] - b[0]) / n; ys = b[3] - (np.arange(n) + 0.5) * s
        im = np.zeros((n, n, 3)); im[:] = (90, 92, 95); im[ys > -15] = (150, 140, 120); return im
    ph = Photo(None, photo_fetch)
    f = paving_flags(L, stem, tip, ph)
    assert f is not None and f[:20].sum() == 0 and f[-8:].all(), f
    ps = cut(L, f, PAVE_RUN, 20.0)
    assert len(ps) == 1 and abs(ps[0].bounds[3] - (-15)) < 3, ps[0].bounds
    inten = lambda xy: np.where(np.abs(np.asarray(xy)[:, 0]) <= 3.0, 40.0, 120.0)   # road 3 m each side of the stem
    o = offset_flags(L, stem, tip, inten)
    assert o is not None and o.all(), o                                     # 7 m out, edge at 3 m: 4 m behind, flagged
    near = LineString([(-3.5, -60), (-3.5, 10)])
    assert not offset_flags(near, stem, tip, inten).any()
    got, cm = apply([list(L.coords)], stem, tip, None, None, 20.0)
    assert got == [list(L.coords)] and cm == {"paving": 0.0, "offset": 0.0}
    class Gr:                                                               # 12 cm kerb rise 3 m either side of the stem
        def height(self, X, Y):
            return np.where(np.abs(np.asarray(X)) >= 3.0, 0.12, 0.0) + 0 * np.asarray(Y)
    assert rise_flags(L, stem, tip, Gr()).all() and not rise_flags(near, stem, tip, Gr()).any()
    class Flat:                                                             # no rise anywhere (holes, flat ground): never flagged
        def height(self, X, Y):
            return np.full(np.shape(X), np.nan)
    assert not rise_flags(L, stem, tip, Flat()).any()
    mid = np.zeros(35, bool); mid[10:20] = True                             # a flagged stretch mid-line stays (H12b)
    assert cut(L, mid, 6.0, 20.0) == [L] if ENDS_ONLY else True
    end = np.zeros(35, bool); end[25:] = True
    assert abs(cut(L, end, 6.0, 20.0)[0].length - 50) < 2.5
    print("kerbcdscut selftest pass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
