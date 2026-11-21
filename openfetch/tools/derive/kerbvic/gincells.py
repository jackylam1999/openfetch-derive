"""gincells.py cells.txt out_dir : kerbguard lots/roads per 1 km MGA55 square (100 m margin) straight from Vicmap ArcGIS (no prep dirs)"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import prep_vic as p
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
back = Transformer.from_crs(7855, 4326, always_xy=True); out = sys.argv[2]
for k in ("lots", "roads"): os.makedirs(f"{out}/{k}", exist_ok=True)
def one(c):
    x, y = c; lo, la = back.transform(x * 1000 - 100, y * 1000 - 100); hi, ha = back.transform(x * 1000 + 1100, y * 1000 + 1100); bb = (lo, la, hi, ha)
    fn = f"{out}/lots/{x * 1000}_{y * 1000}.json"
    if os.path.exists(fn): return
    lots = [f for f in p.arc("Vicmap_Parcel/FeatureServer/0", bb) if f.get("geometry") and f["properties"].get("parcel_road") != "Y"]
    roads = [f for f in p.arc("Vicmap_Transport/FeatureServer/1", bb) if f.get("geometry")]
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": p.road_props(f["properties"]), "geometry": p.proj(f["geometry"])} for f in roads]}, open(f"{out}/roads/{x * 1000}_{y * 1000}.json", "w"))
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"OBJECTID": f["properties"]["OBJECTID"]}, "geometry": p.proj(f["geometry"])} for f in lots]}, open(fn, "w"))
    print(x, y, len(lots), len(roads), flush=True)
cells = [tuple(map(int, l.split())) for l in open(sys.argv[1]) if l.strip()]
with ThreadPoolExecutor(4) as ex: list(ex.map(one, cells))
