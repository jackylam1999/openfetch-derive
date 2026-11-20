"""Win back kerb lines dropped whole (card KN23, 20 Nov 2026; Jacky 15:30Z: "for 2D it does not have to be that precise, only odd shapes
fail"; case P-0237). Lines were dropped by batch because they sat 2-3 m inside the road or behind the verge, and by the old bar that was a
fail. Under the 20 Nov bar (about 3 m off is fine in 2D; odd shapes fail) most of those lines are fine, so each dropped line is judged
again, side by side, and only the odd piece is cut. Cuts are made only where a real kerb turns: at a side-street or lane mouth, and each
cut end is finished with a kerb return into that street (quadratic fillet, radius up to 4 m) so no end is left free.

  1. mouths: the line crosses a street centreline (ground level, street or lane class, not along the line's own street): cut the
     mouth (half the crossed street's class width, as kerbgrid.HALF_W, stretched for a slanting crossing) and add a return at each end;
  2. block side = the stretch between two mouths (or a line end). Every metre of it is measured against the cadastre:
       hug  = nearer than HUG_M to a lot (kerb along a wall, a lane or in a yard; Erskineville n18, n09 on the 20 Nov labels);
       far  = farther than FAR_M from any lot (kerb in the carriageway more than about 3 m past a normal footpath, a mall; n15, n17);
     a side is left out whole when it hugs lots (within 0.5 m of a lot line for 25 m or more), sits in the carriageway (over 8 m from any lot and
     within 3 m of a street centreline for over 15 % of it) or is not along a road (over 10 % of it farther than the street's half width + 6 m)
     (blank beats odd). Nothing measured the other way (LiDAR needs a grid, the cadastre is everywhere), so the review does the rest;
  3. a side shorter than MIN_SIDE is left out.
  4. MID-SIDE CUT (card KN24, 20 Nov; case P-0239): a long side left out whole for one local bad stretch (a hugging run, a stretch in the
     carriageway or away from the road) is cut at that stretch instead: the bad metres (padded PAD_M each end, runs closer than JOIN_M
     joined) are removed and each good piece of MIN_SUB m or more is kept. Each mid cut end is finished with a kerb return of MID_R m
     turned toward the nearest street (the kerb leaves the verge the way a driveway or crossover end does); where no street is within
     MID_STREET_M the piece is left out (no free end). A side with more than MAX_CUT_SHARE of it bad stays out whole. Sides that already
     passed (kept) are never touched by this step.
Kept geometry that was never cut is the published line, byte for byte (no smoothing, no moves).

    python3 kerbrestore.py lines.geojson lots_dir roads_dir out.geojson report.json
    python3 kerbrestore.py --selftest
lots_dir and roads_dir hold <x>_<y>.json km-square cells from kerbgrid-run/fetchin.py (MGA56 metres, lots plus 300 m margin).
"""
import glob, gzip, json, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

HALF_W = {1: 9.0, 2: 8.0, 3: 7.0, 4: 6.5, 5: 5.5, 6: 4.5, 7: 3.0}   # as kerbgrid.HALF_W; paths (8-11) are not streets
HUG_M, HUG_RUN, FAR_M, CARRIAGE_M = 0.5, 25.0, 8.0, 3.0   # kerb lead 20 Nov: the first rule left out 24 good sides of 28
AWAY_M, ROAD_SHARE = 6.0, 0.9
BAD_SHARE, MIN_SIDE = 0.15, 15.0
RADIUS, SAME_ST_DEG, MERGE_M = 4.0, 25.0, 6.0
MIN_SUB, PAD_M, JOIN_M, RUN_M = 20.0, 2.0, 10.0, 6.0   # mid-side cut: smallest kept piece, margin round a bad stretch, join gap, shortest far/away stretch
MAX_CUT_SHARE, MID_R, MID_STREET_M = 0.4, 3.0, 30.0
TIER_A_SHARE, TIER_A_RUN = 0.03, 8.0   # tier A: nearly nothing flagged; tier B: kept but with up to BAD_SHARE flagged (reviewed on its own)


