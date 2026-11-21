"""NSW state layers must be read through their multiCRS service (P-0244, 21 Nov 2026).
NSW_Transport_Theme and NSW_Land_Parcel_Property_Theme (no "_multiCRS") store GDA94 numbers and, asked for outSR 7856, return them
unchanged: same road vertex 334022.99, 6250202.18 there and 334023.45, 6250203.63 on the multiCRS layer (0.46 E, 1.44 N). Roads and
lots fetched that way sit 1.45 m SW of true GDA2020 and of the LiDAR. Same mistake as P-0004 (survey marks), P-0005 (DEM) and P-0139 (lots).
Every derive fetcher calls require_multicrs(url) before it asks a NSW state layer for GDA2020 numbers.

    python3 nswsrc.py --selftest
"""
import re, sys

PLAIN = re.compile(r"/rest/services/(NSW_[A-Za-z0-9_]*?)(?<!_multiCRS)/(Feature|Map)Server")


def require_multicrs(url, why_plain=None):
    """Return url when it is safe; raise ValueError for a NSW state theme read without multiCRS (why_plain = reason to allow it, e.g. no geometry used)."""
    if PLAIN.search(url) and not why_plain:
        raise ValueError("NSW layer read without _multiCRS gives GDA94 numbers labelled GDA2020 (1.45 m off): " + url)
    return url


def selftest():
    B = "https://portal.spatial.nsw.gov.au/server/rest/services/"
    for bad in (B + "NSW_Transport_Theme/FeatureServer/5/query", B + "NSW_Land_Parcel_Property_Theme/FeatureServer/8/query",
                B + "NSW_Administrative_Boundaries_Theme/FeatureServer/2/query"):
        try:
            require_multicrs(bad); raise SystemExit("accepted " + bad)
        except ValueError:
            pass
    for good in (B + "NSW_Transport_Theme_multiCRS/FeatureServer/5/query", B + "NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8/query",
                 "https://services1.arcgis.com/x/arcgis/rest/services/Council_Kerbs/FeatureServer/0/query"):
        assert require_multicrs(good) == good
    assert require_multicrs(B + "NSW_Administrative_Boundaries_Theme/FeatureServer/2/query", "suburb names only") 
    print("nswsrc selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
