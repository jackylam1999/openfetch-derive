#!/usr/bin/env python3
"""Draw the kerb layer for whole areas with the scored model (kerbs-direction.md "4 Nov 09:40Z" item 2: ship by road type).
Same inputs and steps as a scored box in kerblearn.py (photo, lots, centreline, water, LiDAR ground grid; probability, lines at the
check-box threshold, street-offset pieces with the LiDAR step check), but on 1 km boxes with no council kerbs, then every piece is
tagged with the road type of the nearest official centreline (NSW functionhierarchy 1-3 main, 4-5 collector, 6 local, 7+ lane).
Run from openfetch/tools/derive with KERB_CFG set to the model's settings (as kerb-learn/pc/side-street-eval.json, minutes 0).

  python kerbapply.py boxes SUBURB                          (every 1 km MGA56 grid square the NSW suburb outline covers by more
                                                             than 5 ha; shared grid names, so suburbs that touch share boxes, JSON)
  python kerbapply.py fetch out SUBURB                      (photo, lots, roads, water for each box; skips boxes already there)
  python kerbapply.py dem out laz_dir                       (LiDAR ground grid per box from ELVIS .laz tiles, as lidar_kernel.py)
  python kerbapply.py draw out model.pt thresh SUBURB       (lines per box, clipped to the box, tagged; SUBURB.geojson in WGS84)
SUBURB is the NSW suburb name (Administrative Boundaries theme, e.g. PARRAMATTA). The old "AREA lon lat km" form (a km x km block
around a point, 4-5 Nov ship run) still works: give lon lat km after the name.

Output AREA.geojson: LineStrings in EPSG:4326, properties road (main / collector / local / lane), source (model / street offset),
length_m. NSW Imagery and LiDAR (Spatial Services, CC BY 4.0), cadastre and transport themes (CC BY 4.0); output CC BY 4.0 (c) OpenFetch.
"""
import sys, os, json, glob
import numpy as np

import kerblearn as kl
import kerbphoto as kp
from shapely.geometry import shape, mapping, box as sbox
from shapely.strtree import STRtree

ROAD = ("main", "collector", "local", "lane")
EMPTY = {"type": "FeatureCollection", "features": []}
kp.COUNCILS["_none_"] = (None, (0.0, 0.0), "OBJECTID")  # no council kerbs: kp.fetch's kerb query returns nothing
_q = kp.query
kp.query = lambda u, *a, **k: [] if u is None else _q(u, *a, **k)


SUBURBS = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Administrative_Boundaries_Theme/FeatureServer/2/query"
MIN_HA = 5.0  # a grid square is drawn when the suburb covers more than this much of it


def suburb(name, cache="."):
    """Suburb outline in EPSG:7856 (cached as <cache>/<NAME>.suburb.json)."""
    import urllib.request, urllib.parse
    from shapely.ops import unary_union
    fn = os.path.join(cache, f"{name.upper()}.suburb.json")
    if not os.path.exists(fn):
        q = urllib.parse.urlencode({"where": f"suburbname='{name.upper()}'", "outSR": 7856, "f": "geojson"})
        req = urllib.request.Request(f"{SUBURBS}?{q}", headers={"User-Agent": "openfetch-kerbapply"})
        open(fn, "wb").write(urllib.request.urlopen(req, timeout=120).read())
    fs = json.load(open(fn)).get("features") or []
    if not fs:
        raise SystemExit(f"no NSW suburb called {name}")
    return unary_union([shape(f["geometry"]) for f in fs]).buffer(0)


