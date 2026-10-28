#!/usr/bin/env python3
"""One box, start to finish, always the same steps and settings, with quality gates. See docs/playbooks/derive-roofs.md.

Usage: python3 tools/derive/pipeline.py NAME xmin ymin xmax ymax OUTDIR tile.laz [...] [--ref reference.geojson]
       [--from community|trace|snap|gapfill]   (reuse saved outputs of earlier steps)

Box in MGA56 metres (EPSG 7856). Steps: community shapes (community.py) -> trace (roofs.py --mode br) -> move
community shapes onto the LiDAR (snap_pilot.py) -> NSW cadastre lots (lots.py) -> add traces only where nobody drew, cut
along lot lines (gapfill.py) -> gates ->
OUTDIR/report.md + OUTDIR/check.png. Exit code 1 when a FAIL gate trips: then nothing from this box is shown or used.
"""
import sys, os, re, json, subprocess
import numpy as np
from shapely.geometry import shape
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
MARGIN = 40  # traced outside the box so buildings on its edge are whole

# Gate limits. Measured 27 Oct 2026: OSM itself has 2.3 % edges under 1 m; the rejected tracer had 49 %;
# the accepted cleanup has 1.5-1.9 % (Tweed, Parramatta). Accuracy floors come from the Tweed known answer.
MAX_SHORT_EDGES = 0.03      # share of outline edges shorter than 1 m
MAX_SHORT2 = 0.06           # share of edges shorter than 2 m: OSM/Microsoft at Greenwich have 5 %, the steppy trace had 13 %
MAX_MEDIAN_VERTS = 16       # corners per traced building (median)
MAX_UNFILLED = 0.08        # share of house-like LiDAR roofs in no outline (2-4 % on all boxes, 27 Oct)
MIN_RECALL, MIN_PRECISION = 0.85, 0.75
MAX_HEIGHT_BIAS = 0.3       # m, median roof height difference when the reference has heights
# Tracing is trusted in a box only where it covers the roofs OSM/Microsoft already have there (28 Oct 2026): thin or
# unclassified LiDAR (Bowral 2014 ~1.5 pts/m2: 15-23 %; Armidale 2015 0.6 pts/m2: 1 %; DCCEEW 2018 in Mosman and the older
# Tweed surveys: 0-25 %) against 79-89 % on 2019-2023 Spatial Services. Such a box adds no traced gaps: heights only.
# The raw trace joins neighbours under trees in every suburb (Greenwich 78 %), so its merge share is shown, not judged;
# Merged gap houses in new estates (Gregory Hills) are cut along the cadastre lot lines in gapfill.py (lots.py).
MIN_TRACE_FIND = 0.6        # share of community roof area the trace covers
HOUSE_LOT = (100, 2000)     # m2, cadastre lots that hold one house; a traced gap may cover at most one of them


def run(cmd, env=None):
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if r.returncode:
        sys.exit(f"step failed: {' '.join(cmd[:3])}\n{r.stderr[-2000:]}")
    return r.stdout + r.stderr


def outlines(fn):
    return [shape(f["geometry"]) for f in json.load(open(fn))["features"]]


def shape_stats(geoms):
    verts, edges = [], []
    for g in geoms:
        for p in (g.geoms if hasattr(g, "geoms") else [g]):
            c = np.asarray(p.exterior.coords); d = np.hypot(*np.diff(c, axis=0).T)
            verts.append(len(d)); edges.extend(d)
    e = np.array(edges) if edges else np.zeros(1)
    return {"n": len(verts), "median_verts": float(np.median(verts)) if verts else 0, "short_edges": float((e < 1.0).mean()),
            "short2": float((e < 2.0).mean())}


def overlaps(geoms):
    t = STRtree(geoms); n = 0
    for i, g in enumerate(geoms):
        for j in t.query(g):
            if j > i and g.intersection(geoms[j]).area > 0.2 * min(g.area, geoms[j].area):
                n += 1
    return n


def capture(files):
    years = sorted({m.group(1) for f in files for m in [re.search(r"(20\d\d)(\d\d)?-", os.path.basename(f)) or re.search(r"(20\d\d)", os.path.basename(f))] if m})
    return ", ".join(years) or "unknown"


