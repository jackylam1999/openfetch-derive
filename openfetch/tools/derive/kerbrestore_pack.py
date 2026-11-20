"""Blind close-up pack for a kerbrestore batch (card KN23): N random crops over the restored pieces plus M over the sides that were left
out, shuffled, key hidden. Each crop is 60 m square on the NSW aerial (zoom 20, falling back to 19 and 18 where a tile is missing; a
crop made only of missing tiles is refused), the line as drawn in magenta, a cyan ring at the centre, the banner is the draw number only.

    python3 kerbrestore_pack.py restored.geojson dropped.geojson report.json "Suburb,Suburb" seed n_kept n_cut out_dir
writes out_dir/cNN.jpg, out_dir/sheetN.jpg (8 crops a sheet) and out_dir/key.json (what each crop is; the reviewer never sees it).
"""
import io, json, os, sys, time, urllib.request
import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import LineString

TR = Transformer.from_crs(4326, 7856, always_xy=True)
BK = Transformer.from_crs(7856, 4326, always_xy=True)
INV = Transformer.from_crs(7856, 3857, always_xy=True)
ORG = 20037508.342789244
S, PX = 60.0, 720
CACHE = {}


def tile(z, ty, tx):
    k = (z, ty, tx)
    if k not in CACHE:
        u = f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{ty}/{tx}"
        im = None
        for a in range(4):
            try:
                im = np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=60).read())).convert("RGB"))
                break
            except Exception as e:
                if "404" in str(e):
                    break
                time.sleep(2 * (a + 1))
        CACHE[k] = im
    return CACHE[k]


def needed(cx, cy, z=20):
    res = 2 * ORG / 256 / 2 ** z
    mx, my = INV.transform(np.array([cx - S / 2, cx + S / 2]), np.array([cy - S / 2, cy + S / 2]))
    c, r = ((mx + ORG) / res).astype(int), ((ORG - my) / res).astype(int)
    return [(z, ty, tx) for tx in range(c.min() // 256, c.max() // 256 + 1) for ty in range(r.min() // 256, r.max() // 256 + 1)]


def prefetch(spots):
    from concurrent.futures import ThreadPoolExecutor
    todo = sorted({t for m in spots for t in needed(*m)})
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda t: tile(*t), todo))


