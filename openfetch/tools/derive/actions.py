#!/usr/bin/env python3
"""GitHub Actions side of batch.py: the same boxes, one runner job per LiDAR tile, LAZ read straight from an ELVIS zip link.

  python3 actions.py plan URL plan.json [--only xmin ymin xmax ymax]   tiles in the zip -> boxes (prints the box ids as JSON)
  python3 actions.py box NAME URL plan.json BOX OUTDIR                 fetch the box's tiles, run pipeline.py, delete the LAZ
  python3 actions.py join NAME plan.json BOXESDIR OUTDIR               joined layer + summary, like batch.py

The zip is read with HTTP range requests (remotezip): the plan reads only each tile's 375-byte header, a box job only its own
tile and same-year neighbours. ELVIS links expire after about 2 days, so run the workflow while the link is live.
Workflow: github/derive-roofs.yml (copied into the public repo jackylam1999/openfetch-derive by github/sync.sh).
"""
import sys, os, json, struct, shutil, subprocess
from remotezip import RemoteZip
from batch import survey, newest, neighbours, summarise

HERE = os.path.dirname(os.path.abspath(__file__))


def header_box(z, name):
    """xmin ymin xmax ymax from the LAS public header (uncompressed in LAZ too), rounded like batch.py."""
    with z.open(name) as f:
        h = f.read(227)
    xmax, xmin, ymax, ymin = struct.unpack("<4d", h[179:211])
    return [round(xmin), round(ymin), round(xmax), round(ymax)]


def plan(url, out, only=None):
    with RemoteZip(url) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".laz")]
        tiles = newest([(n, survey(n), header_box(z, n)) for n in names])
    if only:
        tiles = [t for t in tiles if t[2][0] < only[2] and t[2][2] > only[0] and t[2][1] < only[3] and t[2][3] > only[1]]
    boxes = {f"{b[0]}_{b[1]}": {"tile": f, "survey": s, "bounds": b, "near": neighbours(tiles, (f, s, b))} for f, s, b in tiles}
    json.dump(boxes, open(out, "w"), indent=1)
    print(json.dumps(sorted(boxes)))


def box(name, url, planf, bid, od):
    p = json.load(open(planf))[bid]
    lazd = os.path.join(od, "laz"); os.makedirs(lazd, exist_ok=True)
    files = []
    with RemoteZip(url) as z:
        for n in p["near"]:
            dest = os.path.join(lazd, os.path.basename(n))
            with z.open(n) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst, 16 << 20)
            files.append(dest)
    bd = os.path.join(od, bid)
    r = subprocess.run([sys.executable, os.path.join(HERE, "pipeline.py"), f"{name}-{bid}", *map(str, p["bounds"]), bd, *files])
    shutil.rmtree(lazd)
    sys.exit(r.returncode)


def join(name, planf, boxesd, od):
    pl = json.load(open(planf))
    os.makedirs(od, exist_ok=True)
    tiles = [(p["tile"], p["survey"], p["bounds"]) for p in pl.values()]
    summarise(name, od, tiles, [os.path.join(boxesd, bid) for bid in pl])


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "plan":
        only = [float(v) for v in a[a.index("--only") + 1:a.index("--only") + 5]] if "--only" in a else None
        plan(a[1], a[2], only)
    elif a[0] == "box":
        box(*a[1:6])
    elif a[0] == "join":
        join(*a[1:5])
    else:
        sys.exit(__doc__)
