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
LAST = None


def edge_width(road, P, N, reach, lo, hi):
    """Kerb distance from the first asphalt run of each sample (kerbroad.runs), densest window; None when too few agree."""
    if not road.covers(P):
        return None
    t = np.arange(0.25, min(reach, hi + krd.OFFSET + krd.RUN) + 0.01, 0.25)
    M = krd.profiles(road, P, N, t)
    e = np.sort([r[0] for row in M if (r := krd.runs(row, t))])
    if len(e) < max(3, krd.SEEN * len(P)):
        return None
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
    if ground is None or road is None or not ground.covers(P):
        LAST = "no ground"
        return None
    r = edge_width(road, P, N, reach, lo, hi)
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
