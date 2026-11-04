#!/usr/bin/env python3
"""Score one roof box the way the kerb method scores a kerb box: found, precise, offset, MERGED and SPLIT against a reference,
one roof per lot, and a per-site view (what a user exporting a small site sees). docs/handoffs/roof-tracing-rounds.md.

Usage: python3 tools/derive/roofscore.py BOXDIR [--ref ref.geojson [--hmax FIELD]] [--box xmin ymin xmax ymax] [--tile 150] [--keep-double] [--json out.json]
       python3 tools/derive/roofscore.py brief scores1.json [scores2.json ...]      one table, one line per box

BOXDIR is a pipeline.py output folder (combined.geojson, traced.geojson, community.geojson, lots.geojson). Without --ref the
reference is the OSM shapes in community.geojson (hand-drawn, one per house in the inner suburbs; not official, say so).
With --ref (council footprints: Tweed, Central Coast, Wollongong LOD2) the reference is official. On OSM, block outlines drawn
over their own parts are left out of the reference (drop_double; --keep-double scores them as before RT5).

Per reference building: found = one output roof with IoU >= 0.5. Merged = its best output roof also covers 40 %+ of another
reference building (a terrace row traced as one roof). Split = 2+ output roofs each cover 30 %+ of it. Precise = share of output
roofs that match one reference building with IoU >= 0.5. Offset = median distance from reference corners to the matched outline.
Lots (NSW cadastre, 30-2000 m2): output roofs spanning 2+ lots, and built lots (40 %+ under a reference roof) with 0 / 1 / 2+ roofs.
Site view: the box cut into `tile` m squares; a tile passes when found >= 85 %, merged <= 5 % and extra <= 15 % there.
The raw trace (traced.geojson) is scored for merged too, so a change in the tracer and a change in the lot cut can be told apart.
"""
import sys, os, json
import numpy as np
from shapely.geometry import shape, box
from shapely.strtree import STRtree

TOL_IOU, MERGE_COVER, SPLIT_COVER = 0.5, 0.4, 0.3
LOT = (30, 2000)   # m2: lots that hold one house, terrace lots included (Erskineville median 132 m2, 21 % under 100)


def load(fn, keep=None):
    if not os.path.exists(fn):
        return [], []
    F = json.load(open(fn))["features"]
    G, P = [], []
    for f in F:
        if keep and not keep(f["properties"]):
            continue
        g = shape(f["geometry"]).buffer(0)
        if g.is_empty:
            continue
        if g.geom_type != "Polygon":
            g = max(g.geoms, key=lambda q: q.area)
        G.append(g); P.append(f["properties"])
    return G, P


def cover(a, b):
    return a.intersection(b).area / b.area if b.area else 0


def drop_double(R, Rp):
    """OSM draws some apartment blocks twice: the whole block outline AND its parts / podium (Overture keeps both, Zetland
    RT2). Judged as two houses, that outline 'merges' its own parts. Leave out every reference outline that holds 80 %+ of a
    smaller reference outline (the parts stay: they are the finer drawing), and exact repeats after the first."""
    rt = STRtree(R); drop = set()
    for i, r in enumerate(R):
        for k in rt.query(r):
            k = int(k)
            if k == i or k in drop or cover(r, R[k]) < 0.8:
                continue
            if R[k].area <= 0.8 * r.area or (k < i and cover(R[k], r) >= 0.8):
                drop.add(i); break
    keep = [i for i in range(len(R)) if i not in drop]
    return [R[i] for i in keep], [Rp[i] for i in keep], len(drop)


