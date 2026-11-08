"""Score OpenFetch kerb lines against a council's own kerb lines in one box, so a checker can say how close we are to the
official data (Jacky 6 Nov 2026: "perfect means like the official kerb data").

    python3 kerbscore.py fetch parramatta|northernbeaches x0 y0 x1 y1 ref.json     (box in EPSG 7856 metres)
    python3 kerbscore.py score kerbs.json(lon/lat) ref.json x0 y0 x1 y1 [--tol 1.0] [--out spots.json]

found    share of council kerb length within tol m of ours
precise  share of our kerb length within tol m of a council kerb
ends     our kerb ends inside the box (2 m in from its edge); "open" = an end where the council kerb carries on
         (council kerb within 2 m of the end, and council kerb again 10 m further on along our heading): a gap we left
gap_m    council kerb length with no kerb of ours within 3 m (missing runs, the thing open ends come from)

Datum: Parramatta's layer returns GDA94 positions labelled GDA2020 (measured 6 Nov 2026, ~1.5 m): score it with --datum 94, which
projects ours GDA2020 -> MGA56 (7856) -> GDA94 MGA56 (28356). Northern Beaches is true GDA2020: --datum 2020.
Boxes used 6 Nov 2026: Parramatta 315000 6256000 316000 6257000 (--datum 94); Mona Vale 342000 6272000 343000 6273000 and Newport
343000 6274000 344000 6275000 (--datum 2020; council lines there are themselves broken at every driveway, so only Parramatta's
are a cleanliness bar). `clean` compares how clean ours and the council's lines are (see clean()).
"""
import json
import sys
import urllib.parse
import urllib.request

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

LAYERS = {
    "parramatta": "https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/2/query",
    "northernbeaches": "https://maps.northernbeaches.nsw.gov.au/arcgis/rest/services/Assets/MapServer/12/query",
}


def fetch(a):
    url = LAYERS[a[0]]; x0, y0, x1, y1 = map(float, a[1:5]); out = a[5]
    feats, off = [], 0
    while True:
        q = dict(geometry=f"{x0},{y0},{x1},{y1}", geometryType="esriGeometryEnvelope", inSR=7856, outSR=7856,
                 spatialRel="esriSpatialRelIntersects", outFields="*", returnGeometry="true", f="geojson",
                 resultOffset=off, resultRecordCount=1000)
        r = json.load(urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(q),
                                                                      headers={"User-Agent": "openfetch-derive"}), timeout=120))
        fs = r.get("features", []); feats += fs; off += len(fs)
        if not fs or not r.get("exceededTransferLimit", len(fs) >= 100):
            break
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    print(len(feats), "council kerb features", file=sys.stderr)


def lines_of(fc, tr=None):
    out = []
    for f in fc["features"]:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        for p in (g.geoms if g.geom_type.startswith("Multi") else [g]):
            if p.geom_type != "LineString" or p.length == 0:
                continue
            c = np.asarray(p.coords)[:, :2]
            if tr is not None:
                x, y = tr(*c.T); c = np.c_[x, y]
            out.append(LineString(c))
    return out


def _share(A, B, tol, clip):
    """Share of the length of lines A (inside clip) within tol of lines B."""
    if not A:
        return 0.0, 0.0
    a = unary_union([g.intersection(clip) for g in A])
    L = a.length
    if L == 0:
        return 0.0, 0.0
    bb = unary_union([g.buffer(tol, quad_segs=4) for g in B]) if B else None
    if bb is None:
        return 0.0, L
    return a.intersection(bb).length / L, L


def score(kerbs_path, ref_path, bx, tol=1.0, datum="94", spots=None):
    t1 = Transformer.from_crs(7844, 7856, always_xy=True).transform
    t2 = Transformer.from_crs(7856, 28356, always_xy=True).transform
    tr = (lambda x, y: t2(*t1(x, y))) if datum == "94" else t1
    ours = [g for g in lines_of(json.load(open(kerbs_path)), tr) if g.intersects(box(*bx).buffer(50))]
    ref = lines_of(json.load(open(ref_path)))
    clip = box(*bx)
    found, Lr = _share(ref, ours, tol, clip)
    precise, Lo = _share(ours, ref, tol, clip)
    # missing council kerb (nothing of ours within 3 m)
    miss = 1 - _share(ref, ours, 3.0, clip)[0]
    rt = STRtree(ref) if ref else None
    inner = box(*bx).buffer(-2)
    ends = opn = 0; pts = []
    for g in ours:
        c = np.asarray(g.coords)
        for e, q in ((c[0], c[1:]), (c[-1], c[-2::-1])):
            if not inner.contains(Point(e)):
                continue
            ends += 1
            back = LineString(np.r_[[e], q]); t = back.interpolate(min(3.0, back.length)).coords[0]
            v = e - np.asarray(t); n = np.hypot(*v)
            if n < 1e-6 or rt is None:
                continue
            v = v / n
            near = lambda p, r: any(ref[int(k)].distance(Point(p)) <= r for k in rt.query(Point(p).buffer(r)))
            if near(e, 2.0) and near(e + v * 10, 2.0):
                opn += 1; pts.append([round(float(e[0]), 1), round(float(e[1]), 1)])
    r = {"found": round(100 * found, 1), "precise": round(100 * precise, 1), "ref_km": round(Lr / 1000, 2),
         "ours_km": round(Lo / 1000, 2), "missing_pct": round(100 * miss, 1), "ends": ends, "ends_open": opn}
    if spots:
        json.dump({"score": r, "open_ends": pts}, open(spots, "w"))
    return r