def load_streets(roads_dir):
    """[(LineString, functionhierarchy)] of ground-level streets and lanes (fh 1-7), each road segment once."""
    out, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(roads_dir, "*.json"))):
        for f in json.load(open(fn))["features"]:
            p = f.get("properties") or {}
            oid = p.get("OBJECTID", p.get("objectid"))
            if oid in seen or not f.get("geometry") or p.get("roadontype", 1) != 1 or p.get("functionhierarchy") not in HALF_W:
                continue
            seen.add(oid)
            g = shape(f["geometry"])
            out += [(q, p["functionhierarchy"]) for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString" and q.length > 0]
    return out


def load_lots(lots_dir):
    lots, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(lots_dir, "*.json"))):
        for f in json.load(open(fn))["features"]:
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if g.wkb in seen:
                continue
            seen.add(g.wkb)
            lots += [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]
    return lots


def tangent(L, s, h=2.5):
    a, b = np.array(L.interpolate(max(0.0, s - h)).coords[0]), np.array(L.interpolate(min(L.length, s + h)).coords[0])
    v = b - a
    n = np.hypot(*v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def mouths(L, streets, tree):
    """Cut spans [(s0, s1, point, u, hw)] where L crosses a street other than its own: merged within MERGE_M, u = the crossed street's
    direction pointing away from the street L runs beside (None when that street is not found)."""
    found = []
    for j in tree.query(L):
        st, fh = streets[int(j)]
        x = L.intersection(st)
        for p in getattr(x, "geoms", [x]):
            if p.is_empty or p.geom_type != "Point":
                continue
            s = L.project(p)
            t, c = tangent(L, s), tangent(st, st.project(p))
            ang = np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, c))))))
            if ang < SAME_ST_DEG:
                continue                      # a shallow crossing is the line's own street curving, not a mouth
            found.append((s, p, fh, c, ang, int(j)))
    found.sort(key=lambda r: r[0])
    out = []
    for s, p, fh, c, ang, j in found:
        hw = min(HALF_W[fh] / max(np.sin(np.radians(ang)), 0.4), 2.5 * HALF_W[fh])
        if out and s - out[-1][0] < MERGE_M + hw:
            if hw > out[-1][4]:
                out[-1] = (s, out[-1][1], out[-1][2], out[-1][3], hw, out[-1][5])
            continue
        out.append((s, p, fh, c, hw, j))
    res = []
    for s, p, fh, c, hw, j in out:
        near = [k for k in tree.query(p.buffer(HALF_W[1] + 12.0)) if int(k) != j]
        u = None
        if near:
            k = min(near, key=lambda k: streets[int(k)][0].distance(p))
            m = streets[int(k)][0]
            if m.distance(p) < 30.0:
                q = np.array(m.interpolate(m.project(p)).coords[0])
                away = np.array(p.coords[0]) - q
                u = c if float(np.dot(c, away)) >= 0 else -c
        res.append((max(0.0, s - hw), min(L.length, s + hw), p, u, hw))
    return res


def arc(L, s_edge, direction, u, hw, room):
    """Kerb return at a cut end: Q is the mouth edge on the kerb (distance s_edge along L); the kerb leaves Q along direction (+1 or -1
    along L, away from the mouth) and the return turns into the side street along u. Quadratic fillet, radius up to RADIUS (not more
    than the street's half width or the room left on the side); points run from the kerb tangent point to the street."""
    r = min(RADIUS, hw, room)
    q = np.array(L.interpolate(s_edge).coords[0])
    a = np.array(L.interpolate(s_edge + direction * r).coords[0])
    b = q + u * r
    return r, [tuple(map(float, (1 - k) ** 2 * a + 2 * (1 - k) * k * q + k ** 2 * b)) for k in np.linspace(0.0, 1.0, 9)]


def sides_of(L, cuts):
    """[(s0, s1, cut_before, cut_after)] stretches of L between cut spans."""
    out, s = [], 0.0
    prev = None
    for c in cuts:
        if c[0] > s:
            out.append((s, c[0], prev, c))
        s, prev = c[1], c
    if s < L.length:
        out.append((s, L.length, prev, None))
    return out