def match(R, O):
    """Per reference building: best output roof by IoU, merged flag, split flag. Per output roof: matched reference or None."""
    ot = STRtree(O); rt = STRtree(R)
    best = [(-1, 0.0)] * len(R)
    for i, r in enumerate(R):
        for j in ot.query(r):
            inter = r.intersection(O[j]).area
            if inter <= 0:
                continue
            iou = inter / r.union(O[j]).area
            if iou > best[i][1]:
                best[i] = (int(j), iou)
    covers = {}   # output roof -> reference buildings it covers 40 %+
    for j, o in enumerate(O):
        covers[j] = [int(i) for i in rt.query(o) if cover(o, R[i]) >= MERGE_COVER]
    merged = [best[i][0] >= 0 and len(covers[best[i][0]]) >= 2 for i in range(len(R))]
    split = [sum(1 for j in ot.query(r) if cover(O[j], r) >= SPLIT_COVER) >= 2 for r in R]
    found = [b[1] >= TOL_IOU for b in best]
    omatch = {}
    for i, (j, iou) in enumerate(best):
        if iou >= TOL_IOU:
            omatch[j] = max(omatch.get(j, 0), iou)
    return best, found, merged, split, omatch, covers


def offset(r, o):
    pts = np.asarray(r.exterior.coords)
    b = o.boundary
    from shapely.geometry import Point
    return float(np.median([b.distance(Point(x, y)) for x, y in pts]))


def score_box(d, ref=None, hmax="HEIGHT_MAX", tile=150, bbox=None, double=False):
    O, Op = load(os.path.join(d, "combined.geojson"))
    T, _ = load(os.path.join(d, "traced.geojson"))
    L, _ = load(os.path.join(d, "lots.geojson"))
    if ref:
        R, Rp = load(ref); kind = "official"
    else:
        R, Rp = load(os.path.join(d, "community.geojson"), lambda p: p.get("src") == "osm"); kind = "osm"
    # the pipeline traces 40 m past the box but writes only the box: judge the reference buildings whose centre is inside
    if O and not bbox:
        bbox = np.minimum.reduce([o.bounds for o in O])[:2].tolist() + np.maximum.reduce([o.bounds for o in O])[2:].tolist()
    if bbox:
        clip = box(*bbox)
        keep = [i for i, r in enumerate(R) if clip.contains(r.centroid)]
        R, Rp = [R[i] for i in keep], [Rp[i] for i in keep]
        L = [l for l in L if clip.intersects(l)]
    nd = 0
    if kind == "osm" and not double:
        R, Rp, nd = drop_double(R, Rp)
    s = {"box": os.path.basename(d.rstrip("/")), "ref": kind, "n_ref": len(R), "n_double": nd, "n_out": len(O),
         "n_gap": sum(1 for p in Op if p.get("kind") == "traced gap"), "n_trace": len(T)}
    if not R or not O:
        return s
    bb = box(*np.minimum.reduce([r.bounds for r in R])[:2], *np.maximum.reduce([r.bounds for r in R])[2:])
    best, found, merged, split, omatch, covers = match(R, O)
    s["found"] = float(np.mean(found)); s["merged"] = float(np.mean(merged)); s["split"] = float(np.mean(split))
    s["precise"] = len(omatch) / len(O)
    offs = [offset(R[i], O[j]) for i, (j, iou) in enumerate(best) if iou >= TOL_IOU]
    s["offset"] = float(np.median(offs)) if offs else None
    s["iou"] = float(np.median([b[1] for b in best if b[1] >= TOL_IOU])) if offs else None
    # the raw trace: how much the tracer itself joins (before lots and the LiDAR split)
    if T:
        _, _, tm, _, _, _ = match(R, T)
        s["trace_merged"] = float(np.mean(tm))
    # one roof per lot
    if L:
        hl = [g for g in L if LOT[0] <= g.area <= LOT[1]]
        lt = STRtree(hl)
        def spans(g):
            return sum(1 for i in lt.query(g) if hl[i].intersection(g).area >= max(15, 0.1 * g.area))
        s["out_2lots"] = float(np.mean([spans(o) >= 2 for o in O]))
        rt = STRtree(R); ot = STRtree(O)
        built = [l for l in hl if any(cover(R[i], l) >= 0.4 for i in rt.query(l))]
        n = [sum(1 for j in ot.query(l) if O[j].intersection(l).area >= max(15, 0.1 * O[j].area)) for l in built]
        s["built_lots"] = len(built)
        s["lots_0"] = float(np.mean([k == 0 for k in n])) if n else None
        s["lots_1"] = float(np.mean([k == 1 for k in n])) if n else None
        s["lots_2"] = float(np.mean([k >= 2 for k in n])) if n else None
    # heights against an official reference
    if ref and any(hmax in p for p in Rp):
        dh = [(Op[j].get("h_max") or 0) - float(Rp[i][hmax]) for i, (j, iou) in enumerate(best)
              if iou >= TOL_IOU and Rp[i].get(hmax) not in (None, "") and Op[j].get("h_max")]
        if dh:
            s["h_bias"] = float(np.median(dh)); s["h_within_1m"] = float(np.mean(np.abs(dh) <= 1))
    # site view
    x0, y0, x1, y1 = bb.bounds
    rc = np.array([[r.centroid.x, r.centroid.y] for r in R]); oc = np.array([[o.centroid.x, o.centroid.y] for o in O])
    passed = total = 0
    for tx in np.arange(x0, x1, tile):
        for ty in np.arange(y0, y1, tile):
            k = (rc[:, 0] >= tx) & (rc[:, 0] < tx + tile) & (rc[:, 1] >= ty) & (rc[:, 1] < ty + tile)
            if k.sum() < 5:
                continue
            ko = (oc[:, 0] >= tx) & (oc[:, 0] < tx + tile) & (oc[:, 1] >= ty) & (oc[:, 1] < ty + tile)
            extra = sum(1 for j in np.flatnonzero(ko) if j not in omatch) / max(1, ko.sum())
            total += 1
            if np.mean(np.array(found)[k]) >= 0.85 and np.mean(np.array(merged)[k]) <= 0.05 and extra <= 0.15:
                passed += 1
    s["sites"] = total; s["sites_ok"] = passed / total if total else None
    return s


