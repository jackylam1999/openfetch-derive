"""Per lot-front sample: truth footpath width (CoM kerb/channel/carriageway), reserve width, centreline distance, street, trees."""
import json, sys, os, numpy as np, shapely
from shapely.geometry import shape, LineString, Point, box
from shapely.ops import unary_union, transform
from shapely.strtree import STRtree
from pyproj import Transformer
TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
STEP, RAY, CLOSE = 2.0, 45.0, 0.4
def load(p):
    return json.load(open(p))["features"]
def proj(g):
    return transform(TO, shape(g))
def blocks(lots):
    P = [proj(f["geometry"]).buffer(0) for f in lots if f["geometry"]]
    land = unary_union([p.buffer(CLOSE) for p in P]).buffer(-CLOSE)
    return land
def samples(land, frame):
    out = []
    for bi, comp in enumerate(getattr(land, "geoms", [land])):
        if comp.area < 300: continue
        ext = comp.exterior; n = max(8, int(ext.length / STEP))
        for v in np.linspace(0, ext.length, n, endpoint=False):
            p = np.array(ext.interpolate(v).coords[0])
            if not frame.contains(Point(p)): continue
            a = np.array(ext.interpolate((v - .5) % ext.length).coords[0]); b = np.array(ext.interpolate((v + .5) % ext.length).coords[0])
            t = b - a; t /= max(np.hypot(*t), 1e-9); nr = np.array([t[1], -t[0]])
            if comp.contains(Point(p + nr * .3)): nr = -nr
            out.append((bi, v, p, nr))
    return out
def hit(ray, geoms, tree, lo=0.0, far=False, hi=None):
    st = Point(ray.coords[0]); best, bi = np.nan, -1
    for g in tree.query(ray, predicate="intersects"):
        x = ray.intersection(geoms[g])
        for q in getattr(x, "geoms", [x]):
            for c in getattr(q, "coords", []):
                d = st.distance(Point(c))
                if d > lo and (hi is None or d < hi) and (np.isnan(best) or (d > best if far else d < best)): best, bi = d, g
    return best, bi
def main(box_dir, truth_paths, out):
    lots = load(os.path.join(box_dir, "lots.geojson")); land = blocks(lots)
    minx, miny, maxx, maxy = land.bounds; frame = box(minx + 60, miny + 60, maxx - 60, maxy - 60)
    roads = [f for f in load(os.path.join(box_dir, "roads.geojson")) if f["geometry"]]
    RL = [proj(f["geometry"]) for f in roads]; RT = STRtree(RL)
    TR = []
    if truth_paths:
        big = box(minx - 50, miny - 50, maxx + 50, maxy + 50)
        for tp in truth_paths:
            for f in json.load(open(tp))["features"]:
                g = f["geometry"]
                if not g: continue
                c = g["coordinates"]
                q = proj(g)
                if q.intersects(big): TR.append(q.buffer(0))
        tu = unary_union(TR); TRb = [g.exterior if g.geom_type == "Polygon" else g for g in getattr(tu, "geoms", [tu])]
        TRl = []
        for g in getattr(tu, "geoms", [tu]):
            TRl += [g.exterior] + list(g.interiors)
        TT = STRtree(TRl)
    LB = [b.exterior for b in getattr(land, "geoms", [land])] + [i for b in getattr(land, "geoms", [land]) for i in b.interiors]
    LT = STRtree(LB)
    trees = [proj(f["geometry"]) for f in load(os.path.join(box_dir, "trees.geojson")) if f["geometry"]]
    tr_xy = np.array([[t.x, t.y] for t in trees]) if trees else np.zeros((0, 2))
    S = samples(land, frame); rows = []
    for bi, v, p, nr in S:
        ray = LineString([p, p + nr * RAY])
        w, _ = hit(ray, LB, LT, lo=0.5)
        c, ri = hit(ray, RL, RT)
        d = np.nan
        if truth_paths:
            d, _ = hit(ray, TRl, TT)
            e = np.nan
            if not np.isnan(d) and not np.isnan(w): e, _ = hit(ray, TRl, TT, lo=d + 0.5, far=True, hi=w - 0.2)
        pr = roads[ri]["properties"] if ri >= 0 else {}
        rows.append({"b": bi, "v": round(v, 1), "x": round(p[0], 2), "y": round(p[1], 2), "nx": round(nr[0], 4), "ny": round(nr[1], 4),
                     "w": None if np.isnan(w) else round(w, 2), "c": None if np.isnan(c) else round(c, 2), "d": None if np.isnan(d) else round(d, 2), "e": None if (not truth_paths or np.isnan(e)) else round(e, 2),
                     "road": pr.get("ezi_road_name"), "cls": pr.get("class_code"), "rpfi": pr.get("pfi"), "div": pr.get("div_rd")})
    # trees: perpendicular offset from lot front, assigned to nearest sample within 10 m outside land
    if len(tr_xy) and rows:
        P = np.array([[r["x"], r["y"]] for r in rows]); N = np.array([[r["nx"], r["ny"]] for r in rows])
        for t in trees:
            if land.contains(t): continue
            dd = np.hypot(P[:, 0] - t.x, P[:, 1] - t.y); i = int(np.argmin(dd))
            if dd[i] > 10: continue
            off = (t.x - P[i, 0]) * N[i, 0] + (t.y - P[i, 1]) * N[i, 1]
            lat = abs((t.x - P[i, 0]) * N[i, 1] - (t.y - P[i, 1]) * N[i, 0])
            if off > 0.3 and lat < 1.5: rows[i].setdefault("t", []).append(round(off, 2))
    json.dump(rows, open(out, "w"))
    print(out, len(rows), sum(r["d"] is not None for r in rows), sum("t" in r for r in rows))
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[3:], sys.argv[2])
