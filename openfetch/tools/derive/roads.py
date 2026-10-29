#!/usr/bin/env python3
"""NSW road centrelines (Spatial Services RoadSegment, CC BY 4.0) for one MGA56 box, used by kerbs.py to drop kerb finds
in cadastre gaps that are not streets (creek reserves, unregistered strips).

Usage: python3 tools/derive/roads.py xmin ymin xmax ymax out.geojson
A failed download writes an empty layer and says so: kerbs.py then keeps every find in the road reserve.
"""
import sys, json
import lots

lots.URL = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Transport_Theme/FeatureServer/5/query"


def main():
    x0, y0, x1, y1 = map(float, sys.argv[1:5]); out = sys.argv[5]
    base = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": 7856, "outSR": 7856,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID", "orderByFields": "OBJECTID",
            "resultRecordCount": lots.PAGE, "f": "geojson"}
    feats, off = [], 0
    try:
        while True:
            d = lots.fetch({**base, "resultOffset": off})
            got = d.get("features", [])
            feats += [{"type": "Feature", "geometry": f["geometry"], "properties": {}} for f in got if f.get("geometry")]
            off += len(got)
            if len(got) < lots.PAGE and not d.get("exceededTransferLimit"):
                break
    except Exception as e:
        print(f"roads: download failed ({e}); kerbs keep every find in the road reserve", file=sys.stderr)
        feats = []
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    print(f"{len(feats)} road segments -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
