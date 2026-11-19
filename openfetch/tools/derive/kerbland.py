"""Land-use and private-land guards for a whole kerb version (kerb lead card KN7, 19 Nov 2026, case P-0197; repeat of P-0196).
Every gate before this one asked about roofs, lanes, doubling and corners; none asked what the land is, so a 238 m line ran through
a cemetery and passed. About 1 random close-up in 10 of the published file showed an odd line. Two whole-line tests:
  land: LAND_SHARE (85 %) or more of a line lies LAND_IN m or more inside land that is not a street: NSW land zoning (EPI Land Zoning,
        mapprod3.environment.nsw.gov.au) RE1 public recreation, RE2 private recreation, SP1 special activities (cemetery, defence,
        hospital...) and SP2 infrastructure where the purpose is a school, cemetery, hospital, car park, worship, health, sport.
        A street along a park edge, or a park road zoned as park, has half its length or less inside: not flagged. A park, cemetery
        or school loop lies wholly inside.
  lot:  LOT_SHARE (20 %) or more of a line lies LOT_IN m or more inside a cadastre lot (NSW Land Parcel). A kerb is on public road;
        98 % of the published lines have none of their length inside a lot, so a line with a fifth inside runs through yards, a
        car park or an estate road.
A failing line is dropped whole (a line is kept or left out, never cut). Tried and left out: distance from every street centreline
(61-84 lines at 20-30 m, 4 of 4 looked at were fine rings along streets: case P-0197).
    land_bad(lines, zones) -> {line index: share}     lot_bad(lines, lots) -> {line index: share}
    area_sample(lines, n, seed) -> n review places drawn by area     python3 kerbland.py --selftest
zones, lots: shapely polygons (metres); zone_blocks(properties) picks the zones.
"""
import re, sys
from shapely.geometry import LineString, Polygon, box
from shapely.strtree import STRtree
from shapely.ops import unary_union

LAND_IN, LAND_SHARE, LOT_IN, LOT_SHARE, MIN_LEN = 8.0, 0.85, 3.0, 0.20, 25.0
ZONES = {"RE1", "RE2", "SP1"}
SP2_USE = re.compile(r"educat|school|universit|cemeter|hospital|health|car park|worship|church|golf|sport|stadium|race|defence|park", re.I)
SP2_NOT = re.compile(r"road|rail|motorway|corridor|drain|water|sewer|electric|transmission|bus|tunnel|port|airport", re.I)


def zone_blocks(props):
    """True for a zone a kerb must not run inside: parks, cemeteries, schools, car parks, hospitals; never roads, rail or utilities."""
    sym, use = (props.get("SYM_CODE") or ""), (props.get("PURPOSE") or "")
    if sym in ZONES:
        return not re.search(r"road|rail", use, re.I)
    return sym == "SP2" and bool(SP2_USE.search(use)) and not SP2_NOT.search(use)


def longest(part):
    if part.is_empty:
        return 0.0
    return max((p.length for p in getattr(part, "geoms", [part]) if hasattr(p, "length")), default=0.0)


def share_inside(lines, polys, depth):
    """{index: share of the line's length lying depth m or more inside any of polys} (zero shares left out)."""
    inner = [p.buffer(-depth) for p in polys]
    inner = [p for p in inner if not p.is_empty]
    if not inner:
        return {}
    T = STRtree(inner)
    out = {}
    for i, g in enumerate(lines):
        if g.length < MIN_LEN:
            continue
        near = T.query(g)
        if len(near):
            r = sum(g.intersection(inner[int(k)]).length for k in near) / g.length
            if r > 0:
                out[i] = min(1.0, r)
    return out


def land_bad(lines, zones):
    """{index: share} of lines mostly inside a blocking zone."""
    return {i: round(r, 2) for i, r in share_inside(lines, zones, LAND_IN).items() if r >= LAND_SHARE}


def lot_bad(lines, lots):
    """{index: share} of lines with a fifth or more of their length inside private lots."""
    return {i: round(r, 2) for i, r in share_inside(lines, lots, LOT_IN).items() if r >= LOT_SHARE}


def area_sample(lines, n, seed, cell=500.0, step=50.0):
    """n review places drawn by AREA, not by line index (case P-0196: a draw seeded by line index re-shuffled on every drop, so old lines
    surfaced about 1 in 10 tiles). Each cell x cell square that holds a line gets a fixed rank from a hash of seed and square; each
    50 m spot on a line is ranked inside its square by a hash of the spot. Dropping or adding lines elsewhere never moves a pick.
    Returns [(x, y)] for the n best-ranked squares."""
    import hashlib
    h = lambda s: int(hashlib.md5(s.encode()).hexdigest()[:12], 16)
    best = {}
    for g in lines:
        for k in range(int(g.length // step) + 1):
            p = g.interpolate(min(k * step, g.length))
            sq = (int(p.x // cell), int(p.y // cell))
            r = h(f"{seed}:{sq}:{round(p.x / step)}:{round(p.y / step)}")
            if sq not in best or r < best[sq][0]:
                best[sq] = (r, p.x, p.y)
    squares = sorted(best, key=lambda sq: h(f"{seed}:{sq}"))
    return [(best[sq][1], best[sq][2]) for sq in squares[:n]]


def selftest():
    park = Polygon([(0, 0), (200, 0), (200, 200), (0, 200)])
    edge = LineString([(-3, 10), (-3, 190)])                 # along the park's edge on the street
    half = LineString([(-3, 10), (-3, 190), (100, 190), (100, 30)])
    loop = LineString([(30, 30), (170, 30), (170, 170), (30, 170), (30, 30)])   # a loop inside the park
    through = LineString([(100, 20), (100, 150)])
    short = LineString([(100, 20), (100, 35)])
    got = land_bad([edge, half, loop, through], [park])
    assert list(got) == [2, 3], got
    assert zone_blocks({"SYM_CODE": "RE1"}) and zone_blocks({"SYM_CODE": "SP1", "PURPOSE": "Cemetery"})
    assert zone_blocks({"SYM_CODE": "SP2", "PURPOSE": "Educational Establishment"}) and zone_blocks({"SYM_CODE": "SP2", "PURPOSE": "Car Park"})
    assert not zone_blocks({"SYM_CODE": "SP2", "PURPOSE": "Classified Road"}) and not zone_blocks({"SYM_CODE": "SP2", "PURPOSE": "Railway"})
    assert not zone_blocks({"SYM_CODE": "R2"})
    lot = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
    kerb = LineString([(-3, 10), (-3, 100)])                  # on the street beside the lot
    drive = LineString([(-3, 10), (5, 10), (30, 10), (30, 30)])   # turns into the lot and runs inside it
    assert list(lot_bad([kerb, drive], [lot])) == [1], lot_bad([kerb, drive], [lot])
    many = [LineString([(i * 400, j * 400), (i * 400 + 300, j * 400)]) for i in range(10) for j in range(10)]
    a = area_sample(many, 12, "s")
    assert len(a) == 12 and a == area_sample(many, 12, "s") and a != area_sample(many, 12, "t")
    pts = lambda L: {(round(x), round(y)) for x, y in L}
    left = [g for g in many if g is not many[3]]
    b = area_sample(left, 12, "s")
    assert len(pts(b) & pts(a)) >= 11, "dropping one line moved the sample"   # one line gone: at most one pick changes
    print("kerbland selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    print(__doc__)