def crop(cx, cy):
    """(image, share of pixels from real tiles) centred on MGA56 (cx, cy)."""
    xs = cx - S / 2 + (np.arange(PX) + 0.5) * S / PX
    ys = cy + S / 2 - (np.arange(PX) + 0.5) * S / PX
    X, Y = np.meshgrid(xs, ys)
    mx, my = INV.transform(X, Y)
    out = np.full((PX, PX, 3), 128, np.uint8)
    have = np.zeros((PX, PX), bool)
    for z in (20, 19, 18):
        res = 2 * ORG / 256 / 2 ** z
        c, r = ((mx + ORG) / res).astype(int), ((ORG - my) / res).astype(int)
        for tx in range(c.min() // 256, c.max() // 256 + 1):
            for ty in range(r.min() // 256, r.max() // 256 + 1):
                m = (c // 256 == tx) & (r // 256 == ty) & ~have
                if not m.any():
                    continue
                t = tile(z, ty, tx)
                if t is None or t.std() < 3:
                    continue
                out[m] = t[r[m] % 256, c[m] % 256]
                have |= m
    return Image.fromarray(out), float(have.mean())


def lines(fc):
    out = []
    for f in fc["features"]:
        P = np.array([TR.transform(*c[:2]) for c in f["geometry"]["coordinates"]])
        if len(P) > 1:
            out.append((P, f["properties"]))
    return out


def draw(n, k, tag, Pm, Ls):
    im, have = crop(*Pm)
    if have < 0.9:
        return None
    d = ImageDraw.Draw(im)
    x0, y0, kk = Pm[0] - S / 2, Pm[1] - S / 2, PX / S
    for Q in Ls:
        if Q[:, 0].min() < Pm[0] + 60 and Q[:, 0].max() > Pm[0] - 60 and Q[:, 1].min() < Pm[1] + 60 and Q[:, 1].max() > Pm[1] - 60:
            d.line([((x - x0) * kk, (y0 + S - y) * kk) for x, y in Q], fill=(255, 0, 255), width=3)
    d.ellipse([PX / 2 - 9, PX / 2 - 9, PX / 2 + 9, PX / 2 + 9], outline=(0, 255, 255), width=2)
    d.rectangle([0, 0, PX, 24], fill=(0, 0, 0))
    d.text((6, 6), f"crop {n:02d}", fill=(255, 255, 0))
    return im


def pick(rng, items, n, area, seen):
    """n length-weighted random spots over items [(P, props)] whose first area is in area; at least 60 m apart."""
    its = [(P, p) for P, p in items if (p.get("areas") or "").split(",")[0] in area]
    if not its:
        return []
    lens = np.array([np.hypot(*np.diff(P, axis=0).T).sum() for P, _ in its])
    out, tries = [], 0
    while len(out) < n and tries < 40 * n:
        tries += 1
        i = rng.choice(len(its), p=lens / lens.sum())
        P, p = its[i]
        seg = np.hypot(*np.diff(P, axis=0).T)
        t = rng.uniform(0, seg.sum())
        j = min(int(np.searchsorted(np.cumsum(seg), t)), len(seg) - 1)
        m = P[j] + (P[j + 1] - P[j]) * rng.uniform(0, 1)
        if any(np.hypot(*(m - q)) < 60 for q in seen):
            continue
        seen.append(m)
        out.append((m, p, P))
    return out


def main(a):
    kept, dropped = lines(json.load(open(a[0]))), lines(json.load(open(a[1])))
    rep = json.load(open(a[2]))
    area = set(a[3].split(","))
    seed, nk, nc, out = int(a[4]), int(a[5]), int(a[6]), a[7]
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(seed)
    seen = []
    cut = [(P, p) for P, p in dropped]
    # sides left out: the stretches of dropped lines the report lists as not kept
    left = []
    for l in rep["lines"]:
        for s in l["sides"]:
            if s["why"]:
                left.append((l["i"], s))
    by = {p["src_index"]: P for P, p in dropped}
    props = {p["src_index"]: p for _, p in dropped}
    cutp = []
    for i, s in left:
        if i in by and (props[i].get("areas") or "").split(",")[0] in area and s["len_m"] >= 25:
            L = LineString(by[i])
            seg = np.array([L.interpolate(t).coords[0] for t in np.arange(s["s0"], s["s1"], 2.0)])
            if len(seg) > 1:
                cutp.append((seg, dict(props[i], side=s["why"])))
    spots = [("kept",) + x for x in pick(rng, kept, nk, area, seen)] + [("cut",) + x for x in pick(rng, cutp, nc, area, seen)]
    prefetch([sp[1] for sp in spots])
    order = rng.permutation(len(spots))
    key, n = {}, 0
    for o in order:
        kind, m, p, P = spots[int(o)]
        ls = [Q for Q, _ in (kept if kind == "kept" else cutp)]
        im = draw(n + 1, kind, kind, m, ls)
        if im is None:
            continue
        n += 1
        im.save(os.path.join(out, f"c{n:02d}.jpg"), quality=85)
        key[f"crop {n:02d}"] = {"kind": kind, "area": (p.get("areas") or "").split(",")[0], "tier": p.get("tier"), "why": p.get("side"),
                                "src_index": p.get("src_index"), "lonlat": [round(v, 6) for v in BK.transform(*m)]}
    json.dump(key, open(os.path.join(out, "key.json"), "w"), indent=0)
    for s in range(0, n, 8):
        Sh = Image.new("RGB", (4 * 360, 2 * 360), "white")
        for q in range(min(8, n - s)):
            Sh.paste(Image.open(os.path.join(out, f"c{s + q + 1:02d}.jpg")).resize((360, 360)), ((q % 4) * 360, (q // 4) * 360))
        Sh.save(os.path.join(out, f"sheet{s // 8 + 1}.jpg"), quality=85)
    print("crops", n, "kept", sum(v["kind"] == "kept" for v in key.values()), "cut", sum(v["kind"] == "cut" for v in key.values()))


if __name__ == "__main__":
    main(sys.argv[1:])
