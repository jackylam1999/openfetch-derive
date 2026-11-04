#!/usr/bin/env python3
"""Kerb tracing pilot (4 Nov 2026, before an iCurb-style learned tracer): walk on from each end of a drawn kerb line, one STEP m at a
time, turning at most TURN degrees per step, to wherever the evidence is strongest. Evidence at a point = max(photo P, LiDAR step / FULL),
so where the model is blind the ground step can carry the trace. Stop after MISS weak steps in a row, after MAXLEN m, or on reaching
another drawn line (a bridged gap). No training: if this does not beat the base, a learned tracer has to see more than P and the step.

Usage (KERB_CFG as the scored model): python kerbtrace.py kp_dir long_dir thresh
  kp_dir holds <box>_derived_<thresh>.geojson (the round's lines), long_dir pc-16-1's <box>_P.npy (kerblong.py).
  Prints found / precise / F1 / added km per box for each variant, then the scenario score as the rounds report it.
"""
import sys, os, json
import numpy as np
from scipy import ndimage
import kerblearn as kl
import compare_kerbs as ck
import kerbstep as ks
from shapely.geometry import LineString, Point, box as sbox
from shapely.strtree import STRtree
from affine import Affine

STEP, TURN, MISS, MAXLEN, MINLEN, FULL, JOIN = 1.0, 15, 3, 80.0, 5.0, 0.08, 1.5  # m, degrees, steps, m, m, m step = evidence 1, m
VARIANTS = [("e0.3", 0.3, False), ("e0.5", 0.5, False), ("e0.3 bridge", 0.3, True), ("e0.5 bridge", 0.5, True)]


class Ev:
    def __init__(self, P, trP, up, trU):
        self.P, self.iP = ndimage.maximum_filter(P, 3), ~trP
        self.U, self.iU = (ndimage.maximum_filter(up, 3), ~trU) if up is not None else (None, None)

    def at(self, xy):
        def get(G, inv):
            c, r = inv * (xy[:, 0], xy[:, 1]); r, c = r.astype(int), c.astype(int)
            ok = (r >= 0) & (c >= 0) & (r < G.shape[0]) & (c < G.shape[1])
            v = np.zeros(len(xy), np.float32); v[ok] = G[r[ok], c[ok]]; return v
        e = get(self.P, self.iP)
        return np.maximum(e, np.clip(get(self.U, self.iU) / FULL, 0, 1)) if self.U is not None else e


def walk(p, h, ev, at, tree, D, own, clip):
    """From point p heading h (radians): returns (points, reached another line)."""
    pts, weak, angs = [p], 0, np.radians(np.arange(-TURN, TURN + 1, 5))
    for _ in range(int(MAXLEN / STEP)):
        hs = h + angs; q = np.column_stack([pts[-1][0] + STEP * np.cos(hs), pts[-1][1] + STEP * np.sin(hs)])
        mid = (q + pts[-1]) / 2; s = (ev.at(q) + ev.at(mid)) / 2; k = int(np.argmax(s))
        if s[k] >= at:
            weak = 0; h = hs[k]
        else:  # weak: go straight on, give up after MISS steps
            weak += 1; k = len(angs) // 2
            if weak > MISS:
                return pts[:-MISS] if len(pts) > MISS else [p], False
        pts.append(q[k])
        if not clip.contains(Point(q[k])):
            return pts, False
        for j in tree.query(Point(q[k]).buffer(JOIN)):
            if j != own and D[j].distance(Point(q[k])) <= JOIN:
                return pts, True
    return pts, False


def trace(D, ev, at, bridge, clip, hits=None):
    tree = STRtree(D); out = []
    for i, l in enumerate(D):
        if l.length < MINLEN:
            continue
        for a, b in ((l.coords[1], l.coords[0]), (l.coords[-2], l.coords[-1])):
            # heading from the last 2 m of the line
            t = l.project(Point(b)); c = l.interpolate(max(t - 2, 0) if t > 0 else min(2, l.length))
            h = np.arctan2(b[1] - c.y, b[0] - c.x)
            pts, hit = walk(np.array(b, float), h, ev, at, tree, D, i, clip)
            if len(pts) * STEP >= MINLEN and (hit or not bridge):
                out.append(LineString(pts))
                if hits is not None:
                    hits.append(hit)
    return out


FEATS = ("length", "Pmean", "Pmin", "Pweak", "step", "stepshare", "straight", "headdiff", "lotd", "cld", "far", "hit", "other",
         "offagree", "road")


