#!/usr/bin/env python3
"""Run a whole ELVIS order through pipeline.py, one box per LiDAR tile, and join the results.

Usage: python3 tools/derive/batch.py NAME OUTDIR laz_folder [--jobs 3] [--only xmin ymin xmax ymax]
       [--redo fail|all|none] [--from community|trace|snap|gapfill]

Rerunning the same OUTDIR keeps passed boxes and reruns failed or unfinished ones (--redo fail, the default).
After a fix, rerun only what it changes: --redo all --from gapfill reruns gap fill + gates on every box in minutes,
reusing the saved trace and snap. Pilot a new order first with --only on 2-3 boxes (densest, steepest, coast).

Each tile's own extent is one box (keeps memory small: a 2 km tile is about 60 million points). A box gets its tile plus
the neighbouring tiles of the same capture year (for buildings on the edge), so every box passes the one-survey gate. Outlines
are clipped to their box by centre, so the joined layer has no doubles. Writes OUTDIR/NAME-combined.geojson and
OUTDIR/NAME-summary.md (one line per box: verdict, gaps, the gates that failed). Boxes that FAIL are left out of the
joined layer.
"""
import sys, os, re, json, glob, subprocess
from concurrent.futures import ThreadPoolExecutor
import laspy

HERE = os.path.dirname(os.path.abspath(__file__))


def survey(f):
    """Capture year: tiles from the same year's programme (e.g. Sydney May and June 2020) are joined as neighbours."""
    m = re.search(r"(20\d\d)", os.path.basename(f).split("_")[0])
    return m.group(1) if m else os.path.basename(f).split("_")[0]


def newest(tiles):
    """Newest survey per tile footprint only (an order can carry older copies of the same tile). tiles = (file, survey, box)."""
    best = {}
    for f, s, b in tiles:
        k = tuple(round(v, -2) for v in b)
        yr = re.search(r"(20\d\d)", s); yr = yr.group(1) if yr else "0"
        if k not in best or yr > best[k][0]:
            best[k] = (yr, f, s, b)
    return [(f, s, b) for _, f, s, b in best.values()]


def neighbours(tiles, t):
    """The tile itself plus the touching tiles of the same capture year."""
    f, s, b = t
    return [g for g, s2, b2 in tiles if s2 == s and b2[0] <= b[2] + 50 and b2[2] >= b[0] - 50 and b2[1] <= b[3] + 50 and b2[3] >= b[1] - 50]


def summarise(name, od, tiles, dirs):
    """Join passed boxes into OUTDIR/NAME-combined.geojson and write OUTDIR/NAME-summary.md."""
    feats, lines = [], ["| Box | Survey | Verdict | Traced gaps | Failed gates |", "|---|---|---|---|---|"]
    for (f, s, b), bd in zip(tiles, dirs):
        rp = os.path.join(bd, "report.md")
        if not os.path.exists(rp):
            lines.append(f"| {b[0]}_{b[1]} | {s} | ERROR (see {bd}.log) | – | – |"); continue
        txt = open(rp).read()
        ok = "VERDICT: passed" in txt
        fails = [l.split("|")[1].strip() for l in txt.splitlines() if l.startswith("|") and "| FAIL | FAIL |" in l]
        m = re.search(r"\((\d+) traced gaps\)", txt)
        lines.append(f"| {b[0]}_{b[1]} | {s} | {'pass' if ok else 'FAIL'} | {m.group(1) if m else '?'} | {', '.join(fails)} |")
        if ok:
            for ft in json.load(open(os.path.join(bd, "combined.geojson")))["features"]:
                ft["properties"]["survey"] = s; feats.append(ft)
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(od, f"{name}-combined.geojson"), "w"))
    n_gap = sum(1 for ft in feats if ft["properties"].get("kind") == "traced gap")
    summ = [f"# {name}", "", f"{len(tiles)} boxes, {sum('| pass |' in l for l in lines)} passed. Joined layer: {len(feats)} outlines ({n_gap} traced gaps).", ""] + lines
    open(os.path.join(od, f"{name}-summary.md"), "w").write("\n".join(summ))
    print("\n".join(summ))


def main():
    a = sys.argv[1:]
    jobs, only = 3, None
    if "--jobs" in a:
        i = a.index("--jobs"); jobs = int(a[i + 1]); del a[i:i + 2]
    start, redo = None, "fail"
    if "--from" in a:
        i = a.index("--from"); start = a[i + 1]; del a[i:i + 2]
    if "--redo" in a:
        i = a.index("--redo"); redo = a[i + 1]; del a[i:i + 2]
    if "--only" in a:
        i = a.index("--only"); only = [float(v) for v in a[i + 1:i + 5]]; del a[i:i + 5]
    name, od, folder = a[:3]
    os.makedirs(od, exist_ok=True)
    tiles = []
    for f in sorted(glob.glob(os.path.join(folder, "*.laz"))):
        with laspy.open(f) as r:
            h = r.header
            tiles.append((f, survey(f), [round(h.mins[0]), round(h.mins[1]), round(h.maxs[0]), round(h.maxs[1])]))
    tiles = newest(tiles)
    if only:
        tiles = [t for t in tiles if t[2][0] < only[2] and t[2][2] > only[0] and t[2][1] < only[3] and t[2][3] > only[1]]

    def run(t):
        f, s, b = t
        near = neighbours(tiles, t)
        bd = os.path.join(od, f"{b[0]}_{b[1]}")
        rp = os.path.join(bd, "report.md")
        if os.path.exists(rp) and (redo == "none" or (redo == "fail" and "VERDICT: passed" in open(rp).read())):
            return bd
        with open(bd + ".log", "w") as log:
            subprocess.run([sys.executable, os.path.join(HERE, "pipeline.py"), f"{name}-{b[0]}_{b[1]}", *map(str, b), bd, *near, *(["--from", start] if start else [])], stdout=log, stderr=log)
        return bd

    with ThreadPoolExecutor(jobs) as ex:
        dirs = list(ex.map(run, tiles))

    summarise(name, od, tiles, dirs)

if __name__ == "__main__":
    main()
