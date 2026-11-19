"""Join the reviewed Vic lot-front rings of several runs into one version file (each ring once; the run boxes overlap a little;
a block ringed by two runs keeps the earlier run's ring, so list the ground-model runs first).
    python3 join_vic.py out.geojson.gz out_mga55.geojson prep_a run_a [prep_b run_b ...] [--areas "Richmond,Fitzroy,..."]
Each feature: road (main: Vicmap class freeway to sub-arterial within reach of the ring, collector: collector, else local),
source "model" (kerbs-check.py's value for drawn lines), length_m, areas (the localities of the streets the ring was measured
on, from kerblot's per-side measures). out_mga55 is the same file in EPSG 7855 metres for kerbreview.py and kerbaudit.py."""
import gzip, json, sys
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
import numpy as np, shapely
from shapely.geometry import LineString
from shapely.strtree import STRtree
from pyproj import Transformer
import kerbaudit as ka

TO = Transformer.from_crs(4326, 7855, always_xy=True).transform
REACH = {1: 14, 2: 11, 3: 11, 4: 8.5}     # m from a main-road centreline (join3.py, NSW 19 Nov 2026)


def road_of(g, RT, RG, RF):
    P = shapely.points(np.asarray([g.interpolate(t).coords[0] for t in np.linspace(0, g.length, max(2, int(g.length // 2)))]))
    fhs = {RF[int(k)] for k in RT.query(g.buffer(15)) if (shapely.distance(P, RG[int(k)]) < REACH.get(RF[int(k)], 9)).any()}
    return "main" if fhs & {1, 2, 3, 4} else "collector" if 5 in fhs else "local"


def main(a):
    only = None
    if "--areas" in a:   # keep only rings measured on streets of these localities (the owner's suburb list; run boxes reach past it)
        i = a.index("--areas"); only = {x.strip().title() for x in a[i + 1].split(",")}; a = a[:i] + a[i + 2:]
    out, out_m, runs = a[0], a[1], list(zip(a[2::2], a[3::2]))
    feats, mfeats, kept, kept_pg = [], [], [], []
    for prep, run in runs:
        roads = [(g, fh) for g, fh in ka.load_roads(f"{prep}/roads") if fh not in ka.SKIP_FH]
        RG, RF = [g for g, _ in roads], [fh for _, fh in roads]; RT = STRtree(RG)
        for f in json.load(open(f"{run}/rings.json"))["features"]:
            cs = [[round(v, 7) for v in c[:2]] for c in f["geometry"]["coordinates"]]
            g = LineString([TO(*c) for c in cs])
            loc = sorted({k.split("|", 1)[1].split(":")[0].title() for k in (f["properties"].get("d") or {}) if "|" in k})
            if only is not None and not (set(loc) & only):
                continue
            if any(h.distance(g) < 0.5 and abs(h.length - g.length) < 1 for h in kept):
                continue
            pg = shapely.Polygon(g.coords).buffer(0)
            if any(pg.intersection(q).area > 0.2 * min(pg.area, q.area) for q in kept_pg if q.intersects(pg)):
                continue   # the same block measured by an earlier run (e.g. Merri-bek ground model, then the aerial): the earlier run wins
            kept.append(g); kept_pg.append(pg)
            pr = {"road": road_of(g, RT, RG, RF), "source": "model", "length_m": round(g.length, 1), "areas": ", ".join(loc)}
            feats.append({"type": "Feature", "properties": pr, "geometry": {"type": "LineString", "coordinates": cs}})
            mfeats.append({"type": "Feature", "properties": dict(pr, id=f["properties"]["id"]),
                           "geometry": {"type": "LineString", "coordinates": [list(p) for p in g.coords]}})
    json.dump({"type": "FeatureCollection", "features": feats}, gzip.open(out, "wt"))
    json.dump({"type": "FeatureCollection", "features": mfeats}, open(out_m, "w"))
    print(len(feats), "rings", round(sum(f["properties"]["length_m"] for f in feats) / 1000, 1), "km",
          {r: sum(1 for f in feats if f["properties"]["road"] == r) for r in ("main", "collector", "local")})


if __name__ == "__main__":
    main(sys.argv[1:])
