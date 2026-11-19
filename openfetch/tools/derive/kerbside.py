"""Street-side kerb lines (19 Nov 2026, kerb lead's rule A, thread "Fill NSW top suburb kerbs, round 4"). A block refused as "side faces
no street" is one huge block gluing streets to bush, creek, rail and park: only part of its outline faces a street, so no ring can be
drawn. Rings stay whole or blank, but a street SIDE may be drawn as a line when
  1. it follows one continuous street (same centreline, side of the block) for MIN_RUN m or more,
  2. its kerb was measured (the LiDAR kerb trace on this side, or the LiDAR ground profile) in 90 % of its 20 m chunks,
  3. BOTH ends join a kerb already drawn (within JOIN m, or the run is carried on along its own direction up to REACH m to meet one),
  4. it passes the centreline, roof, doubling and road-corridor gates of the ring.
An end that meets no drawn kerb is an open end: the whole run is left blank. Lines carry side: true so review can sample them.
    lines(comp, S, ctx, kl) -> [(LineString, used)]    S = kerblot.SIDE (outline samples and street hits of the refused block)
"""
import collections
import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

MIN_RUN = 20.0     # m of continuous street side
GAP = 3            # outline samples (6 m) a driveway or tree pit may break a run
CHUNK = 10         # samples (20 m) measured on their own
MEASURED = 0.9
JOIN, REACH = 1.5, 8.0
STATS = collections.Counter()   # why runs were left out (printed by kerblot with --sides)


def runs(CID, street, n, gap=GAP, lane_ids=()):
    """Index lists of maximal stretches of the outline facing one street (cyclic), small breaks bridged."""
    ok = street & (CID >= 0) & ~np.isin(CID, list(lane_ids))
    out = []
    start = next((k for k in range(n) if not ok[k]), None)
    if start is None:
        return []
    order = [(start + k) % n for k in range(n)]
    cur, brk = [], 0
    for k in order:
        if ok[k]:
            cur.append(k); brk = 0
        else:
            brk += 1
            if brk > gap and cur:
                out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [r for r in out if len(r) >= 2]


def end_join(line, drawn, drawn_t):
    """The line with each end joined to a drawn kerb (snapped within JOIN m, or carried on up to REACH m), or None."""
    pts = [np.asarray(c, float) for c in line.coords]
    for end in (0, -1):
        e = pts[end]; a = pts[end + 1] if end == 0 else pts[end - 1]
        t = e - a; t /= max(np.hypot(*t), 1e-9)
        near = [drawn[int(k)] for k in drawn_t.query(Point(e).buffer(JOIN))]
        hit = None
        if any(g.distance(Point(e)) <= JOIN for g in near):
            hit = min((g for g in near), key=lambda g: g.distance(Point(e))).interpolate(min(near, key=lambda g: g.distance(Point(e))).project(Point(e)))
            hit = np.asarray(hit.coords[0])
        else:
            ray = LineString([e, e + t * REACH])
            best = None
            for k in drawn_t.query(ray):
                x = ray.intersection(drawn[int(k)])
                for q in getattr(x, "geoms", [x]):
                    if q.geom_type == "Point":
                        d = Point(e).distance(q)
                        if best is None or d < best[0]:
                            best = (d, np.asarray(q.coords[0]))
            if best is not None:
                hit = best[1]
        if hit is None:
            return None
        pts = [hit] + pts if end == 0 else pts + [hit]
    return LineString(pts)


def lines(comp, S, ctx, kl):
    P, N, W, C, CID, street, rays = (S[k] for k in ("P", "N", "W", "C", "CID", "street", "rays"))
    n = len(P); out = []
    drawn = [g for g in ctx["drawn"]]
    if not drawn:
        return out
    DT = STRtree(drawn)
    st_fh = ctx["st_fh"]
    for r in runs(CID, street, n, GAP, [i for i, fh in enumerate(st_fh) if fh == kl.LANE_FH]):
        STATS['runs'] += 1
        cid = int(CID[r[0]])
        if len(r) * kl.STEP < MIN_RUN:
            STATS['lane or short'] += 1; continue
        idx = np.asarray(r)
        near = kl.first_hit(rays[idx], ctx["raw_t"], ctx["raw"], lo=0.5)
        d_own = np.where((near < C[idx]) & (near >= kl.D_MIN) & (near <= kl.D_MAX), near, np.nan)
        D = np.full(len(idx), np.nan); how = []
        for s in range(0, len(idx), CHUNK):
            sl = slice(s, min(len(idx), s + CHUNK))
            if len(idx[sl]) < 4:
                continue
            own = d_own[sl]
            if np.isfinite(own).sum() >= max(3, 0.5 * len(own)):
                v, h = float(np.nanmedian(own)), "lidar this side"
            elif ctx["ground"] is not None and (pv := kl.kpw.side_width(ctx["ground"], P[idx][sl], N[idx][sl], float(np.nanmedian(W[idx][sl])) / 2)) is not None:
                v, h = pv, kl.kpw.LAST
            else:
                continue
            v = min(v, float(np.nanmedian(W[idx][sl])) / 2 - (kl.CW_OWN if h in kl.OWN else kl.CW_MIN))
            if v < kl.D_MIN:
                continue
            D[sl] = v; how.append(h)
        if np.isfinite(D).mean() < MEASURED:
            STATS['not measured'] += 1; continue
        fill = np.isnan(D)
        if fill.any():
            D[fill] = np.interp(np.flatnonzero(fill), np.flatnonzero(~fill), D[~fill])
        Q = P[idx] + N[idx] * D[:, None]
        k = 2
        Qs = np.vstack([Q[:1], np.asarray([Q[max(0, i - k):i + k + 1].mean(axis=0) for i in range(1, len(Q) - 1)]), Q[-1:]]) if len(Q) > 3 else Q
        body = LineString(Qs).simplify(0.2)
        if body.length < MIN_RUN or not body.is_simple:
            STATS['body'] += 1; continue
        bad = False
        for g, fh in zip(ctx["st"], st_fh):
            if fh != kl.LANE_FH and g.distance(body) < kl.CL_CLEAR:
                bad = True; break
        if bad:
            STATS['centreline'] += 1; continue
        for kk in ctx["bld_t"].query(body):
            part = body.intersection(ctx["bld"][int(kk)].buffer(-kl.BLD_IN))
            if not part.is_empty and max(p.length for p in getattr(part, "geoms", [part])) > kl.BLD_RUN:
                bad = True; break
        if bad:
            STATS['roof'] += 1; continue
        line = end_join(body, drawn, DT)
        if line is None or not line.is_simple:
            STATS['ends'] += 1; continue
        if kl.kc.doubles(body, drawn, DT) > kl.kc.DOUBLE_RUN:
            STATS['doubles'] += 1; continue
        if ctx["cad"] is not None:
            w, _ = kl.kc.judge(ctx["cad"], body)
            if w:
                STATS['corridor'] += 1; continue
        STATS['ok'] += 1
        out.append((line, {"street": cid, "how": sorted(set(how)), "len": round(body.length, 1)}))
    return out
