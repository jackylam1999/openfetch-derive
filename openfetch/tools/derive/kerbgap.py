"""Gap kerbs (Jacky 15 Nov 2026: "bring them back to fill the gap"; kerb bar 14 Nov: a little off is fine, nothing odd).

Version k's closed block loops, judged ONE LOOP AT A TIME: a loop is kept whole or left out whole, never cut, so no open end
can appear. A loop is left out (blank, not a guess) when any of these hold:
  open      it is not a closed ring after fusing
  main      any part of it lies nearer a main road (functionhierarchy 1-4) than a local street, or within that road's carriageway
  cross     it crosses or touches a street centreline that is on the ground (bridges and tunnels left out)
  lot       a stretch of it runs more than LOT_IN m inside a property lot (roofs, yards)
  unseen run  an unseen stretch over RUN_MAX m (v2)
  unseen    less than SEEN_MIN of it lies within SEEN_D m of a raw traced kerb (unseen stretches sat 6 m out on verges in k)
  official  any part of it lies within OFF_D m of an official council kerb line (--official file), official always wins
  small     its ring is shorter than MIN_LEN m

    python3 kerbgap.py traced.json lots_dir roads_dir out.json --fuse-with raw.json [--box x0 y0 x1 y1 | --traced-only-area]
        [--official official.json(lon/lat GDA2020)] [--why why.json]
"""
import json
import sys

import numpy as np
import shapely
import shapely.prepared
from shapely.geometry import LineString, Polygon, box
from shapely.strtree import STRtree
from pyproj import Transformer

import kerbaudit as ka
import kerbg
import kerbnet as kn

MAIN_FH = (1, 2, 3, 4)
LOT_IN, LOT_RUN = 2.0, 3.0      # m: a stretch over LOT_RUN m long more than LOT_IN m inside one lot
SEEN_D, SEEN_MIN = 1.5, 0.7     # m, share
RUN_MAX = 12                    # m (samples are 1 m apart), longest unseen stretch on a ring
MAIN_SEEN = 0.9                 # share of the main-road side seen (--main-seen)
OFF_D = 6.0                     # m
MIN_LEN = 12.0                  # m