def profile(L, s0, s1, lots, lt, streets, st_tree):
    """Per metre of [s0, s1]: (S, hug, far, away) boolean arrays (hug is raw: every metre within HUG_M of a lot line)."""
    S = np.arange(s0 + 0.5, s1, 1.0)
    P = shapely.points(np.array([L.interpolate(s).coords[0] for s in S]))
    d = shapely.distance(np.array(lots, dtype=object)[lt.nearest(P)], P) if len(lots) else np.full(len(S), 99.0)
    j = st_tree.nearest(P)
    sg = np.array([g for g, _ in streets], dtype=object)[j]
    dc = shapely.distance(sg, P)
    hw = np.array([HALF_W[fh] for _, fh in streets])[j]
    return S, d < HUG_M, (d > FAR_M) & (dc < CARRIAGE_M), dc > hw + AWAY_M


def longest(mask):
    run = best = 0
    for b in mask:
        run = run + 1 if b else 0
        best = max(best, run)
    return best


def flags(L, s0, s1, lots, lt, streets, st_tree):
    """Per metre judgement of [s0, s1] -> (share flagged, longest flagged stretch, why).
    hug  = within HUG_M of a lot line (cadastre), flagged only as a stretch of HUG_RUN m or more (a wall, lane or yard edge);
    far  = farther than FAR_M from any lot AND within CARRIAGE_M of a street centreline (the kerb is in the carriageway or a mall);
    away = farther than AWAY_M past the nearest street's half width: not along a road at all (a diagonal through trees, a yard);
           a side with over AWAY_SHARE of its length away is left out whole (kerb lead, 20 Nov)."""
    if len(np.arange(s0 + 0.5, s1, 1.0)) < 3:
        return 0.0, 0.0, None
    S, hug, far, away = profile(L, s0, s1, lots, lt, streets, st_tree)
    best = longest(hug)
    why = None
    if best >= HUG_RUN:
        why = "hugs lots"
    elif far.mean() > BAD_SHARE:
        why = "in the carriageway"
    elif away.mean() > 1 - ROAD_SHARE:
        why = "away from the road"
    bad = (hug if best >= HUG_RUN else np.zeros(len(S), bool)) | far | away
    return float(bad.mean()), float(max(best if best >= HUG_RUN else 0, 0)), why