def clean(lines, bx, roads=None, lots=None):
    """How clean a set of kerb lines is inside box bx, the same way for council lines and ours (Jacky 6 Nov 2026: "council
    lines usually have very clean kerbs, closed curves ... you need to achieve the same level"): free ends per km (an end with
    no other kerb within 2 m), pieces per km, sharp kinks/wobbles per km, and with roads + lots the ends nothing explains
    (kerbaudit loose ends: not at a side street, a property or the box edge) per km."""
    import kerbaudit as ka
    from shapely.ops import linemerge
    clip = box(*bx)
    parts = []
    for g in lines:
        x = g.intersection(clip)
        for p in getattr(x, "geoms", [x]):
            if p.geom_type == "LineString" and p.length > 0.5:
                parts.append(p)
    m = linemerge(unary_union(parts)) if parts else None
    parts = [p for p in getattr(m, "geoms", [m]) if p is not None and p.length > 0.5] if m is not None else []
    km = sum(p.length for p in parts) / 1000
    if not parts:
        return {"km": 0}
    K = ka.Kerbs([np.asarray(p.coords) for p in parts])
    inner = clip.buffer(-3)
    free = 0
    for i, p in enumerate(K.p):
        for e in (p[0], p[-1]):
            pe = Point(e)
            if np.hypot(*(p[0] - p[-1])) < 1.0 or not inner.contains(pe):
                continue
            if any(int(k) != i and K.g[int(k)].distance(pe) <= 2.0 for k in K.tree.query(pe.buffer(2.0))):
                continue
            free += 1
    fr = ka.free_ends(K); edge = ka.traced_area(K).boundary
    inner_n = sum(1 for q in fr if edge.distance(Point(q)) >= ka.EDGE and inner.contains(Point(q)))
    r = {"km": round(km, 2), "pieces_per_km": round(len(parts) / km, 1), "free_ends_per_km": round(free / km, 1),
         "free_ends_inner_per_km": round(inner_n / km, 2),
         "kinks_per_km": round(len(ka.kinks(K)) / km, 2)}
    if roads is not None and lots is not None:
        loose, _ = ka.loose_ends(K, roads, lots)
        r["loose_ends_per_km"] = round(sum(1 for x in loose if inner.contains(Point(x))) / km, 1)
    return r


def compare(a):
    """kerbscore.py clean kerbs.json ref.json x0 y0 x1 y1 lots_dir roads_dir [--datum 94]: ours vs the council, cleanliness."""
    import kerbaudit as ka, kerbregular as kr
    bx = tuple(map(float, a[2:6]))
    datum = a[a.index("--datum") + 1] if "--datum" in a else "2020"
    back = Transformer.from_crs(28356, 7856, always_xy=True).transform if datum == "94" else None
    ref = lines_of(json.load(open(a[1])), back)
    ours = [LineString(k) for k in ka.read_kerbs(a[0]) if len(k) > 1]
    lots = [g for g in kr.load_faces(a[6]) if g.geom_type == "Polygon"]
    roads = ka.load_roads(a[7])
    return {"council": clean(ref, bx, roads, lots), "ours": clean(ours, bx, roads, lots)}


def main(a):
    if a[0] == "clean":
        return print(json.dumps(compare(a[1:])))
    if a[0] == "fetch":
        return fetch(a[1:])
    tol = float(a[a.index("--tol") + 1]) if "--tol" in a else 1.0
    datum = a[a.index("--datum") + 1] if "--datum" in a else "2020"
    out = a[a.index("--out") + 1] if "--out" in a else None
    print(json.dumps(score(a[1], a[2], tuple(map(float, a[3:7])), tol, datum, out)))


if __name__ == "__main__":
    main(sys.argv[1:])
