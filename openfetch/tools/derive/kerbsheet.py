"""Contact sheet of kerb spots on the NSW aerial: one tile per spot, kerbs cyan, the spot magenta.

    python3 kerbsheet.py kerbs.json(lon/lat GeoJSON) spots.json out.png [--n 12] [--cols 4] [--m 80] [--label "open corner"]
                         [--before other_kerbs.json]

spots.json: a list of [x, y, ...] in EPSG 7856, or a kerbaudit.py result: then the worst spots (open corners on the busiest roads
with the biggest gap, then fussy dead-end caps) make the per-version sheet. With --before,
each spot gets two tiles side by side: the other kerbs (grey label "before") and these kerbs ("after").
With --ref council.json (a kerbscore.py fetch, EPSG 7856 labels) the council's own kerbs are drawn yellow under ours, so a checker
sees where we differ from the official lines; --datum 94 when that council's layer is really GDA94 (Parramatta): its lines and
the spots (a kerbscore.py --out file) are moved back onto GDA2020 first.
"""
import io
import json
import sys
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import box

import kerbaudit as ka

IMG = ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={},{},{},{}&bboxSR=7856"
       "&imageSR=7856&size={},{}&format=jpg&f=image")
PX = 400


def photo(x0, y0, x1, y1):
    for k in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(IMG.format(x0, y0, x1, y1, PX, PX),
                                                              headers={"User-Agent": "openfetch-derive"}), timeout=60)
            return Image.open(io.BytesIO(r.read())).convert("RGB").resize((PX, PX))
        except Exception:
            time.sleep(2 * (k + 1))
    return Image.new("RGB", (PX, PX), (60, 60, 60))


def tile(kerbs, x, y, m, text, ref=None):
    x0, y0, x1, y1 = x - m / 2, y - m / 2, x + m / 2, y + m / 2
    im = photo(x0, y0, x1, y1); dr = ImageDraw.Draw(im)
    s = PX / m
    clip = box(x0 - 5, y0 - 5, x1 + 5, y1 + 5)
    for k in ref or []:
        if box(*k.bounds).intersects(clip):
            dr.line([((px - x0) * s, (y1 - py) * s) for px, py in np.asarray(k.coords)], fill=(255, 210, 0), width=5)
    for k in kerbs:
        kx, ky = k[:, 0], k[:, 1]
        if kx.max() < clip.bounds[0] or kx.min() > clip.bounds[2] or ky.max() < clip.bounds[1] or ky.min() > clip.bounds[3]:
            continue
        dr.line([((px - x0) * s, (y1 - py) * s) for px, py in k], fill=(0, 230, 255), width=3)
    cx, cy = PX / 2, PX / 2
    dr.line([(cx - 9, cy), (cx + 9, cy)], fill=(255, 0, 255), width=5); dr.line([(cx, cy - 9), (cx, cy + 9)], fill=(255, 0, 255), width=5)
    dr.rectangle([6, 6, 8 + 7 * len(text), 26], fill=(0, 0, 0)); dr.text((10, 10), text, fill=(255, 255, 255))
    L = 20 * s; dr.line([(14, PX - 22), (14 + L, PX - 22)], fill=(255, 255, 255), width=3); dr.text((16, PX - 38), "20 m", fill=(255, 255, 255))
    return im


def worst(audit, n=12):
    """The spots Jacky looks at per version: open corners on the busiest roads with the biggest gap first (two thirds), then
    fussy dead-end caps, one per 150 m."""
    p = sorted(audit.get("points", []), key=lambda q: (q[3], -q[2]))
    f = []
    for x, y, _ in audit.get("fussy_points", []):
        if all(np.hypot(x - u, y - v) > 150 for u, v in f):
            f.append((x, y))
    k = min(len(f), n - min(len(p), n * 2 // 3))
    return p[:n - k] + [[x, y] for x, y in f[:k]]


def main(a):
    n = int(a[a.index("--n") + 1]) if "--n" in a else 12
    cols = int(a[a.index("--cols") + 1]) if "--cols" in a else 4
    m = float(a[a.index("--m") + 1]) if "--m" in a else 80.0
    label = a[a.index("--label") + 1] if "--label" in a else "open corner"
    kerbs = ka.read_kerbs(a[0])
    spots = json.load(open(a[1]))
    ref = None
    if "--ref" in a:
        import kerbscore
        from pyproj import Transformer
        back = Transformer.from_crs(28356, 7856, always_xy=True).transform if "--datum" in a and a[a.index("--datum") + 1] == "94" else None
        ref = kerbscore.lines_of(json.load(open(a[a.index("--ref") + 1])), back)
        if isinstance(spots, dict) and "open_ends" in spots:
            spots = spots["open_ends"]
        if back:
            spots = [list(back(sp[0], sp[1])) for sp in spots]
    if isinstance(spots, dict):
        spots = worst(spots, n)
    spots = spots[:n]
    before = ka.read_kerbs(a[a.index("--before") + 1]) if "--before" in a else None
    w = 2 if before else 1
    rows = (len(spots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w * (PX + 4), max(rows, 1) * (PX + 4)), (255, 255, 255))
    for i, sp in enumerate(spots):
        x, y = sp[0], sp[1]
        r, c = divmod(i, cols)
        if before:
            sheet.paste(tile(before, x, y, m, f"{label} {i + 1} before"), (c * 2 * (PX + 4), r * (PX + 4)))
            sheet.paste(tile(kerbs, x, y, m, f"{label} {i + 1} after", ref), ((c * 2 + 1) * (PX + 4), r * (PX + 4)))
        else:
            sheet.paste(tile(kerbs, x, y, m, f"{label} {i + 1}", ref), (c * (PX + 4), r * (PX + 4)))
    sheet.save(a[2])
    print(a[2], len(spots))


if __name__ == "__main__":
    main(sys.argv[1:])
