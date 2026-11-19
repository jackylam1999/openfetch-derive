"""kerbguard.py inputs from kerbvic prep dirs: lots and roads cut per 1 km MGA 55 square (<x000>_<y000>.json, 100 m margin), building
footprints per square (<x>_<y>.json, lon/lat), each feature once across the runs.
    python3 guard_in.py out_dir prep_a [prep_b ...]"""
import json, os, sys
from shapely.geometry import shape, box


def main(a):
    out, preps = a[0], a[1:]
    for k in ("lots", "roads", "bld"):
        os.makedirs(f"{out}/{k}", exist_ok=True)
    for k in ("lots", "roads"):
        seen, feats = set(), []
        for p in preps:
            for f in json.load(open(f"{p}/{k}/{k}.json"))["features"]:
                key = json.dumps(f["geometry"]["coordinates"][:2] if f.get("geometry") else None) + str((f.get("properties") or {}).get("OBJECTID"))
                if f.get("geometry") and key not in seen:
                    seen.add(key); feats.append((f, shape(f["geometry"])))
        cells = {}
        for f, g in feats:
            x0, y0, x1, y1 = g.bounds
            for x in range(int((x0 - 100) // 1000), int((x1 + 100) // 1000) + 1):
                for y in range(int((y0 - 100) // 1000), int((y1 + 100) // 1000) + 1):
                    if g.intersects(box(x * 1000 - 100, y * 1000 - 100, x * 1000 + 1100, y * 1000 + 1100)):
                        cells.setdefault((x, y), []).append(f)
        for (x, y), fs in cells.items():
            json.dump({"type": "FeatureCollection", "features": fs}, open(f"{out}/{k}/{x * 1000}_{y * 1000}.json", "w"))
        print(k, len(feats), "features", len(cells), "squares")
    bl = {}
    for p in preps:
        for fn in os.listdir(f"{p}/bld"):
            d = bl.setdefault(fn, {})
            for f in json.load(open(f"{p}/bld/{fn}"))["features"]:
                d.setdefault(json.dumps(f["geometry"]["coordinates"][0][:3]), f)
    for fn, d in bl.items():
        json.dump({"type": "FeatureCollection", "features": list(d.values())}, open(f"{out}/bld/{fn}", "w"))
    print("bld", sum(len(d) for d in bl.values()), "footprints", len(bl), "squares")


if __name__ == "__main__":
    main(sys.argv[1:])