def boxes(area, lon=None, lat=None, km=None, cache="."):
    """1 km boxes (name, x0, y0) on the MGA56 km grid: every square the suburb covers by > MIN_HA, or the old km x km block."""
    if lon is None:
        W = suburb(area, cache); x0, y0, x1, y1 = W.bounds; res = []
        for i in range(int(x0 // 1000), int(x1 // 1000) + 1):
            for j in range(int(y0 // 1000), int(y1 // 1000) + 1):
                if W.intersection(sbox(i * 1000, j * 1000, i * 1000 + 1000, j * 1000 + 1000)).area > MIN_HA * 1e4:
                    res.append((f"g{i}_{j}", i * 1000, j * 1000))
        return res
    from pyproj import Transformer
    x, y = Transformer.from_crs(4326, 7856, always_xy=True).transform(lon, lat)
    h = km * 500.0; x0, y0 = int(round((x - h) / 1000) * 1000), int(round((y - h) / 1000) * 1000); k = int(np.ceil(km))
    return [(f"g{(x0 + 1000 * i) // 1000}_{(y0 + 1000 * j) // 1000}", x0 + 1000 * i, y0 + 1000 * j) for i in range(k) for j in range(k)]


def _area(a):
    """SUBURB [lon lat km] from the command line -> boxes() arguments."""
    return (a[0], *map(float, a[1:4])) if len(a) >= 4 else (a[0],)


def fetch_one(out, nm, x, y):
    """kp.fetch without council kerbs: photo (0.1 m, moved by kp.SHIFT), lots; then roads and water as kerblearn.data."""
    if os.path.exists(f"{out}/{nm}_meta.json"):
        return
    kp.fetch(nm, "_none_", x, y, out)
    m = json.load(open(f"{out}/{nm}_meta.json")); b = (m["x0"], m["y0"], m["x0"] + m["w"], m["y0"] + m["w"])
    for k, u in kl.CONTEXT.items():
        fs = kp.query(u, b, fields="OBJECTID,functionhierarchy" if k == "roads" else "OBJECTID")
        json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{nm}_{k}.geojson", "w"))
    json.dump(EMPTY, open(f"{out}/{nm}_lga.geojson", "w"))
    json.dump(EMPTY, open(f"{out}/{nm}_kerbs.geojson", "w"))


def fetch(a):
    from concurrent.futures import ThreadPoolExecutor
    out = a[0]; os.makedirs(out, exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda b: fetch_one(out, *b), boxes(*_area(a[1:]), cache=out)))


def dem(a):
    """0.25 m ground grid per box (mean height of class 2 points, NaN where none) over the 1 km box, as lidar_kernel.py."""
    import laspy
    out, src = a[0], a[1]; G, W = 0.25, 1000.0; n = int(W / G)
    B = [(os.path.basename(p)[:-10], json.load(open(p))["box"]) for p in glob.glob(f"{out}/*_meta.json")]
    B = [(nm, b) for nm, b in B if not os.path.exists(f"{out}/{nm}_dem.npy")]
    H = []  # tile bounds once, then one box at a time (all boxes at once held 256 MB each in memory)
    for p in sorted(glob.glob(f"{src}/**/*.la[sz]", recursive=True)):
        with laspy.open(p) as r:
            H.append((p, r.header.mins[0], r.header.mins[1], r.header.maxs[0], r.header.maxs[1]))
    for nm, b in B:
        s, t = np.zeros(n * n), np.zeros(n * n)
        for p, x0, y0, x1, y1 in H:
            if not (b[0] < x1 and b[2] > x0 and b[1] < y1 and b[3] > y0):
                continue
            with laspy.open(p) as r:
                for ch in r.chunk_iterator(5_000_000):
                    g = ch.classification == 2; x, y, z = np.asarray(ch.x)[g], np.asarray(ch.y)[g], np.asarray(ch.z)[g]
                    c = ((x - b[0]) / G).astype(int); rr = n - 1 - ((y - b[1]) / G).astype(int)
                    k = (c >= 0) & (c < n) & (rr >= 0) & (rr < n)
                    i = rr[k] * n + c[k]; np.add.at(s, i, z[k]); np.add.at(t, i, 1)
        d = np.where(t > 0, s / np.maximum(t, 1), np.nan).reshape(n, n).astype(np.float32)
        np.save(f"{out}/{nm}_dem.npy", d); print(nm, f"{np.isfinite(d).mean():.0%} cells with ground", file=sys.stderr, flush=True)


def tag(out, nm, lines):
    """Road type per piece: the most common type of the nearest centreline over samples every 2 m."""
    R = [(shape(f["geometry"]), (f.get("properties") or {}).get("functionhierarchy")) for f in
         json.load(open(f"{out}/{nm}_roads.geojson"))["features"] if f.get("geometry")]
    R = [(g, h) for g, h in R if h is not None]
    if not R:
        return ["local"] * len(lines)
    T = STRtree([g for g, _ in R]); K = [0 if h <= 3 else 1 if h <= 5 else 2 if h == 6 else 3 for _, h in R]; res = []
    for l in lines:
        pts = [l.interpolate(t) for t in np.arange(0, l.length + 0.01, 2.0)] or [l.interpolate(0)]
        res.append(ROAD[np.bincount([K[i] for i in T.nearest(pts)], minlength=4).argmax()])
    return res


def draw(a):
    import torch
    from affine import Affine
    from pyproj import Transformer
    from shapely.ops import transform
    import kerbstreet
    out, mp, th, area = a[0], a[1], float(a[2]), a[3]
    net = kl.model(False); kl.load(net, mp); net = net.to(kl.DEV()).eval()
    to84 = Transformer.from_crs(7856, 4326, always_xy=True).transform
    feats = []; tot = {}
    for nm, x, y in boxes(*_area(a[3:]), cache=out):
        if not os.path.exists(f"{out}/{nm}_meta.json"):
            print(nm, "not fetched", file=sys.stderr); continue
        kl.BX[nm] = (x, y)  # kerbstep.grids places the LiDAR grid by the box corner
        m, tr, rgb, lot, lab, road = kl.labels(out, nm)
        mark = f"{out}/{nm}_drawn.json"; key = {"model": os.path.abspath(mp), "thresh": th, "lidar": os.path.exists(f"{out}/{nm}_dem.npy")}
        if not (os.path.exists(mark) and json.load(open(mark)) == key):  # a box two areas share is drawn once
            P = kl.prob(net, rgb, kl.inputs(out, nm, lot), None, kl.CFG["tta"])
            kp.vec(out, nm, P, tr, th); del P
            if key["lidar"]:
                kerbstreet.fill_file(f"{out}/{nm}_derived.geojson", out, nm)
            json.dump(key, open(mark, "w"))
        has = key["lidar"] or None
        clip = sbox(*m["box"]); L, S = [], []
        for f in json.load(open(f"{out}/{nm}_derived.geojson"))["features"]:
            g = shape(f["geometry"]).intersection(clip)
            for p in getattr(g, "geoms", [g]):
                if p.geom_type == "LineString" and p.length >= kp.MIN_LEN:
                    L.append(p); S.append("street offset" if (f.get("properties") or {}).get("street") else "model")
        for l, s, r in zip(L, S, tag(out, nm, L)):
            feats.append({"type": "Feature", "geometry": mapping(transform(to84, l)),
                          "properties": {"road": r, "source": s, "length_m": round(l.length, 1)}})
            tot[r] = tot.get(r, 0) + l.length
        print(nm, f"{sum(l.length for l in L) / 1000:.1f} km", "LiDAR" if has is not None else "NO LiDAR", file=sys.stderr, flush=True)
        torch.cuda.empty_cache()
    json.dump({"type": "FeatureCollection", "features": feats}, open(f"{out}/{area}.geojson", "w"))
    print("RESULT", area, json.dumps({k: round(v / 1000, 1) for k, v in tot.items()}), "km")


if __name__ == "__main__":
    {"boxes": lambda a: print(json.dumps(boxes(*_area(a)))), "fetch": fetch, "dem": dem, "draw": draw}[sys.argv[1]](sys.argv[2:])
