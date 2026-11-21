"""Wide verges (scenario 13, 21 Nov 2026): the kerb 7-12 m out from the lot front, past kerblot's D_MAX. Kensington and Randwick
streets have grass verges 8-11 m deep; kerblot left them blank (round 3, 19 Nov). One reference is not enough out there: on 2,376
Woollahra street pieces with a council kerb, the first asphalt run in the LiDAR intensity (kerbroad.py) searched 7-12.5 m fired on
53 pieces with no normal width, and 18 of them were 3-8 m off. Cause, seen on the aerial: a concrete parking lane or concrete
carriageway between the real kerb (2-5 m out) and the asphalt reads as not road, and tree canopy over the road. So a wide side is
measured only when two references agree: the asphalt edge (intensity) and a kerb step in the LiDAR ground heights (kerbpcw.py)
at that edge. A concrete parking lane has no kerb step where the asphalt starts, a grass verge has one. No ground grid, no wide side.

    python3 kerbwide.py --selftest
"""
import sys
import numpy as np
import kerbpcw as kpw
import kerbroad as krd

W_MIN, W_MAX = 7.0, 12.0   # m, lot front to kerb (D_MAX of kerblot is 7)
CW_MIN = 2.5               # m, half a carriageway at least between the kerb and the centreline (kerblot.CW_MIN)
AGREE = 1.0                # m between the asphalt-edge kerb and the ground-step kerb
E_WIN, E_SHARE = 1.2, 0.5  # the asphalt edge is the densest 1.2 m of the samples' edges when it holds half the samples that see one:
                           # driveways cross a wide verge, so the middle-half spread test of kerbroad.side_width refused 56 of 75
                           # council-kerbed wide pieces (Parramatta, Canterbury-Bankstown) whose median edge sat on the kerb
PARA = 1.5                 # m: the asphalt edge may move this much along the side (robust trend of the wide edges); more means the
                           # kerb is not parallel to the lot front (a cul-de-sac bulb, a splay), and a ring side drawn parallel to
                           # the lot front would cross the verge (lead blind pack packw13, w25, 21 Nov 2026)
GAP = 1.0                  # m of verge (not road) right before the carriageway when an asphalt footpath comes first
FOOTPATH_ASPHALT = "--no-footpath-asphalt" not in sys.argv
LAST, DRIFT = None, None


def edge_of(row, t, lo):
    """Where the carriageway starts along one profile: the first asphalt run from the lot front, or, when that run starts before the
    wide range (an asphalt footpath at the lot front, Kensington and Randwick), the first run in the wide range that has GAP m of
    grass or concrete just before it (the verge); nan if none."""
    r = krd.runs(row, t)
    if not r:
        return np.nan
    if r[0] >= lo + krd.OFFSET - AGREE or not FOOTPATH_ASPHALT:
        return r[0]
    st = t[1] - t[0]; n = int(round(GAP / st))
    for q in r[1:]:
        k = int(round((q - t[0]) / st))
        if q >= lo + krd.OFFSET - AGREE and k >= n and np.all(row[k - n:k] < 0.5):
            return q
    return r[0]


def edge_width(road, P, N, reach, lo, hi):
    """Kerb distance from the first asphalt run of each sample (kerbroad.runs), densest window; None when too few agree."""
    if not road.covers(P):
        return None
    t = np.arange(0.25, min(reach, hi + krd.OFFSET + krd.RUN) + 0.01, 0.25)
    M = krd.profiles(road, P, N, t)
    global DRIFT
    first = np.asarray([edge_of(row, t, lo) for row in M])
    e = np.sort(first[np.isfinite(first)])
    if len(e) < max(3, krd.SEEN * len(P)):
        return None
    sa = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    m = np.isfinite(first) & (first >= lo + krd.OFFSET - AGREE)   # driveways and asphalt paths before the wide edge are not the kerb
    if m.sum() >= 4:
        i, j = np.triu_indices(int(m.sum()), 1)
        x, y = sa[m], first[m]
        ok = x[j] > x[i]
        DRIFT = abs(float(np.median((y[j] - y[i])[ok] / (x[j] - x[i])[ok]))) * float(x[-1] - x[0])   # Theil-Sen trend over the side
    j = np.searchsorted(e, e + E_WIN, side="right")
    i = int(np.argmax(j - np.arange(len(e))))
    if j[i] - i < E_SHARE * len(e):
        return None
    d = float(np.median(e[i:j[i]])) - krd.OFFSET
    return d if lo <= d <= hi else None


