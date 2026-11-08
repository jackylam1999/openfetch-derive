#!/usr/bin/env python3
"""Spot check by eye (kerbs-direction.md "4 Nov 11:40Z" step C): 3 seeded random 150 m patches on local streets per area, drawn as
contact sheets of 12 (photo at 0.1 m shown at 0.25 m, model lines red, street-offset lines orange, 10 m bar, area + patch id).
  python kerbspot.py ship_dir boxes.json out_dir [seed]    (writes sheet1..N.png and patches.json with each centre in MGA56)
"""
import sys, os, json
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import shape, box as sbox
import kerbapply as ka

PATCH, PX, PER = 150, 400, 12  # m, pixels per patch on the sheet, patches per sheet


def main():
    src, S, out = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]; seed = int(sys.argv[4]) if len(sys.argv) > 4 else 4114
    os.makedirs(out, exist_ok=True); rng = np.random.default_rng(seed); P = []
    for sub, lo, la in S["suburbs"]:
        cand = []
        for nm, x, y in ka.boxes(sub, lo, la, 2):
            if not os.path.exists(f"{src}/{nm}_derived.geojson"):
                continue
            inner = sbox(x + PATCH / 2, y + PATCH / 2, x + 1000 - PATCH / 2, y + 1000 - PATCH / 2)
            for f in json.load(open(f"{src}/{nm}_roads.geojson"))["features"]:
                if f.get("geometry") and (f.get("properties") or {}).get("functionhierarchy") == 6:
                    g = shape(f["geometry"]).intersection(inner)
                    for c in getattr(g, "geoms", [g]):
                        if c.geom_type == "LineString":
                            cand += [(nm, *c.interpolate(t).coords[0]) for t in np.arange(0, c.length, 25.0)]
        for i in rng.choice(len(cand), min(3, len(cand)), replace=False):
            nm, cx, cy = cand[i]; P.append({"area": sub, "box": nm, "x": round(cx, 1), "y": round(cy, 1)})
    for k, p in enumerate(P):
        p["id"] = f"{k + 1:02d} {p['area']}"
    json.dump(P, open(f"{out}/patches.json", "w"), indent=1)
    for s in range(0, len(P), PER):
        sheet = Image.new("RGB", (4 * PX, 3 * (PX + 24)), "white"); d = ImageDraw.Draw(sheet)
        for j, p in enumerate(P[s:s + PER]):
            m = json.load(open(f"{src}/{p['box']}_meta.json")); rgb = np.load(f"{src}/{p['box']}_rgb.npy", mmap_mode="r")
            c0 = int((p["x"] - PATCH / 2 - m["x0"]) / 0.1); r0 = int((m["y0"] + m["w"] - p["y"] - PATCH / 2) / 0.1); w = int(PATCH / 0.1)
            im = Image.fromarray(np.asarray(rgb[r0:r0 + w, c0:c0 + w])).resize((PX, PX)); dr = ImageDraw.Draw(im); sc = PX / PATCH
            for f in json.load(open(f"{src}/{p['box']}_derived.geojson"))["features"]:
                g = shape(f["geometry"]); col = (255, 140, 0) if (f.get("properties") or {}).get("street") else (255, 0, 0)
                for l in getattr(g, "geoms", [g]):
                    xy = [((a - p["x"] + PATCH / 2) * sc, (p["y"] + PATCH / 2 - b) * sc) for a, b in l.coords]
                    dr.line(xy, fill=col, width=2)
            dr.rectangle([8, PX - 16, 8 + 10 * sc, PX - 10], fill="white")
            X, Y = (j % 4) * PX, (j // 4) * (PX + 24)
            sheet.paste(im, (X, Y + 24)); d.text((X + 4, Y + 5), p["id"] + "   (bar 10 m)", fill="black")
        sheet.save(f"{out}/sheet{s // PER + 1}.png")
    print(len(P), "patches,", (len(P) + PER - 1) // PER, "sheets in", out)


if __name__ == "__main__":
    main()