def trace_trust(box, traced, comm):
    """Does the trace redraw the community houses inside the box (found area, houses merged)? Too few houses to judge: trusted."""
    from shapely.ops import unary_union
    inb = lambda g: box[0] <= g.centroid.x < box[2] and box[1] <= g.centroid.y < box[3]
    houses = [g for g in comm if inb(g) and g.area >= 40]
    if len(houses) < 30:
        return True, f"{len(houses)} community houses, too few to judge"
    hu, tu = unary_union(houses), unary_union([g for g in traced if inb(g)])
    found = hu.intersection(tu).area / hu.area
    tree = STRtree(houses); merged = 0
    for t in traced:
        inside = [i for i in tree.query(t) if houses[i].intersection(t).area >= 0.5 * houses[i].area]
        if len(inside) >= 2: merged += len(inside)
    share = merged / len(houses)
    ok = found >= MIN_TRACE_FIND
    return ok, (f"trace covers {100*found:.0f} % of community roof area (min {100*MIN_TRACE_FIND:.0f} %), {100*share:.0f} % of {len(houses)} "
                f"houses inside a raw trace holding 2+ (info)" + ("" if ok else ": NO traced gaps, heights only"))


def busiest(box, geoms, size=200):
    """The size-metre square holding the most outlines."""
    cx = np.array([g.centroid.x for g in geoms]); cy = np.array([g.centroid.y for g in geoms])
    best, zb = -1, box
    for x in np.arange(box[0], box[2] - size, 50):
        for y in np.arange(box[1], box[3] - size, 50):
            k = ((cx > x) & (cx < x + size) & (cy > y) & (cy < y + size)).sum()
            if k > best: best, zb = k, (x, y, x + size, y + size)
    return zb


def picture(out, box, layers, title, gaps):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    # zooms: the busiest 200 m square overall, and the 100 m square with the most traced gaps (what Jacky judges)
    views = [(box, title), (busiest(box, [g for _, gs, _ in layers for g in gs]), "zoom 200 m")]
    if gaps:
        views.append((busiest(box, gaps, 100), "zoom 100 m on traced gaps"))
    fig, axs = plt.subplots(1, len(views), figsize=(9 * len(views), 9))
    for ax, (b, t) in zip(axs, views):
        for name, gs, style in layers:
            for g in gs:
                for p in (g.geoms if hasattr(g, "geoms") else [g]):
                    x, y = p.exterior.xy
                    ax.fill(x, y, **style) if style.get("fill") else ax.plot(x, y, color=style["color"], lw=style["lw"])
        ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); ax.set_aspect("equal"); ax.axis("off"); ax.set_title(t)
    plt.savefig(out, dpi=75, bbox_inches="tight"); plt.close(fig)


