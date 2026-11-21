"""Council kerb-inlet pits as a footpath measure (kerb scenario 16, flush CBD kerbs, 21 Nov 2026).
A kerb inlet is built into the kerb, so where the LiDAR saw no kerb step (flush CBD kerbs, awnings, buses, deep shadow) the inlets
in front of a block side give its footpath width: lot front to pit. City of Sydney kerb inlets lie on the LiDAR-traced kerbs where
both exist (315 of ~1,000 within 0.25 m, 450 within 0.5 m; the rest are mostly on sides with no traced kerb). kerblot.py uses this
only when no LiDAR or earlier-kerb measure exists for a side.

    python3 kerbpit.py --fetch box_lon0 box_lat0 box_lon1 box_lat1 out.json    (City of Sydney Drainage_pits with Kerb_Inlet_Length > 0)
    python3 kerbpit.py --selftest
"""
import json, sys, urllib.parse, urllib.request
import numpy as np
import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree

PIT_MIN = 2        # pits in front of a side
PIT_SPREAD = 1.0   # m: every pit within this of the side's median width
SOURCES = {"sydney": "https://services1.arcgis.com/cNVyNtjGVZybOQWZ/ArcGIS/rest/services/Drainage_pits/FeatureServer/0/query"}


def load(path, to):
    """Kerb-inlet pits (lon/lat GeoJSON points) as (points, tree) in the working grid."""
    pp = [Point(to(*f["geometry"]["coordinates"][:2])) for f in json.load(open(path))["features"]]
    return pp, STRtree(pp)


def width(comp, P, N, W, pits, d_min=1.0, d_max=7.0, step=2.0, pit_min=None):
    """Footpath width of one block side from the pits in front of it, or None. comp: the block; P, N, W: the side's front samples,
    outward normals and distance to the land across. A pit counts when it lies in the side's own sweep (never past its ends, never
    on the cross street) and outside the block, d_min to d_max m from the lot front."""
    if pits is None or len(P) < 2:
        return None
    G, T = pits
    reach = np.minimum(np.asarray(W, float), d_max + 1.0)[:, None]
    zone = shapely.union_all(shapely.linestrings(np.stack([P, P + N * reach], axis=1))).buffer(step * 0.75)
    w_med, d = float(np.median(W)), []
    for k in T.query(zone):
        q = G[int(k)]
        if zone.contains(q) and not comp.contains(q):
            dd = comp.exterior.distance(q)
            if d_min <= dd <= d_max and dd < w_med - 0.5:
                d.append(dd)
    if len(d) < (PIT_MIN if pit_min is None else pit_min):
        return None
    md = float(np.median(d))
    return md if max(abs(x - md) for x in d) <= PIT_SPREAD else None


def fetch(lon0, lat0, lon1, lat1, out, src="sydney"):
    F, off = [], 0
    while True:
        q = dict(where="Kerb_Inlet_Length > 0", geometry=f"{lon0},{lat0},{lon1},{lat1}", geometryType="esriGeometryEnvelope", inSR=7844,
                 outSR=7844, outFields="Asset_ID,Pit_Owner,Kerb_Inlet_Length", f="geojson", resultRecordCount=2000, resultOffset=off,
                 orderByFields="OBJECTID")
        d = json.load(urllib.request.urlopen(urllib.request.Request(SOURCES[src] + "?" + urllib.parse.urlencode(q),
                                                                    headers={"User-Agent": "openfetch-derive"}), timeout=90))
        g = d.get("features", []); F += g; off += len(g)
        if not g or not d.get("properties", {}).get("exceededTransferLimit"):
            break
    json.dump({"type": "FeatureCollection", "features": F}, open(out, "w"))
    return len(F)


def selftest():
    from shapely.geometry import box
    comp = box(0, 0, 100, 50)                                   # a block; its south side faces a street, land across at 20 m
    x = np.arange(1.0, 100.0, 2.0)
    P = np.c_[x, np.zeros_like(x)]; N = np.tile([0.0, -1.0], (len(x), 1)); W = np.full(len(x), 20.0)
    mk = lambda pts: ([Point(p) for p in pts], STRtree([Point(p) for p in pts]))
    assert abs(width(comp, P, N, W, mk([(20, -3.6), (60, -3.9), (85, -3.4)])) - 3.6) < 1e-9   # three inlets agree: median 3.6 m
    assert width(comp, P, N, W, mk([(20, -3.6)])) is None                                         # one inlet is not enough
    assert width(comp, P, N, W, mk([(20, -3.6), (60, -6.2)])) is None                             # disagree by 2.6 m: not a measure
    assert width(comp, P, N, W, mk([(20, -3.6), (-6, -3.5), (106, -3.5)])) is None               # past the side's ends: cross-street pits
    assert width(comp, P, N, W, mk([(20, -0.5), (60, -0.4)])) is None                             # under 1 m: a footpath grate, not a kerb
    assert width(comp, P, N, W, mk([(20, -9.0), (60, -9.5)])) is None                             # over 7 m: far kerb or road middle
    assert width(comp, P, N, np.full(len(x), 3.0), mk([(20, -3.6), (60, -3.9)])) is None          # beyond the land across (3 m reserve)
    assert width(comp, P, N, W, mk([(20, 3.6), (60, 3.9)])) is None                               # inside the block
    assert width(comp, P, N, W, None) is None
    print("kerbpit selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    if a and a[0] == "--fetch":
        print(fetch(*map(float, a[1:5]), a[5]))
        sys.exit(0)
    print(__doc__)