def features(src, nm, D, R, new, hits, ev, clip):
    """One row per trace for the keep/drop filter (kerbs-direction.md step 3) and its label: >= 70% of it within 1 m of council kerb."""
    import shapely
    from kerbmiss import flat
    lots = flat(f"{src}/{nm}_lots.geojson", "Polygon")[0]; roads, rp = flat(f"{src}/{nm}_roads.geojson", "LineString")
    RA, LA = np.asarray(roads, object), np.asarray(lots, object); rt, lt = STRtree(roads), STRtree(lots) if lots else None
    U = shapely.union_all(RA); shapely.prepare(U); dt = STRtree(D)
    ds = ck.samples(D, 2.0); dsp = shapely.points(ds); dri = rt.nearest(dsp); dcl = shapely.distance(dsp, RA[dri])
    off = {}
    for i, d in zip(dri, dcl):
        if d <= 15:
            off.setdefault(i, []).append(d)
    off = {k: np.median(v) for k, v in off.items()}
    rows, ys, lens = [], [], []
    for l, hit in zip(new, hits):
        xy = ck.samples([l], 0.5)
        if not len(xy):
            continue
        e = ev.at(xy); p = ev.P[tuple(np.clip(np.array((ev.iP * (xy[:, 0], xy[:, 1]))[::-1]).astype(int), 0, ev.P.shape[0] - 1))]
        st = ev.U[tuple(np.clip(np.array((ev.iU * (xy[:, 0], xy[:, 1]))[::-1]).astype(int), 0, ev.U.shape[0] - 1))] if ev.U is not None else np.zeros(len(xy))
        mid = l.interpolate(0.5, normalized=True); ri = rt.nearest(mid); rd = RA[ri]
        t = rd.project(mid); a, b = rd.interpolate(max(t - 2, 0)), rd.interpolate(min(t + 2, rd.length))
        c0, c1 = l.coords[0], l.coords[-1]
        h1, h2 = np.arctan2(c1[1] - c0[1], c1[0] - c0[0]), np.arctan2(b.y - a.y, b.x - a.x)
        hd = abs(((h1 - h2) + np.pi / 2) % np.pi - np.pi / 2)
        cld = rd.distance(mid); li = lt.nearest(mid) if lt is not None else None
        lotd = LA[li].distance(mid) if li is not None else 99.0
        far = float(li is not None and lotd > 1 and U.intersects(shapely.shortest_line(mid, LA[li])))
        cp = rd.interpolate(t); X = Point(2 * cp.x - mid.x, 2 * cp.y - mid.y)
        qd = dt.query(X.buffer(1.5)); other = float(min(D[j].distance(X) for j in qd) <= 1.5) if len(qd) else 0.0
        h = rp[ri].get("functionhierarchy") or 9
        rows.append([l.length, p.mean(), p.min(), (e < 0.3).mean(), st.mean(), (st >= 0.04).mean(),
                     Point(c0).distance(Point(c1)) / max(l.length, 1e-6), hd, lotd, cld, far, float(hit), other,
                     abs(cld - off[ri]) if ri in off else 9.0, h])
        ys.append(float((ck.dist(xy, R) <= 1).mean() >= 0.7) if R else 0.0); lens.append(l.length)
    return np.array(rows, np.float32).reshape(-1, len(FEATS)), np.array(ys), np.array(lens)


