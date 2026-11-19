# openfetch-derive

Building outlines and roof heights derived from free NSW LiDAR (ELVIS, CC BY 4.0), for OpenFetch.
Copied from the OpenFetch source by `tools/derive/github/sync.sh`; edit there, not here.
Run: Actions > derive-roofs > Run workflow, with an ELVIS zip link. Public repo: never add secrets or keys.

## KN5 lessons (19 Nov 2026, NSW suburbs 11-40 gap kerbs, stopped)
- NSW lots layer 8 on the multiCRS service returned 500s; the plain NSW_Land_Parcel_Property_Theme service works for lots (fetch.py, fetchin2.py), but its corridor layers (fetchcad.py) still need multiCRS.
- NSW imagery /export returned grey for Hurstville/Kogarah; the /tile/ cache works (kerbtop10-run/ringtile.py).
- Outer suburbs without LiDAR ground: 184 rings -> 83 passed two reviewers -> lead G2 5 odd of 40 -> kerbface.py guards + strict review -> 41 -> lead G2 3 odd of 41. One reviewer is not enough, two are not enough; mall/plaza edges, lane-mouth kinks and sides past parked cars cannot be told by script. Wait for LiDAR ground before more outer suburbs.
