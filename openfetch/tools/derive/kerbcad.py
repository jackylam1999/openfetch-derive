"""Is a drafted kerb inside the official road reserve? (19 Nov 2026, thread "Make NSW top suburb kerbs usable, round 2").
About half of the lot-front rings kerblot.py drafted were turned down by the close-up reviewers because a side ran beside a rail
line, a park, bush, a tree strip, a car park, a construction site or through back yards. All of those are land that is not road:
the NSW cadastre says so itself (Land Parcel and Property theme: RoadCorridor, RailwayCorridor, WaterFeatureCorridor and
Unidentified, i.e. unlotted land). A kerb is the edge of a carriageway, so it lies inside a road corridor. Each kerb point is
labelled by what it lies in; a ring with a run of points that are not in a road corridor is left blank (whole or blank).

    python3 kerbcad.py cad_dir rings.geojson[,..] out.json        label every ring (for tuning and review sheets)
cad_dir holds kerbtop10-run/fetchcad.py files <layer>_<x>_<y>.json (MGA56 polygons) for layers roadcor, rail, water, unid.
"""
import glob, json, os, sys
import numpy as np
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

TOL = 0.5        # m: a kerb point this close to a road corridor counts as in it (cadastre and kerb lines differ by decimetres)
STEP = 1.0       # m between kerb points
RUN_MAX = 8.0    # m: a longer run of kerb points outside every road corridor is not a kerb (a driveway splay or a corner
                 # truncation the cadastre draws square is shorter than this)
RAIL_CLEAR = 9.0  # m: a kerb this close to a rail or water corridor has no room for a carriageway beside it (19 Nov 2026: five
                  # rings ran 0-8 m from the rail along strips with an unbuilt street centreline; refused on review as "beside rail")
NOT_ROAD = ("rail", "water", "unid")
LABELS = ("road",) + NOT_ROAD + ("other",)


class Cad:
    def __init__(self, d, road_lots=()):
        """road_lots: cadastre lots that carry a street (kerblot.drop_road_lots): in the CBD many streets are lots, not
        road corridors (19 Nov 2026: 2 of 78 reviewed rings ran 180 m along such lots)."""
        self.g, seen = {k: [] for k in ("roadcor",) + NOT_ROAD}, set()
        self.g["roadcor"] += list(road_lots)
        for fn in sorted(glob.glob(os.path.join(d, "*_*_*.json"))):
            k = os.path.basename(fn).split("_")[0]
            if k not in self.g:
                continue
            for f in json.load(open(fn))["features"]:
                oid = (k, f.get("properties", {}).get("OBJECTID"))
                if oid in seen or not f.get("geometry"):
                    continue
                seen.add(oid)
                self.g[k].append(shape(f["geometry"]).buffer(0))
        self.t = {k: STRtree(v) for k, v in self.g.items()}

    def barriers(self, frame):
        """Outlines of rail and water corridors near a frame. They are not cadastre lots, so kerblot read the land across a
        street as ending at the next lot past the rail line: a strip beside the rail with an unbuilt street centreline in it
        passed as a street (19 Nov 2026 close-up review: 4 of 30 refused rings ran beside rail). With these as land across,
        the kerb keeps a carriageway's width from the rail or creek or the side faces no street."""
        out = []
        for k in ("rail", "water"):
            for j in self.t[k].query(frame) if self.g[k] else []:
                g = self.g[k][int(j)]
                out += [q.exterior for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]
        return out

    def corridor_at(self, P):
        """Index of the road corridor (or road lot) each point lies in, -1 for none."""
        out = np.full(len(P), -1)
        if self.g["roadcor"]:
            i, j = self.t["roadcor"].query(shapely.points(P), predicate="intersects")
            out[i] = j
        return out

    def in_corridor(self, pt, k):
        return self.g["roadcor"][k].distance(pt) <= 1.0

    def label(self, P):
        """Label per point (array n x 2): 'road' if within TOL of a road corridor, else the not-road layer it lies in, else 'other'
        (inside a lot or in a gap the cadastre leaves)."""
        pts = shapely.points(P)
        out = np.full(len(P), "other", dtype=object)
        for k in ("water", "unid", "rail"):     # later layers win: rail over unlotted land
            if self.g[k]:
                i, _ = self.t[k].query(pts, predicate="intersects")
                out[np.unique(i)] = k
        if self.g["roadcor"]:
            i, _ = self.t["roadcor"].query(pts, predicate="dwithin", distance=TOL)
            out[np.unique(i)] = "road"
        return out


def ring_points(line):
    return np.asarray([line.interpolate(t).coords[0] for t in np.arange(0, line.length, STEP)])


def longest(b):
    """Longest run of True in a closed ring of flags (number of samples)."""
    b = np.asarray(b, bool)
    if not b.any():
        return 0
    if b.all():
        return len(b)
    b = np.roll(b, -int(np.flatnonzero(~b)[0]))
    best = cur = 0
    for v in b:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def runs(lab):
    """Longest run (m, closed ring) of points that are not road, and the label most common in it."""
    bad = lab != "road"
    if not bad.any():
        return 0.0, None
    if bad.all():
        return len(lab) * STEP, max(set(lab.tolist()), key=lab.tolist().count)
    k = int(np.flatnonzero(~bad)[0])
    b, L = np.roll(bad, -k), np.roll(lab, -k)
    best, cur, start, at = 0, 0, 0, 0
    for i, v in enumerate(b):
        cur = cur + 1 if v else 0
        if cur == 1:
            start = i
        if cur > best:
            best, at = cur, start
    seg = L[at:at + best].tolist()
    return best * STEP, max(set(seg), key=seg.count)


def judge(cad, line):
    """(reason, metres) when a ring runs over RUN_MAX m outside every road corridor or within RAIL_CLEAR m of a rail or water
    corridor, else (None, share in road)."""
    P = ring_points(line)
    lab = cad.label(P)
    near = np.zeros(len(P), bool)
    for k in ("rail", "water"):
        if cad.g[k]:
            i, _ = cad.t[k].query(shapely.points(P), predicate="dwithin", distance=RAIL_CLEAR)
            near[np.unique(i)] = True
    if longest(near) * STEP > RUN_MAX:
        return "beside a rail line or creek", float(longest(near) * STEP)
    m, what = runs(lab)
    if m > RUN_MAX:
        return {"rail": "beside a rail corridor", "water": "beside a creek or water corridor",
                "unid": "beside unlotted land (park, bush, rail or crown land)"}.get(what, "outside the road reserve (yards, car park, private land)"), m
    return None, float((lab == "road").mean())


def main(a):
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    cad = Cad(a[0])
    out = {}
    for fn in a[1].split(","):
        for f in json.load(open(fn))["features"]:
            c = f["geometry"]["coordinates"]
            line = shapely.LineString([to(*p[:2]) for p in c])
            lab = cad.label(ring_points(line))
            m, what = runs(lab)
            pid = f["properties"].get("id") or f"{os.path.basename(fn)}:{len(out)}"
            out[pid] = {"run_m": m, "run_in": what, "road": round(float((lab == "road").mean()), 3),
                        **{k: int((lab == k).sum()) for k in LABELS[1:]}, "len_m": round(line.length, 1)}
    json.dump(out, open(a[2], "w"), indent=0)
    r = np.asarray([v["run_m"] for v in out.values()])
    print(len(out), "rings; longest non-road run m: p50", np.percentile(r, 50), "p90", np.percentile(r, 90), "over", RUN_MAX, int((r > RUN_MAX).sum()))


if __name__ == "__main__":
    main(sys.argv[1:])
