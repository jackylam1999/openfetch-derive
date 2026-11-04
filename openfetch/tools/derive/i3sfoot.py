#!/usr/bin/env python3
"""Official roof judge from a council's I3S 3D-object scene layer (RT4, docs/handoffs/roof-tracing-rounds.md).

Reads every leaf node's uncompressed geometry (geometries/0) and attributes, joins each building's triangles in plan into
one footprint, and writes a GeoJSON in the layer's CRS with HEIGHT_MAX = top of the mesh - bottom of the mesh (m), the
same field roofscore.py reads for Central Coast. Wollongong LOD2 (Aerometrex Nov 2024) is MGA 56 + AHD.

Usage: python3 tools/derive/i3sfoot.py SCENE_LAYER_URL out.geojson [--box xmin ymin xmax ymax]
"""
import sys, json, gzip, struct, urllib.request
import numpy as np
import shapely
from shapely.geometry import mapping, box as sbox

HDR = {"User-Agent": "openfetch-derive", "Accept-Encoding": "gzip"}


def get(url):
    b = urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=120).read()
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def attrs(url, info):
    """OBJECTID and the Float64 fields of one node (strings skipped)."""
    out = {}
    for a in info:
        b = get(f"{url}/attributes/{a['key']}/0")
        n = struct.unpack_from("<I", b, 0)[0]
        if "objectIds" in a:
            out[a["name"]] = np.frombuffer(b, "<u4", n, 4)
        elif a.get("attributeValues", {}).get("valueType") == "Float64":
            off = 4 + (-4) % 8  # values are 8-byte aligned after the header
            out[a["name"]] = np.frombuffer(b, "<f8", n, off)
    return out


def main(a):
    url, fn = a[0], a[1]
    clip = sbox(*map(float, a[a.index("--box") + 1:a.index("--box") + 5])) if "--box" in a else None
    L = json.loads(get(url + "?f=json"))
    per = L["store"]["defaultGeometrySchema"]
    assert per["ordering"] == ["position", "normal", "uv0", "color"], per["ordering"]
    nodes, page = [], 0
    while True:
        p = json.loads(get(f"{url}/nodepages/{page}"))["nodes"]
        nodes += p
        if len(p) < L["nodePages"]["nodesPerPage"]:
            break
        page += 1
    feats = {}
    for nd in nodes:
        m = nd.get("mesh")
        if not m or nd.get("children"):
            continue
        r = m["geometry"]["resource"]
        b = get(f"{url}/nodes/{r}/geometries/0")
        vc, fc = struct.unpack_from("<II", b, 0)
        o = 8
        pos = np.frombuffer(b, "<f4", vc * 3, o).reshape(-1, 3).astype("f8") + nd["obb"]["center"]
        o += vc * (12 + 12 + 8 + 4)
        fid = np.frombuffer(b, "<u8", fc, o); o += fc * 8
        fr = np.frombuffer(b, "<u4", fc * 2, o).reshape(-1, 2)
        at = attrs(f"{url}/nodes/{r}", L["attributeStorageInfo"])
        ids = at.get("OBJECTID")
        for k in range(fc):
            t0, t1 = fr[k]
            P = pos[t0 * 3:(t1 + 1) * 3]
            fe = feats.setdefault(int(fid[k]), {"xy": [], "z": []})
            fe["xy"].append(P[:, :2].reshape(-1, 3, 2)); fe["z"].append(P[:, 2])
            if ids is not None:
                j = np.nonzero(ids == fid[k])[0]
                if len(j):
                    fe["p"] = {n: float(v[j[0]]) for n, v in at.items() if n != "OBJECTID"}
    out = []
    for i, fe in feats.items():
        tri = np.concatenate(fe["xy"])
        z = np.concatenate(fe["z"])
        g = shapely.union_all(shapely.polygons(np.concatenate([tri, tri[:, :1]], 1))).buffer(0.05).buffer(-0.05)
        g = g.simplify(0.1)
        if g.is_empty or (clip is not None and not g.intersects(clip)):
            continue
        if g.geom_type == "MultiPolygon":  # one footprint per building: keep the biggest piece
            g = max(g.geoms, key=lambda q: q.area)
        if g.area < 4:
            continue
        p = {"OBJECTID": i, **fe.get("p", {}), "HEIGHT_MAX": round(float(z.max() - z.min()), 2), "z_top": round(float(z.max()), 2)}
        out.append({"type": "Feature", "geometry": mapping(shapely.Polygon(g.exterior)), "properties": p})
    json.dump({"type": "FeatureCollection", "features": out}, open(fn, "w"))
    print(f"{len(out)} footprints -> {fn}")


if __name__ == "__main__":
    main(sys.argv[1:])
