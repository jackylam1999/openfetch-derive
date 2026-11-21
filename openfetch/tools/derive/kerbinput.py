"""The LiDAR-trace input of kerblot.py must be kerb traces, never a kerbs version OpenFetch made (P-0253, 21 Nov 2026).
kerblot measures footpath widths from its traced_raw input and labels them "lidar" (this side, other side, same street). Scenario 16
ran it with the published version nsw-2026-11-20-h as that input, so OpenFetch's own lot-front rings were measured as if LiDAR had
seen them and lent to other blocks: Arthur St, Surry Hills got a "lidar same street" width of 1.25 m from 97 m of made lines
(none on a LiDAR trace; 16 measures within 1.23-1.34 m, the spread of a constant offset, not of a kerb), and the ring it lent to sat
3-4 m short of the kerb (S16 crops f34, g04). With the kerb traces (nsw-traced-raw.json) Arthur St has no measure and no ring.
A made version is closed rings (nsw-2026-11-20-h: 86 % of its lines); traces are open lines along kerbs (nsw-traced-raw: 2 %).

    python3 kerbinput.py traces.geojson    (prints the closed share; exit 1 when it looks like a made version)
    python3 kerbinput.py --selftest
"""
import gzip
import json
import sys

MADE = 0.25   # share of closed lines above which a "traces" file is a made kerbs version (rings), not traces


def closed_share(fc):
    """Share of the lines in a GeoJSON FeatureCollection (dict) that close on themselves."""
    n = c = 0
    for f in fc.get("features", []):
        g = f.get("geometry") or {}
        for q in ([g.get("coordinates")] if g.get("type") == "LineString" else g.get("coordinates") or [] if g.get("type") == "MultiLineString" else []):
            if q and len(q) > 1:
                n += 1
                c += list(q[0][:2]) == list(q[-1][:2])
    return c / n if n else 0.0


def why_not_traces(path):
    """Reason the file must not be used as kerblot's LiDAR traces, or None."""
    op = gzip.open if str(path).endswith(".gz") else open
    s = closed_share(json.load(op(path, "rt")))
    if s > MADE:
        return (f"{path}: {round(100 * s)} % of its lines are closed rings, so it is a kerbs version OpenFetch made, not LiDAR kerb "
                "traces; widths measured from it would be labelled lidar (P-0253). Pass the traced file (nsw-traced-raw.json).")
    return None


def selftest():
    line = lambda pts: {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": pts}}
    ring = line([[0, 0], [1, 0], [1, 1], [0, 0]])
    trace = line([[0, 0], [1, 0], [2, 0.1]])
    assert closed_share({"features": [ring, ring, ring, trace]}) == 0.75
    assert closed_share({"features": [trace] * 9 + [ring]}) == 0.1
    assert closed_share({"features": []}) == 0.0
    multi = {"type": "Feature", "properties": {}, "geometry": {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[0, 0], [1, 0], [0, 0]]]}}
    assert closed_share({"features": [multi]}) == 0.5
    import os
    import tempfile
    d = tempfile.mkdtemp()
    for name, feats, bad in (("h.json", [ring] * 86 + [trace] * 14, True), ("raw.json", [trace] * 98 + [ring] * 2, False)):
        p = os.path.join(d, name)
        json.dump({"type": "FeatureCollection", "features": feats}, open(p, "w"))
        assert (why_not_traces(p) is not None) == bad, name
    print("kerbinput selftest pass")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        sys.exit(selftest())
    if len(a) == 1:
        w = why_not_traces(a[0])
        print(w or "ok: kerb traces")
        sys.exit(1 if w else 0)
    print(__doc__)