def side_width(ground, road, P, N, reach, lo=W_MIN, hi=W_MAX, c=None):
    """Kerb distance of a wide-verge street side, or None (LAST says why). c: median lot front to street centreline, m."""
    global LAST
    LAST = None
    global DRIFT
    DRIFT = None
    reach = max(reach, hi + krd.OFFSET + krd.RUN)   # kerblot passes half the reserve; the asphalt run past a 7-12 m kerb needs 2.75 m
                                                    # more (5 of 36 blind-OK pieces were lost to it); c guards the far side
    if ground is None or road is None or not ground.covers(P):
        LAST = "no ground"
        return None
    r = edge_width(road, P, N, reach, lo, hi)
    if DRIFT is not None and DRIFT > PARA:
        LAST = "kerb not parallel to the lot front"
        return None
    if r is None:
        LAST = "no asphalt edge"
        return None
    g = kpw.side_width(ground, P, N, reach, max(lo - AGREE, r - AGREE), r + AGREE)
    if g is None:
        LAST = "no kerb step at the asphalt edge"
        return None
    if abs(g - r) > AGREE:
        LAST = "step and edge disagree"
        return None
    w = round((g + r) / 2, 2)
    if c is not None and c < w + CW_MIN:
        LAST = "street centreline too near"
        return None
    LAST = "lidar wide verge"
    return w


class _G:
    """Test ground: lot front at 0, kerb face at k m (15 cm drop), flat either side, along y = 0..100, normals +x."""

    def __init__(self, k):
        self.k = k

    def height(self, X, Y):
        return np.where(X < self.k, 0.0, -0.15).astype(np.float32) - 0.005 * X

    def covers(self, P):
        return True


class _R:
    def __init__(self, e):
        self.e = e

    def at(self, X, Y):
        return (X >= self.e).astype(float)

    def covers(self, P):
        return True


def selftest():
    P = np.c_[np.zeros(40), np.arange(0, 80, 2.0)]; N = np.tile([1.0, 0.0], (40, 1))
    w = side_width(_G(9.0), _R(9.0 + krd.OFFSET), P, N, 45.0)
    assert w is not None and abs(w - 9.0) < 0.5 and LAST == "lidar wide verge", (w, LAST)        # grass verge, kerb 9 m out
    assert side_width(_G(3.5), _R(9.0 + krd.OFFSET), P, N, 45.0) is None                        # concrete parking lane: kerb at 3.5 m
    assert LAST == "no kerb step at the asphalt edge", LAST
    assert side_width(_G(9.0), _R(4.0 + krd.OFFSET), P, N, 45.0) is None
    assert side_width(_G(9.0), _R(9.75), P, N, 45.0, c=10.5) is None and LAST == "street centreline too near"
    assert side_width(None, _R(9.75), P, N, 45.0) is None and LAST == "no ground"
    class _B(_R):                                                                               # kerb turning away: a bulb
        def at(self, X, Y):
            return (X >= self.e + 0.06 * Y).astype(float)
    assert side_width(_G(9.0), _B(8.0 + krd.OFFSET), P, N, 45.0) is None and LAST == "kerb not parallel to the lot front", LAST
    class _F(_R):                                                                               # 2 m asphalt footpath at the lot front,
        def at(self, X, Y):                                                                     # grass verge, kerb at 9 m
            return ((X >= self.e) | ((X >= 0.5) & (X < 3.0))).astype(float)
    w = side_width(_G(9.0), _F(9.0 + krd.OFFSET), P, N, 45.0)
    assert w is not None and abs(w - 9.0) < 0.5, (w, LAST)
    class _D(_R):                                                                               # 3 asphalt driveways of 40 samples
        def at(self, X, Y):
            return ((X >= self.e) | ((Y % 26) < 2.5)).astype(float)
    w = side_width(_G(9.0), _D(9.0 + krd.OFFSET), P, N, 45.0)
    assert w is not None and abs(w - 9.0) < 0.5, (w, LAST)
    print("kerbwide selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
