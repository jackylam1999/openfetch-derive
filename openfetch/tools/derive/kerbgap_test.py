"""Regression tests for kerbgap.py v3/v4 (15 Nov 2026, George St CBD: most blocks blank because LiDAR lost the kerb under
awnings and buses, and rear-lane mouths blanked whole blocks). Run: python3 kerbgap_test.py"""
import numpy as np
import shapely
from shapely.geometry import LineString

import kerbgap as kg


def ring(w, h):
    return LineString([(0, 0), (w, 0), (w, h), (0, h), (0, 0)])


def test_straight_gap_bridged():
    g = ring(60, 200); P = kg.samples(g); xy = shapely.get_coordinates(P)
    seen = ~((xy[:, 1] < 0.1) & (xy[:, 0] > 10) & (xy[:, 0] < 50))
    assert not seen.all()
    assert kg.bridged(P, seen).all(), "a 40 m straight unseen kerb between two seen ends is bridged"


def test_corner_gap_not_bridged_when_strict():
    g = ring(60, 200); P = kg.samples(g); xy = shapely.get_coordinates(P)
    seen = ~((np.hypot(xy[:, 0] - 60, xy[:, 1]) < 15))
    assert not kg.bridged(P, seen).all(), "an unseen stretch round a corner is never bridged as straight"


def test_lane_mouth():
    g = ring(60, 200); P = kg.samples(g)
    lane = LineString([(30, -20), (30, 40)])
    seen = np.ones(len(P), bool)
    assert kg.lane_mouth_ok(g, P, seen, seen, lane), "a lane mouth the kerb was seen past is allowed"
    xy = shapely.get_coordinates(P)
    blind = ~((xy[:, 1] < 0.1) & (np.abs(xy[:, 0] - 30) < 12))
    assert not kg.lane_mouth_ok(g, P, blind, blind, lane), "a lane mouth with no kerb seen near it stays blank"
    street = LineString([(30, -20), (30, 220)])
    assert not kg.lane_mouth_ok(g, P, seen, seen, LineString([(0, 0), (60, 0)])), "a lane along the kerb is not a mouth"
    assert street.intersects(g)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