def main():
    a = sys.argv[1:]
    ref, start = None, "community"
    if "--from" in a:
        i = a.index("--from"); start = a[i + 1]; del a[i:i + 2]
    if "--ref" in a:
        i = a.index("--ref"); ref = a[i + 1]; del a[i:i + 2]
    name = a[0]; box = [float(v) for v in a[1:5]]; od = a[5]; files = a[6:]
    os.makedirs(od, exist_ok=True)
    wide = [box[0] - MARGIN, box[1] - MARGIN, box[2] + MARGIN, box[3] + MARGIN]
    P = lambda f: os.path.join(od, f)
    gates = []  # (level, name, ok, detail)

    # datum: MGA56 GDA2020 or GDA94 (shifted), heights AHD
    gates.append(("FAIL", "heights are AHD", all("AHD" in f for f in files), "file names must carry AHD"))
    gates.append(("FAIL", "one LiDAR capture", "," not in capture(files), f"capture {capture(files)}: pass only the newest survey's tiles"))

    # --from STEP reuses the saved output of every earlier step, so a fix reruns only what it changes
    steps = ["community", "trace", "snap", "gapfill"]
    redo = lambda s, out: steps.index(s) >= steps.index(start) or not os.path.exists(P(out))
    if redo("community", "community.geojson"):
        print(run([sys.executable, os.path.join(HERE, "community.py"), *map(str, wide), P("community.geojson")]).strip())
    if redo("trace", "traced.geojson"):
        print(run([sys.executable, os.path.join(HERE, "roofs.py"), P("traced.geojson"), *files, "--bbox", *map(str, wide), "--mode", "br", "--epsg", "7856"]).strip().splitlines()[-1])
    if redo("snap", "snapped.geojson"):
        print(run([sys.executable, os.path.join(HERE, "snap_pilot.py"), P("community.geojson"), P("snapped.geojson"), *files], {"BOX": " ".join(map(str, wide))}).strip().splitlines()[-1])
    if redo("community", "lots.geojson"):  # lot lines change rarely: fetched once per box, like the community shapes
        print(run([sys.executable, os.path.join(HERE, "lots.py"), *map(str, wide), P("lots.geojson")]).strip())
    gf = run([sys.executable, os.path.join(HERE, "gapfill.py"), P("snapped.geojson"), P("traced.geojson"), P("combined.geojson"),
              P("community.geojson"), P("lots.geojson"), *files]).strip()
    print(gf)

    # keep only outlines whose centre is inside the box, so neighbouring boxes join without doubles
    cj = json.load(open(P("combined.geojson")))
    inbox = lambda g: box[0] <= g.centroid.x < box[2] and box[1] <= g.centroid.y < box[3]
    cj["features"] = [f for f in cj["features"] if inbox(shape(f["geometry"]))]
    json.dump(cj, open(P("combined.geojson"), "w"))
    traced, comb, comm = outlines(P("traced.geojson")), outlines(P("combined.geojson")), outlines(P("community.geojson"))
    ok_trace, why = trace_trust(box, traced, comm)
    gates.append(("INFO", "tracing trusted in this box", ok_trace, why))
    if not ok_trace:  # heights on community shapes only: drop the traced gaps
        cj["features"] = [f for f in cj["features"] if f["properties"].get("kind") != "traced gap"]
        json.dump(cj, open(P("combined.geojson"), "w")); comb = outlines(P("combined.geojson"))
    kinds = [f["properties"].get("kind") for f in json.load(open(P("combined.geojson")))["features"]]
    gaps = [g for g, k in zip(comb, kinds) if k == "traced gap"]
    # gates judge only what we add (traced gaps); community shapes keep their own drawing and are reported for info
    sg, st, sc = shape_stats(gaps), shape_stats(traced), shape_stats([g for g, k in zip(comb, kinds) if k != "traced gap"])
    few = sg["n"] < 10  # a box with few traced gaps (bush, water): judge each outline, not a share
    from clean import short_walls
    each_ok = all(short_walls(g) <= 1 for g in gaps)
    gates.append(("FAIL", "clean traced gap outlines", (each_ok if few else sg["short_edges"] <= MAX_SHORT_EDGES and sg["median_verts"] <= MAX_MEDIAN_VERTS),
                  f"{100*sg['short_edges']:.1f} % edges < 1 m (max {100*MAX_SHORT_EDGES:.0f} %), median {sg['median_verts']:.0f} corners (max {MAX_MEDIAN_VERTS})"))
    gates.append(("FAIL", "no 1-2 m steps in traced gaps", (each_ok if few else sg["short2"] <= MAX_SHORT2),
                  f"{100*sg['short2']:.1f} % edges < 2 m (max {100*MAX_SHORT2:.0f} %; community {100*sc['short2']:.1f} %)"))
    gates.append(("INFO", "whole trace / community shapes", True,
                  f"trace {100*st['short_edges']:.1f} % short, median {st['median_verts']:.0f} corners; community {100*sc['short_edges']:.1f} % short (as drawn by OSM/Microsoft)"))
    # houses the LiDAR shows that end up in no outline (the shape gates cannot see dropped houses). House-like =
    # 40-1000 m2 and fills 60 % of its rectangle; big ragged blobs are tree canopy classed as building and stay out.
    from shapely.ops import unary_union
    allc = unary_union(comb + comm)  # community shapes without a LiDAR fit still show in the app
    houses = [g for g in traced if 40 <= g.area <= 1000 and g.area / g.minimum_rotated_rectangle.area >= 0.6 and inbox(g)]
    n_lost = sum(1 for g in houses if g.intersection(allc).area < 0.3 * g.area); lost = n_lost / max(1, len(houses))
    gates.append(("FAIL", "LiDAR houses left out", not ok_trace or lost <= MAX_UNFILLED or n_lost <= 3, f"{100*lost:.1f} % of {len(houses)} house-like LiDAR roofs in no outline (max {100*MAX_UNFILLED:.0f} %)" + ("" if ok_trace else "; not judged, tracing off")))
    # new estates: one traced gap must not join houses on separate lots (gapfill.py cuts along lot lines and drops the rest)
    lots = [g for g in outlines(P("lots.geojson")) if HOUSE_LOT[0] <= g.area <= HOUSE_LOT[1]]
    lt = STRtree(lots) if lots else None
    span = sum(1 for g in gaps if sum(1 for i in (lt.query(g) if lt else []) if lots[i].intersection(g).area >= max(15, 0.1 * g.area)) >= 2)
    m = re.search(r"\((\d+) lots; (\d+) gaps over 2\+ house lots dropped; (\d+) traces split by the LiDAR\)", gf)
    gates.append(("FAIL", "one house lot per traced gap", span == 0,
                  f"{span} traced gaps cover 2+ house lots ({HOUSE_LOT[0]}-{HOUSE_LOT[1]} m2); "
                  + (f"{m.group(1)} cadastre lots, {m.group(2)} gaps dropped for joining lots, {m.group(3)} traces off-lot split by LiDAR" if m else "")
                  + ("" if lots else "; NO cadastre lots: merged houses not checked")))
    tiny = sum(1 for g in comb if g.area < 10)
    gates.append(("FAIL", "no tiny outlines", tiny == 0, f"{tiny} outlines under 10 m2"))
    nov = overlaps(comb)
    gates.append(("FAIL", "no overlapping outlines", nov == 0, f"{nov} pairs overlap > 20 %"))

    acc = ""
    if ref:
        txt = run([sys.executable, os.path.join(HERE, "compare.py"), P("combined.geojson"), ref, "--bbox", *map(str, box)])
        m = re.search(r"recall ([\d.]+), precision ([\d.]+)", txt); rec, pre = (float(m.group(1)), float(m.group(2))) if m else (0, 0)
        h = re.search(r"h_max difference median ([+-][\d.]+)", txt)
        gates.append(("WARN", "finds the reference buildings", rec >= MIN_RECALL, f"recall {rec:.2f} (min {MIN_RECALL})"))
        gates.append(("WARN", "few extra buildings", pre >= MIN_PRECISION, f"precision {pre:.2f} (min {MIN_PRECISION}); extras are often newer/demolished buildings, see capture date"))
        if h:
            gates.append(("FAIL", "roof heights", abs(float(h.group(1))) <= MAX_HEIGHT_BIAS, f"median {h.group(1)} m (max ±{MAX_HEIGHT_BIAS})"))
        acc = "\n```\n" + txt.strip() + "\n```\n"

    refg = outlines(ref) if ref else comm
    picture(P("check.png"), box, [("reference", refg, {"fill": True, "color": "tab:blue", "alpha": 0.25, "lw": 0}),
                                 ("community moved", outlines(P("snapped.geojson")), {"color": "tab:red", "lw": 0.9}),
                                 ("traced gaps", gaps, {"color": "darkorange", "lw": 1.2})],
            f"{name}: red = OSM/Microsoft moved onto LiDAR, orange = traced gap, blue = {'reference' if ref else 'community today'}", gaps)

    failed = [g for g in gates if g[0] == "FAIL" and not g[2]]
    lines = [f"# {name}", "", f"Box {box} (MGA56). LiDAR capture {capture(files)}. Community shapes {len(comm)}, "
             f"final outlines {len(comb)} ({len(gaps)} traced gaps).", "",
             "| Gate | Level | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {n} | {lvl} | {('info' if ok else 'no') if lvl == 'INFO' else 'pass' if ok else ('FAIL' if lvl == 'FAIL' else 'warn')} | {d} |" for lvl, n, ok, d in gates]
    lines += ["", "**VERDICT: " + ("FAILED, do not show or use. Fix the step, rerun." if failed else "passed. Look at check.png before showing it.") + "**", acc]
    open(P("report.md"), "w").write("\n".join(lines))
    print("\n".join(lines))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
