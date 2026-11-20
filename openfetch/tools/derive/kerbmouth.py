"""Cut a kerb ring at its lane mouths instead of dropping it (KN21, 20 Nov 2026, kerb lead 4; Jacky 20 Nov 15:30Z "cut, do not drop").
KN18 dropped 244 whole rings (137 km) because a ring crossed a mapped rear lane (kerblane.py): the ring ran straight across the mouth.
A real kerb stops at the mouth and turns into the lane. This does the same, per crossing:
  cut     the ring is removed for HALF_W + R_RETURN either side of the lane centreline (the lane's mapped width is LANE_W per lane);
  return  a quarter-circle of radius R_RETURN joins each cut end to the lane edge, R_RETURN deep into the lane, so no end is free;
  keep    what lies between two mouths is a street side (one line, returns on both ends); a side under MIN_SIDE m is left out.
A crossing where the ring is not straight inside the cut (a corner at the mouth) is refused whole: the return would be a guess.
    cut_ring(ring_xy, lanes) -> {"sides": [{"xy": [...], "ring": [...the street part only], "ring_m": float, "lo": s0, "hi": s1}], "why": [...], "mouths": n}
    lanes = [(LineString, lanecount)] in metres (MGA 56).  python3 kerbmouth.py --selftest
"""
import math
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring

LANE_W, R_RETURN, MIN_SIDE = 3.3, 2.5, 12.0
STRAIGHT_D, RUN_PAST = 0.6, 1.0   # m: the ring may stray this far from its chord from the lane edge to RUN_PAST m past the arc
TOUCH_IN = 1.5      # m: the lane must run this far inside the ring from the crossing, or it only touches


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n else (0.0, 0.0)


def _lane_dir(lane, p, poly):
    """unit vector along the lane at p that points into the ring, or None when the lane does not enter it."""
    t = lane.project(Point(p))
    a, b = lane.interpolate(max(t - 1.0, 0)), lane.interpolate(min(t + 1.0, lane.length))
    d = _unit((b.x - a.x, b.y - a.y))
    for sg in (1, -1):
        q = Point(p[0] + sg * d[0] * TOUCH_IN * 2, p[1] + sg * d[1] * TOUCH_IN * 2)
        if poly.contains(q):
            return (sg * d[0], sg * d[1])
    return None


def crossings(ring, lanes):
    """[(s along the ring, point, into-ring unit vector, half width m)] for every lane crossing that enters the ring."""
    poly = Polygon(ring.coords)
    out = []
    for g, lc in lanes:
        if not g.intersects(poly):
            continue
        x = g.intersection(ring)
        if x.is_empty:
            continue
        for q in getattr(x, "geoms", [x]):
            if q.geom_type != "Point":
                continue
            d = _lane_dir(g, (q.x, q.y), poly)
            if d is None:
                continue
            out.append((ring.project(q), (q.x, q.y), d, LANE_W * max(1, min(lc or 1, 2)) / 2))
    return sorted(out)


def _arc(c, start, end, n=6):
    """points on the circle around c from start to end (the short way), both ends included."""
    a0, a1 = math.atan2(start[1] - c[1], start[0] - c[0]), math.atan2(end[1] - c[1], end[0] - c[0])
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    r = math.hypot(start[0] - c[0], start[1] - c[1])
    return [(c[0] + r * math.cos(a0 + da * i / n), c[1] + r * math.sin(a0 + da * i / n)) for i in range(n + 1)]