def samples(g, step=1.0):
    n = max(2, int(g.length // step) + 1)
    return shapely.points([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, n)])


def judge(o, ctx):
    g = LineString(o)
    if np.hypot(*(o[0] - o[-1])) > 0.5:
        return "open"
    if g.length < MIN_LEN:
        return "small"
    P = samples(g)
    s_g, s_fh, s_t = ctx["streets"]
    r_g, r_t = ctx["raw"]
    seen = np.zeros(len(P), bool)
    for k in r_t.query(g.buffer(SEEN_D)):
        seen |= shapely.distance(P, r_g[int(k)]) < SEEN_D
    near = s_t.nearest(P)
    on_main = np.array([s_fh[int(k)] in MAIN_FH for k in near])
    for k in s_t.query(g.buffer(30)):
        if s_fh[int(k)] in MAIN_FH:
            on_main |= shapely.distance(P, s_g[int(k)]) < kn.SCOPE_W.get(s_fh[int(k)], 6.0)
    if on_main.any():
        # --main-seen: a block on a main road stays only when its main-road side was seen almost all along (LiDAR kerb step)
        if not ctx["main_seen"] or seen[on_main].mean() < MAIN_SEEN:
            return "main"
    for k in s_t.query(g):
        if g.intersects(s_g[int(k)]):
            return "cross"
    lots, l_t = ctx["lots"]
    for k in l_t.query(g):
        inner = lots[int(k)].buffer(-LOT_IN)
        if not inner.is_empty and g.intersection(inner).length > LOT_RUN:
            return "lot"
    if seen.mean() < SEEN_MIN:
        return "unseen"
    # v2 (15 Nov 2026 review: a guessed corner across a roof, F13; a wobble through angle parking, R22): no unseen stretch
    # longer than RUN_MAX m anywhere on the ring, so a loop is only ever a guess between kerbs it saw, never round a corner
    s2 = np.concatenate([seen, seen]); run = best = 0
    for v in s2:
        run = 0 if v else run + 1; best = max(best, run)
    if min(best, len(seen)) > RUN_MAX:
        return "unseen run"
    if ctx["off"] is not None:
        o_g, o_t = ctx["off"]
        if len(o_t.query(g, predicate="dwithin", distance=OFF_D)):
            return "official"
    return None


def read_lines(fn, to):
    out = []
    for f in json.load(open(fn))["features"]:
        geom = f.get("geometry") or {}
        cs = geom.get("coordinates") or []
        parts = cs if geom.get("type") == "MultiLineString" else [cs] if geom.get("type") == "LineString" else []
        out += [LineString([to(*c[:2]) for c in p]) for p in parts if len(p) > 1]
    return out


def main(a):
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    to = Transformer.from_crs(7844, 7856, always_xy=True).transform
    traced = ka.read_kerbs(a[0])
    lots = [g for g in kn.kr.load_faces(a[1]) if g.geom_type == "Polygon"]
    roads = ka.load_roads(a[2])
    sys.argv = [sys.argv[0]] + a[:4]
    import glob, os
    from shapely.geometry import shape
    seen = set()
    for fn in sorted(glob.glob(os.path.join(a[2], "*.json"))):
        for f in json.load(open(fn)).get("features", []):
            pr = f.get("properties") or {}
            if pr.get("roadontype") in (2, 3) and f.get("geometry") and pr.get("OBJECTID") not in seen:
                seen.add(pr.get("OBJECTID")); g = shape(f["geometry"])
                parts = [q for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
                kn.BRIDGES.extend(parts)
                if pr.get("functionhierarchy") not in ka.SKIP_FH:
                    kn.OVER_STREETS.extend(parts)
                if pr.get("roadontype") == 2 and pr.get("functionhierarchy") in (5, 6, 7):
                    kn.LOCAL_BRIDGES.extend(parts)
                if pr.get("roadontype") == 3:
                    kn.TUNNELS.extend(parts)
    if "--box" in a:
        i = a.index("--box"); area = box(*map(float, a[i + 1:i + 5]))
    else:
        area = ka.traced_area(ka.Kerbs(traced))
    st = {}
    traced = kn.untangle(traced, st)
    ground = kn.on_ground(roads, kn.BRIDGES); level = kn.on_ground(roads, kn.TUNNELS)
    R = [LineString(t) for t in ka.read_kerbs(a[a.index("--fuse-with") + 1]) if len(t) > 1]
    R = [g for g in R if area.buffer(300).intersects(g)]
    kn.FUSE_T, kn.FUSE, kn.FUSE_K = (R, STRtree(R)), kn.SKEL_FUSE, kn.SKEL_K
    kn.CLOSE_EDGE = True
    import os, pickle
    cache = a[a.index("--loops-cache") + 1] if "--loops-cache" in a else None
    if cache and os.path.exists(cache):
        out = pickle.load(open(cache, "rb"))
    else:
        out = kn.build(traced, lots, ground, area, st, keep_traced=False)
        kerbg.OVER[:] = kn.BRIDGES; kerbg.TUNNELS_G[:] = kn.TUNNELS
        out = kerbg.roundabouts(out, level, lots, st)
        if cache:
            pickle.dump(out, open(cache, "wb"))
    sg = [(g, fh) for g, fh in ground if fh not in ka.SKIP_FH]
    ctx = {"streets": ([g for g, _ in sg], [fh for _, fh in sg], STRtree([g for g, _ in sg])),
           "lots": (lots, STRtree(lots)), "raw": (R, STRtree(R)), "off": None, "main_seen": "--main-seen" in a}
    if "--official" in a:
        O = read_lines(a[a.index("--official") + 1], to)
        ctx["off"] = (O, STRtree(O))
    keep, why, km = [], [], {}
    if "--core" in a:
        i = a.index("--core"); core = box(*map(float, a[i + 1:i + 5]))
        out = [o for o in out if core.contains(LineString(o).centroid)]
    else:
        pa = shapely.prepared.prep(area)
        out = [o for o in out if pa.intersects(LineString(o))]
    for o in out:
        w = judge(np.asarray(o), ctx)
        L = LineString(o).length / 1000
        km[w or "kept"] = round(km.get(w or "kept", 0) + L, 2)
        if w is None:
            keep.append(o)
        else:
            why.append((w, o))
    if "--why" in a:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"why": w}, "geometry": {"type": "LineString", "coordinates": [[round(v, 2) for v in p] for p in o]}}
            for w, o in why]}, open(a[a.index("--why") + 1], "w"))
    feats = [{"type": "Feature", "properties": {"kind": "block loop", "source": "OpenFetch"},
              "geometry": {"type": "LineString", "coordinates": [[round(v, 8) for v in back(x, y)] for x, y in o]}}
             for o in keep]
    json.dump({"type": "FeatureCollection", "features": feats}, open(a[3], "w"))
    print("RESULT", json.dumps({"loops": len(out), "kept": len(keep), "km": km}))


if __name__ == "__main__":
    main(sys.argv[1:])