def pct(v):
    return "-" if v is None else f"{100 * v:.0f}%"


def brief(rows):
    cols = ["box", "ref", "n_ref", "found", "precise", "merged", "trace_merged", "split", "offset", "out_2lots", "lots_1", "sites_ok", "h_bias"]
    print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
    for s in rows:
        v = [s.get("box"), s.get("ref"), s.get("n_ref")] + [pct(s.get(k)) for k in cols[3:8]]
        v += ["-" if s.get("offset") is None else f"{s['offset']:.2f} m"] + [pct(s.get(k)) for k in cols[9:12]]
        v += ["-" if s.get("h_bias") is None else f"{s['h_bias']:+.2f} m"]
        print("| " + " | ".join(str(x) for x in v) + " |")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "brief":
        brief([json.load(open(f)) for f in a[1:]]); sys.exit()
    ref = a[a.index("--ref") + 1] if "--ref" in a else None
    hm = a[a.index("--hmax") + 1] if "--hmax" in a else "HEIGHT_MAX"
    tile = float(a[a.index("--tile") + 1]) if "--tile" in a else 150
    out = a[a.index("--json") + 1] if "--json" in a else None
    bbox = [float(v) for v in a[a.index("--box") + 1:a.index("--box") + 5]] if "--box" in a else None
    s = score_box(a[0], ref, hm, tile, bbox, "--keep-double" in a)
    if out:
        json.dump(s, open(out, "w"), indent=1)
    brief([s])
    print(f"reference: {s['n_ref']} {s['ref']} buildings" + (f" ({s['n_double']} OSM block outlines over their own parts left out)" if s.get("n_double") else "") + "; output {s['n_out']} roofs ({s['n_gap']} traced gaps); raw trace {s['n_trace']} blobs"
          + (f"; {s['built_lots']} built lots: {pct(s.get('lots_0'))} no roof, {pct(s.get('lots_1'))} one, {pct(s.get('lots_2'))} two+" if s.get("built_lots") else ""))
