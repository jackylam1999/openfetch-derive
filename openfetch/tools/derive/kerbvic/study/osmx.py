import osmium, json, math, sys, os
BOX = json.load(open(os.path.join(os.path.dirname(__file__), "boxes.json")))
def bb(lat, lon, half=600):
    dlat = half / 111320; dlon = half / (111320 * math.cos(math.radians(lat))); return lon - dlon, lat - dlat, lon + dlon, lat + dlat
BB = {k: bb(*v) for k, v in BOX.items()}
out = {k: [] for k in BB}
KEEP = ("highway", "footway", "barrier", "width", "sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both", "lanes", "parking:both", "parking:left", "parking:right", "est_width", "area:highway", "kerb", "name", "parking:lane:both", "parking:lane:left", "parking:lane:right", "area", "amenity")
class H(osmium.SimpleHandler):
    def way(self, w):
        t = w.tags
        if not ("highway" in t or t.get("barrier") == "kerb" or "area:highway" in t or t.get("amenity") == "parking"): return
        try: c = [(n.lon, n.lat) for n in w.nodes]
        except Exception: return
        if len(c) < 2: return
        x0 = min(p[0] for p in c); x1 = max(p[0] for p in c); y0 = min(p[1] for p in c); y1 = max(p[1] for p in c)
        for k, b in BB.items():
            if x1 >= b[0] and x0 <= b[2] and y1 >= b[1] and y0 <= b[3]:
                out[k].append({"type": "Feature", "properties": {kk: t[kk] for kk in KEEP if kk in t} | {"id": w.id}, "geometry": {"type": "LineString", "coordinates": c}})
H().apply_file(sys.argv[1], locations=True, idx="flex_mem")
for k, F in out.items():
    json.dump({"type": "FeatureCollection", "features": F}, open(os.path.join(os.path.dirname(__file__), "..", "data", k, "osm.geojson"), "w")); print(k, len(F))
