"""Council kerb lines for the derive kerb tools (truth for scoring, or a source), read only through the council's registry datum entry
(data/sources/nsw/<council>.json "datum"). Several council layers answer outSR 7856 with GDA94 numbers: Parramatta (Data.NSW hosted,
Web Mercator stored) and Canterbury-Bankstown (AGOL, outSR 4326 gives the stored GDA94 coordinates) read that way sat 0.48 E / 1.42 N
(1.5 m SW) off the LiDAR and made good kerbs look odd (canopy round 8, 21 Nov 2026, P-0254; same trap as the NSW state themes, P-0244).

Rule: ask the server for the "served" code; read the numbers as "stored" when shift is "client" (the app moves them on the page),
as "served" when shift is "none"; convert to GDA2020 MGA56 (7856) with pyproj. "unknown" or a missing entry is refused.

    python3 kerbtruth.py fetch <registry.json> <layer_url> <cells: 322_6242,...> <out.json>
    python3 kerbtruth.py --selftest
"""
import json, sys, urllib.parse, urllib.request

EPSG = {"EPSG:4283": 4283, "EPSG:4326": 4326, "EPSG:7844": 7844, "EPSG:7856": 7856, "EPSG:28356": 28356, "EPSG:3857": 3857}


class Refused(Exception):
    pass


def plan(datum):
    """(code to ask the server for, code its numbers really are) from a registry datum entry; Refused when nobody checked it."""
    if not datum or datum.get("shift") not in ("client", "none"):
        raise Refused("no checked datum entry (shift %r): measure the layer and record it in the registry first" % (datum or {}).get("shift"))
    served, stored = EPSG.get(datum.get("served")), EPSG.get(datum.get("stored"))
    if served is None:
        raise Refused("served CRS %r not known" % datum.get("served"))
    real = stored if datum["shift"] == "client" else served
    if real is None or real == 3857:
        raise Refused("shift %s but stored CRS %r is not a datum" % (datum["shift"], datum.get("stored")))
    return served, real


def transformer(real):
    from pyproj import Transformer
    return Transformer.from_crs(real, 7856, always_xy=True)


def to7856(paths, real):
    t = transformer(real)
    return [[list(t.transform(*q[:2])) for q in p] for p in paths]


def fetch(registry, url, cells, ua="openfetch-derive"):
    """Polylines (7856) of layer url intersecting 1 km cells [(i, j)], read through the registry entry's datum."""
    served, real = plan(json.load(open(registry)).get("datum"))
    out = []
    for i, j in cells:
        off = 0
        while True:
            q = {"geometry": f"{i * 1000},{j * 1000},{i * 1000 + 1000},{j * 1000 + 1000}", "geometryType": "esriGeometryEnvelope", "inSR": 7856,
                 "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "outSR": served, "f": "json",
                 "resultOffset": off, "resultRecordCount": 1000}
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/query?" + urllib.parse.urlencode(q),
                                                                          headers={"User-Agent": ua}), timeout=90).read())
            if "error" in d:
                raise RuntimeError(d["error"])
            fs = d.get("features", [])
            out += to7856([p for f in fs for p in (f.get("geometry") or {}).get("paths", [])], real)
            off += len(fs)
            if not fs or not d.get("exceededTransferLimit"):
                break
    return out


def selftest():
    lonlat = (151.0583, -33.9568)   # a Narwee street corner
    cb = {"stored": "EPSG:4283", "served": "EPSG:4326", "shift": "client"}
    s, r = plan(cb); assert (s, r) == (4326, 4283), (s, r)
    moved = to7856([[lonlat]], r)[0][0]; naive = to7856([[lonlat]], 4326)[0][0]
    dx, dy = moved[0] - naive[0], moved[1] - naive[1]
    assert abs(dx - 0.48) < 0.05 and abs(dy - 1.42) < 0.05, ("GDA94 numbers move 0.48 E 1.42 N into GDA2020", dx, dy)
    assert plan({"stored": "EPSG:4283", "served": "EPSG:4283", "shift": "client"}) == (4283, 4283)    # Parramatta
    assert plan({"stored": "EPSG:3857", "served": "EPSG:7844", "shift": "none"}) == (7844, 7844)      # Woollahra
    for bad in (None, {"stored": "unknown", "served": "EPSG:7844", "shift": "unknown"}, {"stored": "EPSG:3857", "served": "EPSG:4326", "shift": "client"}):
        try:
            plan(bad); raise AssertionError("must refuse %r" % bad)
        except Refused:
            pass
    print("kerbtruth selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        selftest()
    elif sys.argv[1:2] == ["fetch"]:
        reg, url, cells, dst = sys.argv[2:6]
        L = fetch(reg, url, [tuple(map(int, c.split("_"))) for c in cells.split(",")])
        json.dump(L, open(dst, "w")); print(len(L), "lines")
    else:
        print(__doc__)
