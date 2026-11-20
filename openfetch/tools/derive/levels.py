#!/usr/bin/env python3
"""Stepped buildings ("levels") for a CBD area from held LiDAR: roofer LoD1.3 on the app's own OpenStreetMap / Microsoft outlines,
then the clean-up rules in levels_clean.py. One run per area, one roofer pass per LiDAR tile. See docs/playbooks/derive-roofs.md.

Usage: python3 tools/derive/levels.py AREA OUTDIR xmin ymin xmax ymax tile.laz [...] [--jobs 4] [--roofer docker|<path to roofer>]

Box in MGA56 metres (EPSG 7856). Outlines: tiles.openfetch.earth Overture copy (the release the app reads), whole buildings by id, with
the mapped height (building or tallest part). Writes:
  OUTDIR/nsw-levels-AREA.json       lon/lat (EPSG 7844), one feature per level of each stepped building, for tools/mirror/build.mjs
  OUTDIR/nsw-levels-AREA.bbox.json  for the catalog (levels-publish.py)
  OUTDIR/roofer/                    roofer's output and the roof cells per tile, reused when the clean-up is rerun on the same outlines
  OUTDIR/levels-mga.json            the same levels unwidened in MGA56, for review drawings only (never published)
  OUTDIR/report.md + stats.json     counts, plain-shape reasons, gates; exit code 1 when a gate FAILs (nothing from the area is used)
Licence (card "Stepped buildings in the roofs pipeline", 20 Nov 2026): no outline is stored. Each level's shape is the LiDAR level,
widened 1 m outward wherever it meets the outline, and keyed by the outline's Overture id (`of_id`); the app cuts it to the outline it
draws, at download (src/core/fetch/fetch-3d.js lidarRoofs). A building that keeps its plain shape has no entry.
"""
import sys, os, re, json, math, gzip, shutil, subprocess, tempfile, urllib.request, argparse, collections
import numpy as np
import laspy
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
import shapely
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import levels_clean as LC

CAT = "https://tiles.openfetch.earth/au/catalog.json"
HDR = {"User-Agent": "openfetch-derive", "Origin": "https://openfetch.earth", "Referer": "https://openfetch.earth/"}
IMAGE = "3dgi/roofer:develop"   # the pilot's image (`latest` does not exist); settings below from the pilot's best run
ROOFER = ["--lod13", "--no-lod22", "--complexity-factor", "0.3", "--plane-detect-min-points", "100", "--plane-detect-epsilon", "0.5",
          "--lod13-step-height", "4", "--id-attribute", "fid"]
WIDEN = 1.0          # m: a level is stored widened this far outward where it meets the outline (no outline edge is stored)
MAX_SHORT = 0.05     # gate: share of level edges under 1 m (pilot after rule 3: 3.6-4.5 %)
TILE_MARGIN = 60.0   # m: points read around a tile so buildings on its edge are whole


