"""Which datum a LiDAR file is really in (P-0244, 21 Nov 2026). Grid makers (kerbroad.grid, kerbpcw.make_grid) call check_frame first.

NSW Spatial Services point clouds are headed GDA2020 / MGA (EPSG 7854-7856) or GDA94 / MGA (28354-28356). The header can be wrong:
the 2019 surveys and Sydney202004 are headed GDA94, but measured against the state road centrelines (multiCRS layer, true GDA2020)
the 28 such tiles sit in the SAME frame as the 15 GDA2020-headed tiles (asphalt centre vs centreline, least squares over 1,000-4,000
samples per tile: median offset 0.50 E / 1.46 N vs 0.71 / 1.41 for the GDA2020 tiles). Moving them by the GDA94 to GDA2020 shift
(+0.48, +1.42 m) would have put them 1.45 m off, so the declared datum alone is never trusted either way (AGENTS: never trust a
declared CRS). A file headed GDA94 is gridded only when its survey is in FRAME_CHECKED below; any other survey is refused until
`kerbframe.py` (the same fit) has measured it. Heights are AHD in both datums and are not touched.

    python3 lascrs.py --selftest
"""
import os, re, sys

GDA2020 = {7854: 54, 7855: 55, 7856: 56}
GDA94 = {28354: 54, 28355: 55, 28356: 56}
# surveys headed GDA94 that were measured to be in the GDA2020 frame (21 Nov 2026, kerbframe fit on 28 tiles); name = file name up to the tile id
FRAME_CHECKED = {"Sydney201906": "28 GDA94-headed tiles with these surveys: offset to road centrelines equals the GDA2020 tiles'",
                 "Penrith201906": "same", "Sydney202004": "same"}
NOT_CHECKED = "Sydney201304 (one tile, 3326260, sparse ground)"


def epsg_of_crs(crs):
    if crs is None:
        return None
    e = crs.to_epsg()
    if e:
        return e
    for sub in getattr(crs, "sub_crs_list", []) or []:
        e = sub.to_epsg()
        if e in GDA2020 or e in GDA94:
            return e
    return None


def header_epsg(header):
    try:
        return epsg_of_crs(header.parse_crs())
    except Exception:
        return None


def survey_of(path):
    m = re.match(r"([A-Za-z]+\d{6})", os.path.basename(str(path)))
    return m.group(1) if m else ""


def check_frame(header, path):
    """EPSG the file declares; raises ValueError for a file with no datum, an unknown datum, or a GDA94 header on a survey nobody measured."""
    e = header_epsg(header)
    if e is None:
        raise ValueError("LiDAR file declares no horizontal datum: not gridded")
    if e in GDA2020:
        return e
    if e in GDA94:
        s = survey_of(path)
        if s in FRAME_CHECKED:
            return e
        raise ValueError(f"{os.path.basename(str(path))} is headed GDA94 and survey '{s}' has not been measured: run kerbframe.py on it first "
                         f"(2019 surveys were found to be in the GDA2020 frame despite the header, P-0244), then add it to FRAME_CHECKED")
    raise ValueError(f"unknown LiDAR datum EPSG {e}")


def grid_selftest():
    import tempfile
    import numpy as np
    import laspy
    from pyproj import CRS
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kerbpcw, kerbroad
    E, N = 334500.25, 6250500.25
    def las(d, name, epsg):
        hdr = laspy.LasHeader(point_format=3, version="1.2")
        if epsg:
            hdr.add_crs(CRS.from_epsg(epsg))
        hdr.offsets = (334000.0, 6250000.0, 0.0); hdr.scales = (0.01, 0.01, 0.01)
        a = laspy.LasData(hdr)
        a.x, a.y, a.z = np.array([E]), np.array([N]), np.array([10.0]); a.classification = np.array([2]); a.intensity = np.array([7])
        p = os.path.join(d, name); a.write(p); return p
    with tempfile.TemporaryDirectory() as d:
        ok = las(d, "Sydney202005-x_3346250_56.las", 7856)
        checked = las(d, "Sydney201906-x_3346250_56.las", 28356)
        new = las(d, "Penrith203001-x_3346250_56.las", 28356)
        none = las(d, "none_3346250_56.las", None)
        for p in (ok, checked):                          # both land at the file's own coordinates, nothing moved
            o = os.path.join(d, "r" + os.path.basename(p)); os.makedirs(o)
            kerbroad.grid([p], o)
            g = np.load(os.path.join(o, "334_6250.npz"))["i"]; j, i = np.argwhere(g != 255)[0]
            assert (334000 + i * 0.5) <= E < (334000 + i * 0.5 + 0.5) and (6250000 + j * 0.5) <= N < (6250000 + j * 0.5 + 0.5), (p, i, j)
            o2 = os.path.join(d, "p" + os.path.basename(p)); os.makedirs(o2); kerbpcw.make_grid([p], 334, 6250, o2)
        for p in (new, none):                            # an unmeasured GDA94 survey and a file with no datum are refused
            try:
                kerbroad.grid([p], d)
                raise SystemExit("gridded " + p)
            except ValueError:
                pass


def selftest():
    class H:
        def __init__(self, e): self.e = e
        def parse_crs(self):
            e = self.e
            class C:
                def to_epsg(self): return e
            return C() if e else None
    assert check_frame(H(7856), "Sydney202005-a_1_56.laz") == 7856
    assert check_frame(H(28356), "Sydney201906-a_1_56.laz") == 28356        # measured, kept as it is
    for e, n in ((28356, "Sydney209912-a.laz"), (None, "Sydney202005-a.laz"), (4326, "x.laz")):
        try:
            check_frame(H(e), n); raise SystemExit(f"accepted {e} {n}")
        except ValueError:
            pass
    assert survey_of("/a/b/Penrith201906-LID1-C3-AHD_2866260_56_0002_0002.laz") == "Penrith201906"
    try:
        import laspy, kerbroad
    except ImportError:
        print("lascrs: laspy / kerbroad not here, grid files not tested")
    else:
        grid_selftest()
    print("lascrs selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