def _fillet(ring, s0, p, d, hw, fwd):
    """The kept end of the ring on one side of a mouth: where an arc of radius R_RETURN leaves the ring and meets the lane edge.
    The ring must run straight (within STRAIGHT_D of its chord) from the lane edge to just past the arc. fwd True: the kept stretch lies at
    greater distance than the mouth. Returns {"s": distance of the tangent point on the ring (unrolled), "arc": points from the lane edge
    to the ring (fwd) or from the ring to the lane edge (back)}, or None when the ring bends there or the arc would leave the block."""
    L = ring.length
    sg = 1 if fwd else -1
    ta = _at(ring, s0 + sg * hw)
    tb = _at(ring, s0 + sg * (hw + R_RETURN + RUN_PAST))
    chord = LineString([(ta.x, ta.y), (tb.x, tb.y)])
    if any(chord.distance(_at(ring, s0 + sg * (hw + (R_RETURN + RUN_PAST) * k / 12))) > STRAIGHT_D for k in range(13)):
        return None
    u = _unit((tb.x - ta.x, tb.y - ta.y))
    nf = (-d[1], d[0])
    if nf[0] * u[0] + nf[1] * u[1] < 0:
        nf = (-nf[0], -nf[1])
    b = (p[0] + nf[0] * hw, p[1] + nf[1] * hw)                      # on this side's lane edge line; u points toward the kept stretch
    den = u[0] * d[1] - u[1] * d[0]
    if abs(den) < 1e-9:
        return None
    ux = ((b[0] - ta.x) * d[1] - (b[1] - ta.y) * d[0]) / den
    x = (ta.x + ux * u[0], ta.y + ux * u[1])
    th = math.acos(max(-1.0, min(1.0, u[0] * d[0] + u[1] * d[1])))
    if th < math.radians(35) or th > math.radians(145):
        return None
    tau = R_RETURN / math.tan(th / 2)
    A = (x[0] + tau * u[0], x[1] + tau * u[1])
    pr = ring.project(Point(A))
    if ring.distance(Point(A)) > STRAIGHT_D:
        return None
    delta = (pr - s0 + L / 2) % L - L / 2
    if sg * delta <= 0 or abs(delta) > 30:
        return None
    Q = (x[0] + d[0] * tau, x[1] + d[1] * tau)
    bis = _unit((u[0] + d[0], u[1] + d[1]))
    c = (x[0] + bis[0] * R_RETURN / math.sin(th / 2), x[1] + bis[1] * R_RETURN / math.sin(th / 2))
    arc = _arc(c, Q, A) if fwd else _arc(c, A, Q)
    if not all(Polygon(ring.coords).buffer(0.3).contains(Point(q)) for q in arc):
        return None
    return {"s": s0 + delta, "arc": arc}


def cut_ring(ring_xy, lanes):
    ring = LineString(ring_xy)
    cr = crossings(ring, lanes)
    if not cr:
        return {"sides": [], "why": ["no lane crossing that enters the ring"], "mouths": 0, "whole": True}
    L = ring.length
    iv = []
    for s, p, d, hw in cr:
        fb, ff = _fillet(ring, s, p, d, hw, False), _fillet(ring, s, p, d, hw, True)
        if fb is None or ff is None:
            return {"sides": [], "why": ["a corner at a lane mouth"], "mouths": len(cr), "whole": False}
        iv.append([fb["s"], ff["s"], fb, ff])
    iv.sort(key=lambda v: v[0])
    merged = [list(iv[0])]
    for lo, hi, fb, ff in iv[1:]:
        m = merged[-1]
        if lo <= m[1]:
            if hi > m[1]:
                m[1], m[3] = hi, ff
        else:
            merged.append([lo, hi, fb, ff])
    while len(merged) > 1 and merged[-1][1] - L >= merged[0][0]:
        last = merged.pop()
        if last[0] - L < merged[0][0]:
            merged[0][0], merged[0][2] = last[0] - L, last[2]
        if last[1] - L > merged[0][1]:
            merged[0][1], merged[0][3] = last[1] - L, last[3]
    if merged[0][1] - merged[0][0] >= L:
        return {"sides": [], "why": ["cuts cover the ring"], "mouths": len(cr), "whole": False}
    sides, why = [], []
    for i, (lo, hi, fb, ff) in enumerate(merged):
        nxt = merged[(i + 1) % len(merged)]
        a_s, b_s = hi, nxt[0] + (L if i + 1 == len(merged) else 0)
        n = b_s - a_s
        if n < MIN_SIDE:
            why.append(f"side of {n:.0f} m left out"); continue
        ring_pts = _along(ring, a_s, b_s)
        pts = ff["arc"][:-1] + ring_pts + nxt[2]["arc"][1:]
        sides.append({"xy": pts, "ring": ring_pts, "ring_m": n, "lo": a_s, "hi": b_s})
    return {"sides": sides, "why": why, "mouths": len(cr), "whole": False}