def overture_outlines(x0, y0, x1, y1):
    """whole OpenStreetMap / Microsoft buildings touching the box from the app's own Overture copy: (id, polygon, mapped height, src)"""
    from pmtiles.reader import Reader
    import mapbox_vector_tile as mvt
    rel = json.load(urllib.request.urlopen(urllib.request.Request(CAT, headers=HDR)))["latest"]
    url = f"https://tiles.openfetch.earth/au/{rel}/buildings.pmtiles"
    rd = Reader(lambda o, l: urllib.request.urlopen(urllib.request.Request(url, headers={**HDR, "Range": f"bytes={o}-{o+l-1}"})).read())
    T = Transformer.from_crs(4326, 7856, always_xy=True); Ti = Transformer.from_crs(7856, 4326, always_xy=True)
    W, S = Ti.transform(x0, y0); E, N = Ti.transform(x1, y1); z = 14; n = 2**z
    tx = lambda lon: int((lon+180)/360*n); ty = lambda lat: int((1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n)
    pieces, parth = collections.defaultdict(list), {}
    for x in range(tx(W), tx(E)+1):
        for y in range(ty(N), ty(S)+1):
            t = rd.get(z, x, y)
            if not t: continue
            t = gzip.decompress(t) if t[:2] == b"\x1f\x8b" else t
            d = mvt.decode(t); L = d.get("building", {}); ext = L.get("extent", 4096)
            def tr(X, Y, zz=None, x=x, y=y, ext=ext):
                lon = (x+np.asarray(X)/ext)/n*360-180; yy = y+1-np.asarray(Y)/ext
                return T.transform(lon, np.degrees(np.arctan(np.sinh(np.pi*(1-2*yy/n)))))
            for f in d.get("building_part", {}).get("features", []):
                p = f["properties"]; hh = p.get("height") or (p.get("num_floors") and p["num_floors"]*3.5)
                if hh and p.get("building_id"): parth[p["building_id"]] = max(parth.get(p["building_id"], 0), float(hh))
            for f in L.get("features", []):
                try: g = shapely.transform(shapely.make_valid(shape(f["geometry"])), lambda a: np.column_stack(tr(a[:, 0], a[:, 1])))
                except Exception: continue
                pieces[f["properties"].get("id")].append((g.buffer(0), f["properties"]))
    out = []
    for k, v in pieces.items():
        if not k: continue
        g = unary_union([a for a, _ in v]).buffer(0.01, join_style=2).buffer(-0.01, join_style=2)
        if g.geom_type == "MultiPolygon": g = max(g.geoms, key=lambda p: p.area)
        if g.is_empty or g.area < 15: continue
        p = v[0][1]; a = p.get("height") or (p.get("num_floors") and p["num_floors"]*3.5) or 0
        h = max(float(a), parth.get(k, 0)) or None
        src = "osm" if "OpenStreetMap" in str(p.get("sources") or p.get("@source") or "") else "ms"
        g = shapely.make_valid(g.simplify(0.05))   # one self-touching ring makes roofer drop the whole tile (Sydney 3326248, 20 Nov 2026)
        g = max(LC.polys(g), key=lambda p: p.area, default=None)
        if g is not None and g.is_valid and g.area >= 15: out.append((k, g, h, src))
    return rel, out


def tile_box(f):
    with laspy.open(f) as r: h = r.header
    return [float(h.mins[0]), float(h.mins[1]), float(h.maxs[0]), float(h.maxs[1])]


def survey(f):
    m = re.search(r"(20\d\d)", os.path.basename(f).split("_")[0]); return m.group(1) if m else None


def newest(tiles):
    """newest survey per tile footprint (an order can carry older copies of the same tile)"""
    best = {}
    for f, b in tiles:
        k = tuple(round(v, -2) for v in b); y = survey(f) or "0"
        if k not in best or y > best[k][0]: best[k] = (y, f, b)
    return [(f, b) for _, f, b in best.values()]


def roof_points(files, b):
    """building-class (6) points inside box b from the given tiles"""
    A = []
    for f in files:
        with laspy.open(f) as r:
            for ch in r.chunk_iterator(5_000_000):
                m = (ch.x > b[0]) & (ch.x < b[2]) & (ch.y > b[1]) & (ch.y < b[3]) & (ch.classification == 6)
                if m.any(): A.append(np.c_[np.array(ch.x[m]), np.array(ch.y[m]), np.array(ch.z[m])])
    return np.concatenate(A) if A else np.zeros((0, 3))


def run_roofer(roofer, files, outl, b, wd, jobs, od):
    """roofer LoD1.3 on the outlines in `outl` with the tiles in `files` into `od` (kept: a rerun of the clean-up reuses it);
    returns {fid: {ground, pieces [(z, polygon)]}}"""
    if os.path.isdir(od) and any(f.endswith(".city.jsonl") for f in os.listdir(od)) and os.path.exists(od + ".fids.json") and json.load(open(od + ".fids.json")) == [f["properties"]["fid"] for f in json.load(open(outl))["features"]]:
        return {k: v for fn in sorted(os.listdir(od)) if fn.endswith(".city.jsonl") for k, v in read_levels(os.path.join(od, fn)).items()}
    shutil.rmtree(od, ignore_errors=True); os.makedirs(os.path.dirname(od), exist_ok=True)
    bx = [str(int(math.floor(b[0]))), str(int(math.floor(b[1]))), str(int(math.ceil(b[2]))), str(int(math.ceil(b[3])))]
    if roofer == "docker":
        dirs = sorted({os.path.dirname(os.path.abspath(f)) for f in files})
        vols = sum([["-v", f"{d}:/laz{i}:ro"] for i, d in enumerate(dirs)], [])
        inp = [f"/laz{dirs.index(os.path.dirname(os.path.abspath(f)))}/{os.path.basename(f)}" for f in files]
        cmd = ["docker", "run", "--rm", *vols, "-v", f"{wd}:/w", "-v", f"{os.path.dirname(od)}:/o", IMAGE, "-j", str(jobs), *ROOFER, "--box", *bx, *inp, "/w/" + os.path.basename(outl), "/o/" + os.path.basename(od)]
    else:
        cmd = [roofer, "-j", str(jobs), *ROOFER, "--box", *bx, *files, outl, od]
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    bad = re.search(r"feature that is not valid\. WKT: POLYGON \(\(([-\d.]+) ([-\d.]+)", r.stdout + r.stderr)
    if bad and not os.path.isdir(od): return {"invalid": (float(bad.group(1)), float(bad.group(2)))}
    if not os.path.isdir(od): raise SystemExit(f"roofer wrote nothing for {len(json.load(open(outl))['features'])} outlines (box {bx}): stopped, never silently empty")
    json.dump([f["properties"]["fid"] for f in json.load(open(outl))["features"]], open(od + ".fids.json", "w"))
    out = {}
    for fn in sorted(os.listdir(od)):
        if fn.endswith(".city.jsonl"): out.update(read_levels(os.path.join(od, fn)))
    return out


def read_levels(path):
    L = open(path).read().splitlines(); hd = json.loads(L[0]); sc = hd["transform"]["scale"]; tr = hd["transform"]["translate"]; out = {}
    for line in L[1:]:
        o = json.loads(line)
        V = [(v[0]*sc[0]+tr[0], v[1]*sc[1]+tr[1], v[2]*sc[2]+tr[2]) for v in o["vertices"]]
        b = [v for v in o["CityObjects"].values() if v["type"] == "Building"][0]; at = b["attributes"]; pieces = []
        for v in o["CityObjects"].values():
            if v["type"] != "BuildingPart": continue
            for g in v.get("geometry", []):
                if str(g["lod"]) != "1.3": continue
                sem = g["semantics"]
                for si, surf in enumerate(g["boundaries"][0]):
                    if sem["surfaces"][sem["values"][0][si]]["type"] != "RoofSurface": continue
                    rings = [[V[i][:2] for i in r] for r in surf]
                    p = shapely.Polygon(rings[0], rings[1:]).buffer(0)
                    if p.area > 0.01: pieces.append([float(np.mean([V[i][2] for i in surf[0]])), p])
        if pieces: out[int(at["fid"])] = {"ground": at.get("rf_h_ground"), "pieces": pieces}
    return out


def widen(g, F):
    """the level as stored: widened 1 m outward wherever it meets the outline, so cutting it to the outline gives it back exactly"""
    return shapely.make_valid(unary_union([g, g.buffer(WIDEN, join_style=2).difference(F)]))


def main():
    a = argparse.ArgumentParser(); a.add_argument("area"); a.add_argument("out"); a.add_argument("box", nargs=4, type=float); a.add_argument("laz", nargs="+")
    a.add_argument("--jobs", type=int, default=4); a.add_argument("--roofer", default="docker"); o = a.parse_args()
    os.makedirs(o.out, exist_ok=True); B = box(*o.box)
    tiles = newest([(f, tile_box(f)) for f in o.laz]); tiles = [(f, b) for f, b in tiles if box(*b).intersects(B)]
    if len({survey(f) for f, _ in tiles}) > 1: print("note: tiles from more than one survey year:", sorted({survey(f) for f, _ in tiles}))
    rel, O = overture_outlines(*o.box)
    O = [q for q in O if B.contains(q[1].centroid)]
    print(f"{o.area}: {len(O)} outlines (Overture {rel}), {len(tiles)} LiDAR tiles", flush=True)
    levels, T_all, year, skipped = {}, [], {}, 0
    with tempfile.TemporaryDirectory() as wd:
        for f, tb in tiles:
            mine = [i for i, q in enumerate(O) if box(*tb).contains(q[1].centroid)]
            if not mine: continue
            ob = unary_union([O[i][1] for i in mine]).bounds; rb = [ob[0]-TILE_MARGIN, ob[1]-TILE_MARGIN, ob[2]+TILE_MARGIN, ob[3]+TILE_MARGIN]
            files = [g for g, b in tiles if not (b[2] < rb[0] or b[0] > rb[2] or b[3] < rb[1] or b[1] > rb[3])]
            outl = os.path.join(wd, "outlines.geojson")
            for _ in range(50):   # roofer's own simplify can make a valid outline invalid, and then it drops the whole tile: that one keeps its plain shape
                json.dump({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::7856"}},
                           "features": [{"type": "Feature", "properties": {"fid": i, "h": O[i][2]}, "geometry": mapping(O[i][1])} for i in mine]}, open(outl, "w"))
                got = run_roofer(o.roofer, files, outl, rb, wd, o.jobs, os.path.join(os.path.abspath(o.out), "roofer", os.path.basename(f)[:-4]))
                if "invalid" not in got: break
                pt = shapely.Point(*got["invalid"]); drop = [i for i in mine if O[i][1].exterior.distance(pt) < 0.5]
                if not drop: raise SystemExit(f"roofer refused an outline at {got['invalid']} that is not in the list")
                mine = [i for i in mine if i not in drop]; skipped += len(drop)
            else: raise SystemExit("roofer refused more than 50 outlines in one tile: stopped")
            cf = os.path.join(o.out, "roofer", os.path.basename(f)[:-4] + ".cells.npy")
            if not os.path.exists(cf): np.save(cf, LC.surface(roof_points(files, rb)))
            levels.update(got); T_all.append(np.load(cf))
            for i in got: year[i] = survey(f)
            print(f"  {os.path.basename(f)}: {len(mine)} outlines, {len(got)} with LiDAR levels", flush=True)
    T = np.concatenate(T_all) if T_all else np.zeros((0, 3)); T = T[np.unique(np.round(T[:, :2], 1), axis=0, return_index=True)[1]] if len(T) else T
    T = LC.Cells(T)
    pre = {i: LC.prepare(v["pieces"]) for i, v in levels.items()}
    tree = STRtree([O[i][1] for i in pre]); ids = list(pre)
    mga = {}; st = collections.Counter(); why = collections.Counter(); feats = []; short = edges = spikes = leaks = 0
    ll = Transformer.from_crs(7856, 7844, always_xy=True).transform
    for i in pre:
        F = O[i][1]; nb = [ids[j] for j in tree.query(F.buffer(LC.NB_GAP)) if ids[j] != i]
        nbr = [pre[k] for k in nb]
        P, reason = LC.clean(pre[i], F, levels[i]["ground"], O[i][2], nbr, T)
        st["with LiDAR"] += 1
        if reason: why[reason] += 1; continue
        st["stepped"] += 1; s, t = LC.edges(P); short += s; edges += t; spikes += LC.spikes(P); leaks += LC.leaks(P, F, nbr)
        g0 = levels[i]["ground"]; f = LC.fit(P, T, F); mga[O[i][0]] = {"ground": g0, "h": O[i][2], "pieces": [[round(z, 2), g.wkt] for z, g in P]}
        for k, (z, g) in enumerate(sorted(P, key=lambda q: q[0])):
            keep = [q for q in LC.polys(widen(g, F)) if q.intersection(g).area >= 1]   # strips of the 1 m widening cut off from the level go
            for part in (shapely.transform(q, lambda c: np.round(np.column_stack(ll(c[:, 0], c[:, 1])), 7)) for q in keep):
                feats.append({"type": "Feature", "geometry": mapping(part), "properties": {"of_id": O[i][0], "level": k, "roof_top_m": round(z-g0, 2),
                              "ground_m": round(g0, 2), "levels": len(P), "fit": round(f, 2), "lidar_year": year.get(i), "from": "OpenStreetMap" if O[i][3] == "osm" else "Microsoft"}})
    ds = "nsw-levels-" + o.area
    json.dump(mga, open(os.path.join(o.out, "levels-mga.json"), "w"))   # for review drawings only (levels_to_3dm.py), never published: holds no outline but is in MGA
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(o.out, ds + ".json"), "w"))
    lo0, la0 = ll(o.box[0], o.box[1]); lo1, la1 = ll(o.box[2], o.box[3])
    json.dump({"ds": ds, "area": o.area, "bbox": [round(lo0-.002, 4), round(la0-.002, 4), round(lo1+.002, 4), round(la1+.002, 4)], "buildings": st["stepped"],
               "years": sorted({y for y in year.values() if y})}, open(os.path.join(o.out, ds + ".bbox.json"), "w"))
    sp = short / max(1, edges)
    gates = [("No crane-like spikes", spikes == 0, f"{spikes}"), ("No neighbour leaks", leaks == 0, f"{leaks}"),
             ("Square level edges", sp <= MAX_SHORT, f"{100*sp:.1f} % of edges under 1 m (limit {100*MAX_SHORT:.0f} %)")]
    if skipped: why["outline roofer could not read"] += skipped
    stats = {"area": o.area, "overture": rel, "outlines": len(O), **st, "plain": dict(why), "spikes": spikes, "leaks": leaks, "short_pct": round(100*sp, 1),
             "pass": all(g[1] for g in gates), "levels": len(feats)}
    json.dump(stats, open(os.path.join(o.out, "stats.json"), "w"), indent=1)
    rep = [f"# Stepped buildings: {o.area}", "", f"Box {' '.join(str(int(v)) for v in o.box)} (MGA56). Overture {rel}. LiDAR {', '.join(sorted({survey(f) or '?' for f, _ in tiles}))}.", "",
           f"- Outlines in the box: {len(O)}; with LiDAR levels: {st['with LiDAR']}; stepped: {st['stepped']} ({len(feats)} level shapes)",
           "- Plain shape kept: " + (", ".join(f"{v} {k}" for k, v in why.most_common()) or "none"), "", "| Gate | Result | Value |", "| --- | --- | --- |"]
    rep += [f"| {n} | {'PASS' if ok else 'FAIL'} | {v} |" for n, ok, v in gates]
    open(os.path.join(o.out, "report.md"), "w").write("\n".join(rep) + "\n"); print("\n".join(rep))
    sys.exit(0 if stats["pass"] else 1)


if __name__ == "__main__":
    main()