def runs_of(mask):
    """[(i0, i1)] of consecutive True entries (i1 exclusive)."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def bad_spans(L, s0, s1, lots, lt, streets, st_tree):
    """The bad stretches of one side as [(a, b)] metres along L, padded and joined, or None when the side cannot be cut (over MAX_CUT_SHARE bad).
    A hug stretch counts from HUG_RUN m; a far or away stretch from RUN_M m (a single wet metre at a mouth is not a stretch)."""
    S, hug, far, away = profile(L, s0, s1, lots, lt, streets, st_tree)
    bad = np.zeros(len(S), bool)
    for m, need in ((hug, HUG_RUN), (far, RUN_M), (away, RUN_M)):
        for i0, i1 in runs_of(m):
            if i1 - i0 >= need:
                bad[i0:i1] = True
    spans = []
    for i0, i1 in runs_of(bad):
        a, b = max(s0, S[i0] - 0.5 - PAD_M), min(s1, S[i1 - 1] + 0.5 + PAD_M)
        if spans and a - spans[-1][1] < JOIN_M:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    if not spans or sum(b - a for a, b in spans) > MAX_CUT_SHARE * (s1 - s0):
        return None
    return spans


def mid_cut(L, s_edge, streets, st_tree):
    """Pseudo mouth (s, s, point, u, MID_R) for a cut in mid-side: u points from the kerb to the nearest street centreline, or None
    when no street is within MID_STREET_M (the piece then has no honest return and is left out)."""
    p = L.interpolate(s_edge)
    j = int(st_tree.nearest(p))
    g = streets[j][0]
    if g.distance(p) > MID_STREET_M or g.distance(p) < 0.5:
        return None
    q = np.array(g.interpolate(g.project(p)).coords[0])
    v = q - np.array(p.coords[0])
    return (s_edge, s_edge, p, v / np.hypot(*v), MID_R)


def make_piece(L, s0, s1, cb, ca):
    """-> (piece xy, number of returns) for the stretch [s0, s1] of L, each end with its kerb return when given (cb/ca carry u and half width)."""
    room = (s1 - s0) / 3.0
    r0 = r1 = 0.0
    head, tail = [], []
    if cb is not None and cb[3] is not None:
        r0, c = arc(L, s0, +1, cb[3], cb[4], room)
        head = c[::-1]
    if ca is not None and ca[3] is not None:
        r1, c = arc(L, s1, -1, ca[3], ca[4], room)
        tail = c
    lo, hi = (s0 + r0, s1 - r1)
    if s0 == 0 and s1 == L.length and not head and not tail:
        return [tuple(c) for c in L.coords], 0        # never cut: the published line, byte for byte
    body = [(x, y) for x, y in L.coords if lo + 0.01 < L.project(Point(x, y)) < hi - 0.01]
    pa, pb = L.interpolate(lo).coords[0], L.interpolate(hi).coords[0]
    mid = ([] if not head else head[:-1]) + [(pa[0], pa[1])] + body + [(pb[0], pb[1])] + ([] if not tail else tail[1:])
    return mid, int(bool(head)) + int(bool(tail))


def judge(line_xy, streets, st_tree, lots, lt):
    """-> (pieces [list of xy], sides [dict]). Each kept side is one piece; a cut end carries its kerb return. A side left out whole for a
    local stretch is cut at that stretch (step 4 of the module note): its good sub-pieces are kept with "cut_mid" and listed in the side dict
    under "pieces"; sides[i]["why"] stays the whole-side reason so the funnel still counts it."""
    L = LineString(line_xy)
    cuts = mouths(L, streets, st_tree)
    sides, pieces = [], []
    for s0, s1, cb, ca in sides_of(L, cuts):
        share, run, why = flags(L, s0, s1, lots, lt, streets, st_tree)
        n = {"s0": round(s0, 1), "s1": round(s1, 1), "len_m": round(s1 - s0, 1), "flagged": round(share, 2), "longest_flag_m": run}
        if s1 - s0 < MIN_SIDE:
            why = "short side"
        n["why"] = why
        sides.append(n)
        if why in ("hugs lots", "in the carriageway", "away from the road") and s1 - s0 >= 2 * MIN_SUB:
            spans = bad_spans(L, s0, s1, lots, lt, streets, st_tree)
            if spans:
                n["cut_spans_m"] = [[round(a, 1), round(b, 1)] for a, b in spans]
                edges = [s0] + [x for a, b in spans for x in (a, b)] + [s1]
                subs = []
                for k in range(0, len(edges), 2):
                    a, b = edges[k], edges[k + 1]
                    if b - a < MIN_SUB:
                        continue
                    c0 = cb if a == s0 else mid_cut(L, a, streets, st_tree)
                    c1 = ca if b == s1 else mid_cut(L, b, streets, st_tree)
                    if (a != s0 and c0 is None) or (b != s1 and c1 is None):
                        continue
                    if flags(L, a, b, lots, lt, streets, st_tree)[2]:
                        continue
                    q, nr = make_piece(L, a, b, c0, c1)
                    subs.append((q, nr, a, b))
                n["pieces"] = [{"s0": round(a, 1), "s1": round(b, 1), "returns": nr, "q": q} for q, nr, a, b in subs]
        if why:
            continue
        q, nr = make_piece(L, s0, s1, cb, ca)
        n["returns"] = nr
        pieces.append(q)
    return pieces, sides


def selftest():
    """A 10 m collector (fh 4, x axis) with a local street (fh 6) crossing at x=100, lots 4.5 m back along the north side."""
    from shapely.geometry import box
    main = (LineString([(-50, 0), (250, 0)]), 4)
    side = (LineString([(100, -80), (100, 80)]), 6)
    st = [main, side]
    tree = STRtree([s for s, _ in st])
    lots = [box(-50, 11, 90, 40), box(110, 11, 250, 40)]
    lt = STRtree(lots)
    kerb = [(-50 + 0.4 * k, 6.5) for k in range(0, 751)]                 # kerb 6.5 m north of the centreline: lot front at 11 is 4.5 m behind
    piece, sides = judge(kerb, st, tree, lots, lt)
    assert len(sides) == 2 and all(s["why"] is None for s in sides), sides
    assert len(piece) == 2 and all(p[0] != p[-1] for p in piece)
    # the gap between the two pieces is the mouth (about 4.5 m each side of x=100), and each end turns north into the side street
    left, right = piece
    assert 92.0 < left[-1][0] < 100.0 and left[-1][1] > 6.5 + 3.0, left[-3:]
    assert 100.0 < right[0][0] < 108.0 and right[0][1] > 6.5 + 3.0, right[:3]
    # a kerb hugging the lots (0.5 m off them, 10.5 m from the centreline) is left out whole; one in the road 12 m from the lots too
    hug = [(-50 + 0.4 * k, 10.8) for k in range(0, 751)]
    _, sides = judge(hug, st, tree, lots, lt)
    assert [s["why"] for s in sides] == ["hugs lots", "hugs lots"], sides
    far = [(-50 + 0.4 * k, 2.0) for k in range(0, 751)]
    far = [(x, y) for x, y in far]
    _, sides = judge(far, st, tree, [box(-50, 20, 250, 40)], STRtree([box(-50, 20, 250, 40)]))
    assert [s["why"] for s in sides] == ["in the carriageway", "in the carriageway"], sides
    away = [(-50 + 0.4 * k, 25.0) for k in range(0, 751)]               # 25 m from the street, 14 m behind the lot fronts: not along a road
    _, sides = judge(away, st, tree, [box(-50, 40, 250, 60)], STRtree([box(-50, 40, 250, 60)]))
    assert [s["why"] for s in sides] == ["away from the road", "away from the road"], sides
    away = [(-50 + 0.4 * k, 25.0) for k in range(0, 751)]               # 25 m from the street, 14 m behind the lot fronts: not along a road
    _, sides = judge(away, st, tree, [box(-50, 40, 250, 60)], STRtree([box(-50, 40, 250, 60)]))
    assert [s["why"] for s in sides] == ["away from the road", "away from the road"], sides
    # MID-SIDE CUT (KN24): a 300 m kerb with one 60 m stretch where a lot comes right up to it was left out whole by the hug rule; now only
    # the stretch goes, the two good pieces stay, and each mid cut end turns south (toward the street) with a 3 m return
    lots2 = [box(-50, 11, 40, 40), box(40, 6.7, 100, 40), box(100, 11, 250, 40)]
    st2 = [main]
    tree2 = STRtree([g for g, _ in st2])
    piece, sides = judge(kerb[:int(300 / 0.4)], st2, tree2, lots2, STRtree(lots2))
    assert [s["why"] for s in sides] == ["hugs lots"] and len(sides[0]["pieces"]) == 2, sides
    a, b = sides[0]["pieces"]
    assert piece == [] and a["returns"] == 1 and b["returns"] == 1, (piece, sides)
    assert 85.0 < a["s1"] < 90.0 and 150.0 < b["s0"] < 155.0, (a["s1"], b["s0"])
    qa, qb = a["q"], b["q"]
    assert qa[-1][1] < 6.5 - 2.0 and qb[0][1] < 6.5 - 2.0, (qa[-3:], qb[:3])        # the returns run south, toward the street
    assert all(abs(y - 6.5) < 1e-6 for _, y in qa[:-8]) and all(abs(y - 6.5) < 1e-6 for _, y in qb[9:]), "kerb moved"
    assert max(x for x, _ in qa) < 41.0 and min(x for x, _ in qb) > 99.0, "the hugging stretch is still in"
    # a side that is mostly bad stays out whole, and so does a stretch with no street near enough for a return
    _, sides = judge(kerb[:int(300 / 0.4)], st2, tree2, [box(-50, 11, 40, 40), box(40, 6.7, 240, 40)], STRtree([box(-50, 11, 40, 40), box(40, 6.7, 240, 40)]))
    assert not sides[0].get("pieces"), sides
    far_st = [(LineString([(-50, 200), (250, 200)]), 4)]
    _, sides = judge(kerb[:int(300 / 0.4)], far_st, STRtree([g for g, _ in far_st]), lots2, STRtree(lots2))
    assert not sides[0].get("pieces"), sides
    # a shallow crossing (the street curving under the kerb) is not a mouth; an untouched line comes back unchanged
    bend = LineString([(0, 0), (200, 0)])
    assert mouths(LineString([(0, 2), (200, 2)]), [(bend, 4)], STRtree([bend])) == []
    keep, _ = judge(kerb[:200], st, tree, lots, lt)
    assert keep == [[tuple(c) for c in kerb[:200]]], "uncut line moved"
    print("kerbrestore selftest pass")
    return 0


def feat(q, back, props):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(v, 7) for v in back(*c)] for c in q]}, "properties": props}


def main(a):
    from pyproj import Transformer
    to = Transformer.from_crs(4326, 7856, always_xy=True).transform
    back = Transformer.from_crs(7856, 4326, always_xy=True).transform
    op = gzip.open if a[0].endswith(".gz") else open
    F = json.load(op(a[0], "rt"))["features"]
    lots, streets = load_lots(a[1]), load_streets(a[2])
    lt, st_tree = STRtree(lots), STRtree([s for s, _ in streets])
    out, rep, funnel = [], [], {}
    for k, f in enumerate(F):
        xy = [to(*c[:2]) for c in f["geometry"]["coordinates"]]
        pieces, sides = judge(xy, streets, st_tree, lots, lt)
        p = f["properties"]
        area = (p.get("areas") or "").split(",")[0] or "?"
        z = funnel.setdefault(area, {"lines": 0, "km": 0.0, "sides": 0, "sides_kept": 0, "km_kept": 0.0, "why": {}, "returns": 0})
        z["lines"] += 1
        z["km"] += LineString(xy).length / 1000
        z["sides"] += len(sides)
        for s in sides:
            if s["why"]:
                z["why"][s["why"]] = z["why"].get(s["why"], 0.0) + s["len_m"] / 1000
        for q in pieces:
            z["sides_kept"] += 1
            z["km_kept"] += LineString(q).length / 1000
        z["returns"] += sum(s.get("returns", 0) for s in sides)
        kept = [n for n in sides if not n["why"]]
        for i, (q, n) in enumerate(zip(pieces, kept)):
            tier = "A" if n["flagged"] <= TIER_A_SHARE and n["longest_flag_m"] <= TIER_A_RUN else "B"
            out.append(feat(q, back, dict(p, piece=i, of=len(pieces), tier=tier, flagged=n["flagged"], returns=n.get("returns", 0))))
        for n in sides:
            subs = n.pop("pieces", [])
            for j, sp in enumerate(subs):
                z["mid_pieces"] = z.get("mid_pieces", 0) + 1
                z["mid_km"] = z.get("mid_km", 0.0) + LineString(sp["q"]).length / 1000
                z["returns"] += sp["returns"]
                out.append(feat(sp["q"], back, dict(p, piece=j, of=len(subs), tier="C", flagged=n["flagged"], returns=sp["returns"], cut_mid=True,
                                                    side_s0=n["s0"], side_s1=n["s1"], why_whole=n["why"], s0=sp["s0"], s1=sp["s1"])))
                sp.pop("q")
        rep.append({"i": p.get("src_index", k), "area": area, "sides": sides})
    for z in funnel.values():
        z["km"], z["km_kept"], z["mid_km"] = round(z["km"], 1), round(z["km_kept"], 1), round(z.get("mid_km", 0.0), 1)
        z["why"] = {w: round(v, 1) for w, v in z["why"].items()}
    json.dump({"type": "FeatureCollection", "features": out}, open(a[3], "w"))
    json.dump({"check": "openfetch-derive kerbrestore.py", "file": os.path.basename(a[0]), "funnel": funnel, "lines": rep}, open(a[4], "w"))
    print(json.dumps(funnel, indent=0)[:3000])
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