def filt(src, ld, th, at=0.3):
    """Leave-one-box-out keep/drop filter on the e0.3 traces of the 8 NSW boxes. The training boxes are not used: their P comes from
    a model trained on them (near-perfect there), so their traces would not look like real ones. Cut chosen on the check boxes."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{ld}/{b[0]}_P.npy") and os.path.exists(f"{src}/{b[0]}_dem.npy")]
    per = {}
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        trP = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        D, R = ck.lines(f"{src}/{nm}_derived_{th}.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        trU, up = ks.grids(src, nm, D)[:2]; ev = Ev(P, trP, up, trU); hits = []
        new = trace(D, ev, at, False, clip, hits)
        X, y, L = features(src, nm, D, R, new, hits, ev, clip)
        per[nm] = (D, R, new, X, y, L)
        print(nm, "traces", len(y), "good share by length", round(float((y * L).sum() / max(L.sum(), 1)), 2), flush=True)
    prob = {}
    for nm in boxes:
        Xt = np.concatenate([per[o][3] for o in boxes if o != nm]); yt = np.concatenate([per[o][4] for o in boxes if o != nm])
        wt = np.concatenate([per[o][5] for o in boxes if o != nm])
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
        clf.fit(Xt, yt, sample_weight=wt); prob[nm] = clf.predict_proba(per[nm][3])[:, 1] if len(per[nm][3]) else np.zeros(0)
    hold = [n for n in boxes if n in dict(h[:2] for h in kl.HOLD)]; val = [n for n in boxes if n not in hold]
    res = {}
    for cut in (None, 0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        res[cut] = {}
        for nm in boxes:
            D, R, new, X, y, L = per[nm]
            keep = [l for l, q in zip(new, prob[nm]) if cut is not None and q >= cut]
            kl_ = sum(l.length for l in keep); good = sum(l.length for l, q, g in zip(new, prob[nm], y) if cut is not None and q >= cut and g)
            res[cut][nm] = (*ks.rate(D + keep, R), kl_ / 1000, good / max(kl_, 1e-6))
        by = {}
        for nm in boxes:
            by.setdefault(kl.SCEN[nm], []).append(nm)
        sc = float(np.mean([np.mean([ks.f1(res[cut][n]) for n in v]) for v in by.values()]))
        vs = float(np.mean([ks.f1(res[cut][n]) for n in val]))
        add = sum(res[cut][n][2] for n in boxes); prec = sum(res[cut][n][2] * res[cut][n][3] for n in boxes) / max(add, 1e-6)
        print("cut", cut, "scenario", round(sc, 3), "check-box mean", round(vs, 3), "worst held-out", round(min(ks.f1(res[cut][n]) for n in hold), 3),
              "added km", round(add, 1), "kept-trace precision", round(prec, 2), "olympicpark found", round(res[cut]["olympicpark"][0], 3), flush=True)
    for nm in boxes:
        print(nm, {str(c): (round(v[nm][0], 3), round(v[nm][1], 3), round(ks.f1(v[nm]), 3), round(v[nm][2], 2)) for c, v in res.items()})
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
    clf.fit(np.concatenate([per[o][3] for o in boxes]), np.concatenate([per[o][4] for o in boxes]), sample_weight=np.concatenate([per[o][5] for o in boxes]))
    import pickle
    pickle.dump(clf, open(f"{ld}/tracefilter.pkl", "wb"))


def main():
    src, ld, th = sys.argv[1:4]; res = {}
    boxes = [b[0] for b in kl.VAL + kl.HOLD if os.path.exists(f"{ld}/{b[0]}_P.npy") and os.path.exists(f"{src}/{b[0]}_derived_{th}.geojson")]
    for nm in boxes:
        m = json.load(open(f"{src}/{nm}_meta.json")); clip = sbox(*m["box"])
        trP = Affine(kl.CELL, 0, m["x0"], 0, -kl.CELL, m["y0"] + m["w"]); P = np.load(f"{ld}/{nm}_P.npy").astype(np.float32) / 255
        D, R = ck.lines(f"{src}/{nm}_derived_{th}.geojson", clip), ck.lines(f"{src}/{nm}_kerbs.geojson", clip)
        up, trU = (None, None)
        if os.path.exists(f"{src}/{nm}_dem.npy"):
            trU, up = ks.grids(src, nm, D)[:2]
        ev = Ev(P, trP, up, trU)
        res[nm] = {"base": (*ks.rate(D, R), 0.0)}
        for name, at, br in VARIANTS:
            new = trace(D, ev, at, br, clip)
            res[nm][name] = (*ks.rate(D + new, R), round(sum(l.length for l in new) / 1000, 2))
        print(nm, "LiDAR" if up is not None else "photo only", {k: (round(v[0], 3), round(v[1], 3), round(ks.f1(v), 3), v[2]) for k, v in res[nm].items()}, flush=True)
    by = {}
    for nm in boxes:
        by.setdefault(kl.SCEN[nm], []).append(nm)
    hold = [n for n in boxes if n in dict(h[:2] for h in kl.HOLD)]
    for k in res[boxes[0]]:
        print(k, "scenario score", round(float(np.mean([np.mean([ks.f1(res[n][k]) for n in v]) for v in by.values()])), 3),
              "worst held-out", round(min(ks.f1(res[n][k]) for n in hold), 3), "added km", round(sum(res[n][k][2] for n in boxes), 1), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "filter":  # python kerbtrace.py filter kp_dir long_dir thresh
        filt(*sys.argv[2:5])
    else:
        main()
