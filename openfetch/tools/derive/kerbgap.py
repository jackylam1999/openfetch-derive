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

v3-v5 (15 Nov 2026, George St CBD: most blocks blank because the LiDAR lost the kerb under awnings and buses; Jacky: "fill as
much gap as possible ... a few metres off is fine, as long as not odd lines like intersection lines or weird turns to the wrong
kerb"; his marks on the first loose try: three blocks merged across a street and a bump, all from guessed stretches that bend):
  --bridge      a STRAIGHT unseen stretch (within STRAIGHT_D of the chord, up to BRIDGE_MAX m) between two seen ends counts as seen
  --lane-mouth  an access lane (functionhierarchy 7) may cross the ring where the ring runs straight past its mouth
  --loose       SEEN_MIN 0.5, MAIN_SEEN 0.6; RUN_MAX stays 12 m for any stretch that bends (KG_RUN to try others: 25/40 brought
                Jacky's merges back)
  --split       a ring that fails is cut along every street it crosses (the street band at its measured half width) and each
                piece is judged again; a cut side must lie CUT_SEEN on a seen kerb
Published as version 2026-11-15-b: 1,219 km (2026-11-15: 1,022 km); reviewer 40 OK of 40 fresh places on the new lines.

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
BRIDGE_MAX, STRAIGHT_D = 60, 1.0  # v3 (--bridge): an unseen stretch up to BRIDGE_MAX m counts as seen when the ring runs straight
                                  # (within STRAIGHT_D m of the chord) between the two seen ends: awnings, buses and parked cars hide
                                  # the kerb step on CBD main roads (George St, 15 Nov 2026); a corner or a wobble is never straight
LANE_FH, LANE_SEEN, LANE_GAP = 7, 6, 8        # v3 (--lane-mouth): an access lane's mouth may cross the ring where the kerb was seen LANE_SEEN m
                                  # either side of the crossing (the kerb runs past the lane on a layback)


def bridged(P, seen):
    """seen, with every straight unseen stretch of up to BRIDGE_MAX samples between two seen samples marked seen."""
    n = len(seen)
    if seen.all() or not seen.any():
        return seen.copy()
    out = seen.copy(); xy = shapely.get_coordinates(P)
    start = int(np.argmax(seen))
    i = 0
    while i < n:
        k = (start + i) % n
        if seen[k]:
            i += 1; continue
        j = i
        while j < n and not seen[(start + j) % n]:
            j += 1
        L = j - i
        a, b = xy[(start + i - 1) % n], xy[(start + j) % n]
        idx = [(start + t) % n for t in range(i, j)]
        ab = b - a; d = np.hypot(*ab)
        if L <= BRIDGE_MAX and d > 0:
            w = xy[idx] - a; dev = np.abs(ab[0] * w[:, 1] - ab[1] * w[:, 0]) / d
            along = (xy[idx] - a) @ ab / d
            if dev.max() <= STRAIGHT_D and along.min() >= -STRAIGHT_D and along.max() <= d + STRAIGHT_D:
                out[idx] = True
        i = j
    return out


def samples(g, step=1.0):
    n = max(2, int(g.length // step) + 1)
    return shapely.points([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, n)])


def lane_mouth_ok(g, P, raw_seen, seen, lane):
    """An access lane crossing the ring at points only; at each crossing the ring runs straight (bridged) for LANE_SEEN m
    either side and the kerb step was seen within LANE_GAP m on both sides (a lane mouth on a layback, never a street)."""
    x = g.intersection(lane)
    pts = [q for q in getattr(x, "geoms", [x]) if q.geom_type == "Point"]
    if not pts or len(pts) != len(getattr(x, "geoms", [x])):
        return False
    xy = shapely.get_coordinates(P)
    for q in pts:
        d = shapely.distance(P, q)
        if not seen[d <= LANE_SEEN].all():
            return False
        k = int(np.argmin(d)); n = len(P)
        for step in (1, -1):
            if not any(raw_seen[(k + step * t) % n] for t in range(1, LANE_GAP + 1)):
                return False
    return True


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
    raw_seen = seen
    if ctx.get("bridge"):
        seen = bridged(P, seen)
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
            if ctx.get("lane_mouth") and s_fh[int(k)] == LANE_FH and lane_mouth_ok(g, P, raw_seen, seen, s_g[int(k)]):
                continue
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


HALF_W = {1: 9.0, 2: 8.0, 3: 7.0, 4: 6.5, 5: 5.5, 6: 4.5, 7: 3.0}   # m, centreline to kerb when no kerb was seen along it
CUT_SEEN = 0.5                   # share of each new cut side that must lie on a seen kerb (LiDAR step)


def half_width(c, ctx, fh):
    """Centreline to kerb in m, from the raw LiDAR kerb traces along this street (median on both sides), else HALF_W."""
    r_g, r_t = ctx["raw"]
    P = samples(c, 2.0); d = np.full(len(P), np.inf)
    for k in r_t.query(c.buffer(12)):
        d = np.minimum(d, shapely.distance(P, r_g[int(k)]))
    d = d[(d > 1.5) & (d < 12)]
    return float(np.median(d)) if len(d) >= 5 else HALF_W.get(fh, 5.0)


def split_cross(o, ctx):
    """v5 (--split, Jacky 15 Nov 2026 "keep adding coverage"): a loop that runs round two blocks and across the street between them
    is cut along every street it crosses (the street band, centreline +- its measured half width, taken out) and each block left
    is judged again on its own; a new cut side must lie CUT_SEEN on a seen kerb, so a cut is never a guess."""
    s_g, s_fh, s_t = ctx["streets"]; r_g, r_t = ctx["raw"]
    g = LineString(o); Pg = Polygon(o)
    if not Pg.is_valid:
        Pg = Pg.buffer(0)
    cut = []
    for k in s_t.query(g):
        if g.intersects(s_g[int(k)]):
            c = s_g[int(k)].intersection(Pg.buffer(20))
            if not c.is_empty:
                cut.append(c.buffer(half_width(s_g[int(k)], ctx, s_fh[int(k)]), cap_style=2))
    if not cut:
        return []
    band = shapely.union_all(cut)
    rest = Pg.difference(band).buffer(-4.0).buffer(4.0)
    out = []
    for q in getattr(rest, "geoms", [rest]):
        if q.geom_type != "Polygon" or q.area < 300:
            continue
        ring = np.asarray(q.exterior.coords)
        if judge(ring, ctx) is not None:
            continue
        side = LineString(ring).intersection(band.buffer(1.0))
        if side.length > 0:
            P = samples(side if side.geom_type == "LineString" else shapely.line_merge(side) if side.geom_type == "MultiLineString" else LineString(ring), 1.0)
            seen = np.zeros(len(P), bool)
            for k in r_t.query(side.buffer(1.5)):
                seen |= shapely.distance(P, r_g[int(k)]) < SEEN_D
            if seen.mean() < CUT_SEEN:
                continue
        out.append(ring)
    return out


def read_lines(fn, to):
    out = []
    for f in json.load(open(fn))["features"]:
        geom = f.get("geometry") or {}
        cs = geom.get("coordinates") or []
        parts = cs if geom.get("type") == "MultiLineString" else [cs] if geom.get("type") == "LineString" else []
        out += [LineString([to(*c[:2]) for c in p]) for p in parts if len(p) > 1]
    return out


LOOSE = {"SEEN_MIN": 0.5, "MAIN_SEEN": 0.6, "RUN_MAX": int(__import__("os").environ.get("KG_RUN", 12)), "BRIDGE_MAX": 150}
# v4 (--loose, Jacky 15 Nov 2026: "fill as much gap as possible ... a few metres off is fine, as long as not odd lines like
# intersection lines or weird turns to the wrong kerb"): looser seen shares and longer guessed stretches; the odd-line gates
# (cross, lot, open, small, official) stay as they are


def main(a):
    if "--loose" in a:
        globals().update(LOOSE)
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
           "lots": (lots, STRtree(lots)), "raw": (R, STRtree(R)), "off": None, "main_seen": "--main-seen" in a,
           "bridge": "--bridge" in a, "lane_mouth": "--lane-mouth" in a}
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
        if w is not None and w not in ("open", "small") and "--split" in a:
            parts = split_cross(np.asarray(o), ctx)
            if parts:
                keep += [list(map(tuple, p)) for p in parts]; km["split"] = round(km.get("split", 0) + sum(LineString(p).length for p in parts) / 1000, 2)
                continue
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
