#!/usr/bin/env python3
"""Community building outlines (OSM + Microsoft, from our own Overture copy) for one MGA56 box.

Usage: python3 tools/derive/community.py xmin ymin xmax ymax out.geojson

Reads tiles.openfetch.earth (zoom 14) and returns each building once (by Overture id), clipped to the box by
intersection, in EPSG:7856. Property `src` is "osm" or "ms" (Microsoft ML footprints).
"""
import sys, json, math, gzip, urllib.request
from pmtiles.reader import Reader
import mapbox_vector_tile
from pyproj import Transformer
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

URL = "https://tiles.openfetch.earth/au/2026-10-21.0/buildings.pmtiles"
HDR = {"User-Agent": "Mozilla/5.0 openfetch-derive", "Origin": "https://openfetch.earth", "Referer": "https://openfetch.earth/"}
Z = 14


def get(offset, length):
    rq = urllib.request.Request(URL, headers={**HDR, "Range": f"bytes={offset}-{offset + length - 1}"})
    return urllib.request.urlopen(rq).read()


def main():
    x0, y0, x1, y1 = map(float, sys.argv[1:5]); out = sys.argv[5]
    to_ll = Transformer.from_crs(7856, 4326, always_xy=True); to_mga = Transformer.from_crs(4326, 7856, always_xy=True)
    lon0, lat0 = to_ll.transform(x0, y0); lon1, lat1 = to_ll.transform(x1, y1)
    n = 2 ** Z
    tx = lambda lon: int((lon + 180) / 360 * n)
    ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    r = Reader(get); clip = box(x0, y0, x1, y1); seen = {}; feats = []
    for x in range(tx(lon0), tx(lon1) + 1):
        for y in range(ty(lat1), ty(lat0) + 1):
            d = r.get(Z, x, y)
            if not d: continue
            if d[:2] == b"\x1f\x8b": d = gzip.decompress(d)
            for layer in mapbox_vector_tile.decode(d).values():
                ext = layer.get("extent", 4096)
                for f in layer["features"]:
                    g = f["geometry"]; p = f["properties"]
                    if g["type"] not in ("Polygon", "MultiPolygon"): continue
                    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
                    rings = []
                    for poly in polys:
                        rr = []
                        for ring in poly:
                            pts = []
                            for px, py in ring:
                                lon = (x + px / ext) / n * 360 - 180; yn = y + 1 - py / ext  # tile y origin is bottom-left
                                lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yn / n))))
                                pts.append(to_mga.transform(lon, lat))
                            rr.append(pts)
                        rings.append(rr)
                    geom = shape({"type": "MultiPolygon", "coordinates": rings}).buffer(0)
                    src = "ms" if "ml_buildings" in str(p.get("sources", "")) else "osm"
                    seen.setdefault(p.get("id"), [src, []])[1].append(geom)
    # a building cut by a tile edge comes as pieces with one id: join them, then keep it if it touches the box
    for i, (src, gs) in seen.items():
        geom = unary_union(gs).buffer(0.05, join_style=2).buffer(-0.05, join_style=2)
        if not geom.intersects(clip): continue
        if geom.geom_type != "Polygon": geom = max(geom.geoms, key=lambda q: q.area)
        feats.append({"type": "Feature", "geometry": mapping(geom), "properties": {"id": i, "src": src}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    print(f"{len(feats)} community buildings ({sum(f['properties']['src'] == 'osm' for f in feats)} OSM) -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