def _at(ring, s):
    return ring.interpolate(s % ring.length)


def _along(ring, a, b):
    """ring points from distance a to b (unrolled, may pass the ring start): the two ends and every original vertex between them,
    so straight sides stay straight segments (the road gate judges segments)."""
    L = ring.length
    co = list(ring.coords)
    d = [0.0]
    for p, q in zip(co[:-1], co[1:]):
        d.append(d[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    out = [(ring.interpolate(a % L).x, ring.interpolate(a % L).y)]
    for k in range(-1, 2):
        for i in range(len(co) - 1):
            if a + 1e-6 < d[i] + k * L < b - 1e-6:
                out.append(co[i])
    pb = ring.interpolate(b % L)
    out.append((pb.x, pb.y))
    return out


def selftest():
    near = cut_ring([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)], [(LineString([(94, -10), (94, 60)]), 1)])
    assert len(near["sides"]) == 1 and near["mouths"] == 1, near                   # a mouth 6 m from a corner: the return still fits
    L_shape = [(0, 0), (100, 0), (100, 40), (60, 40), (60, 100), (0, 100), (0, 0)]
    bend = cut_ring(L_shape, [(LineString([(58, -10), (58, 60)]), 1)])             # a lane whose edge meets the other frontage first
    assert not bend["sides"] or all(Polygon(L_shape).buffer(0.4).contains(Point(p)) for sd in bend["sides"] for p in sd["xy"]), bend
    sq = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
    lane = LineString([(50, -10), (50, 60)])        # one lane entering from the south side
    r = cut_ring(sq, [(lane, 1)])
    assert r["mouths"] == 1 and len(r["sides"]) == 1, r
    s = LineString(r["sides"][0]["xy"])
    q0, q1 = r["sides"][0]["xy"][0], r["sides"][0]["xy"][-1]
    # both ends sit R_RETURN deep in the lane, 1.65 m off its centreline, on opposite sides, so no end crosses the lane
    assert abs(abs(q0[0] - 50) - LANE_W / 2) < 0.05 and abs(abs(q1[0] - 50) - LANE_W / 2) < 0.05 and q0[0] != q1[0], (q0, q1)
    assert abs(q0[1] - R_RETURN) < 0.05 and abs(q1[1] - R_RETURN) < 0.05
    assert not s.crosses(lane) and s.distance(lane) >= LANE_W / 2 - 0.05
    assert abs(s.length - (400 - 2 * (LANE_W / 2 + R_RETURN) + 2 * math.pi / 2 * R_RETURN)) < 6, s.length
    two = cut_ring(sq, [(lane, 1), (LineString([(50, 110), (50, 40)]), 1)])
    assert two["mouths"] == 2 and len(two["sides"]) == 2, two
    assert all(LineString(x["xy"]).distance(l) >= LANE_W / 2 - 0.05 for x in two["sides"] for l in (lane, LineString([(50, 110), (50, 40)])))
    assert cut_ring(sq, [(LineString([(200, 50), (300, 50)]), 1)])["whole"]
    assert cut_ring(sq, [(LineString([(50, 20), (50, 80)]), 1)])["whole"]      # never reaches the ring: not a mouth
    corner = cut_ring(sq, [(LineString([(98, -10), (98, 60)]), 1)])             # mouth in the bend of the corner
    assert corner["why"] == ["a corner at a lane mouth"], corner
    print("kerbmouth selftest pass")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--selftest"]:
        selftest()
