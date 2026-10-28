#!/usr/bin/env python3
"""NSW cadastre lots (Spatial Services, CC BY 4.0) for one MGA56 box, used by gapfill.py to cut traced roofs along lot lines.

Usage: python3 tools/derive/lots.py xmin ymin xmax ymax out.geojson

Reads the NSW Cadastre Lot layer 100 lots per request (its page limit) and writes them in EPSG:7856 with `lot` (lot/section/plan)
and `area` (m2, from the shape). A failed download writes an empty layer and says so: gapfill.py then falls back to the LiDAR
(ground gaps, roof height steps) alone.
"""
import sys, json, time, urllib.request, urllib.parse

URL = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query"
HDR = {"User-Agent": "Mozilla/5.0 openfetch-derive"}
PAGE = 100


def fetch(q):
    for i in range(4):
        try:
            rq = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), headers=HDR)
            return json.loads(urllib.request.urlopen(rq, timeout=60).read())
        except Exception:
            if i == 3:
                raise
            time.sleep(2 ** (i + 1))


def main():
    from shapely.geometry import shape, mapping
    x0, y0, x1, y1 = map(float, sys.argv[1:5]); out = sys.argv[5]
    base = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": 7856, "outSR": 7856,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "lotidstring", "orderByFields": "OBJECTID",
            "resultRecordCount": PAGE, "f": "geojson"}
    feats, seen, off = [], set(), 0
    try:
        while True:
            d = fetch({**base, "resultOffset": off})
            got = d.get("features", [])
            for f in got:
                if not f.get("geometry"):
                    continue
                g = shape(f["geometry"]).buffer(0)
                lot = f["properties"].get("lotidstring") or ""
                if g.is_empty or (lot, round(g.area)) in seen:
                    continue
                seen.add((lot, round(g.area)))
                feats.append({"type": "Feature", "geometry": mapping(g), "properties": {"lot": lot, "area": round(g.area, 1)}})
            off += len(got)
            if len(got) < PAGE and not d.get("exceededTransferLimit"):
                break
    except Exception as e:
        print(f"lots: cadastre download failed ({e}); no lot lines, LiDAR splitting only", file=sys.stderr)
        feats = []
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    print(f"{len(feats)} cadastre lots -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
