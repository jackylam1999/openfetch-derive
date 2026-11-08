#!/usr/bin/env python3
"""Check A (kerbs-direction.md "4 Nov 11:40Z"): score the SHIPPING output (kerbapply.py draw, which never sees council kerbs) on a
scored box it overlaps, against that box's council reference, as kerblearn scores the model: found / precise / offset by road type.
  python kerbshipcheck.py ship_dir kp_dir box thresh work_dir      (e.g. parramatta: the held-out box inside the Parramatta ship area)
"""
import sys, os, json, shutil
from shapely.geometry import shape, mapping, box as sbox
import kerblearn as kl
import kerbphoto as kp


def main():
    src, kpd, nm, th, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(kpd):
        if f.startswith(nm + "_") and not f.startswith(f"{nm}_derived") and not os.path.exists(f"{out}/{f}"):
            try:
                os.link(f"{kpd}/{f}", f"{out}/{f}")
            except OSError:
                shutil.copy(f"{kpd}/{f}", f"{out}/{f}")
    clip = sbox(*json.load(open(f"{kpd}/{nm}_meta.json"))["box"]); feats = []; used = []
    for f in os.listdir(src):
        if f.endswith("_drawn.json"):
            b = f[:-11]; m = json.load(open(f"{src}/{b}_meta.json"))
            if not sbox(*m["box"]).intersects(clip):
                continue
            used.append(b)
            own = sbox(*m["box"])  # each ship box keeps only its own square, as kerbapply.draw does
            for g in json.load(open(f"{src}/{b}_derived.geojson"))["features"]:
                s = shape(g["geometry"]).intersection(own).intersection(clip)
                if not s.is_empty:
                    feats.append({"type": "Feature", "geometry": mapping(s), "properties": g.get("properties") or {}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(f"{out}/{nm}_derived.geojson", "w"))
    s = kp.score(out, nm, th)
    os.replace(f"{out}/{nm}_derived.geojson", f"{out}/{nm}_derived_{th}.geojson")
    kl.SCEN.setdefault(nm, "?")
    r = kl._final((out, nm, th, s))[1]
    r["ship_boxes"] = used
    json.dump(r, open(f"{out}/{nm}_check.json", "w"), indent=1)
    print(json.dumps({k: r.get(k) for k in ("recall", "precision", "offset_median_m", "scales", "ship_boxes")}))


if __name__ == "__main__":
    main()
