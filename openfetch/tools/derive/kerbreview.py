"""Independent kerb reviewer: checks a kerb version for shapes that are obviously wrong before Jacky ever sees it, and gets
stricter over time (Jacky 7 Nov 2026: "so many back and forth ... when the result it shows is obviously wrong. I want this process
to be automated and improved overtime").

    python3 kerbreview.py check kerbs.json[.gz] out_dir --roads roads_dir [--prev review.json] [--cases kerbreview-cases.json] [--no-photo]
    python3 kerbreview.py visual out_dir verdicts.json        (the visual reviewer's tile verdicts -> review.json result)
    python3 kerbreview.py selftest kerbs.json[.gz] version    (every case found in that version must be caught by the checks)
    python3 kerbreview.py sample kerbs.json[.gz] out_dir [40]   (headline: random places sheet) ; score out_dir verdicts.json
    python3 kerbreview.py addcase x y version "Jacky's words" kinds [--r 20]   (kinds: comma list of KINDS, x y in EPSG 7856)

check writes out_dir/review.json (counts, per-km rates, worst spots, fails) and out_dir/review-sheet.png (the worst 12 spots on
the NSW aerial: our kerbs cyan, the flagged part magenta, label = what is wrong), then 8 random places ("random": things no
geometry rule knows yet). review.json "result" is "pending visual" when
the geometry passes: a separate reviewer (a fresh agent that did not make the version) opens review-sheet.png, judges each tile as
Jacky would (OK / WRONG + why) into verdicts.json [{"tile": 1, "verdict": "OK"|"WRONG", "why": "..."}], and `visual` sets
"result" to pass only when no tile is WRONG. Every WRONG tile is added to the cases file, so it is checked forever after.
kerbs-check.py (OpenFetch main) refuses a version whose review.json is missing or not "pass".

Kinds (all in metres, EPSG 7856; every one is a shape council kerb lines do not have):
  cross    two kerbs cross in an X (neither ends there)
  poke     a kerb crosses another and its end pokes less than POKE m past it
  self     a kerb crosses itself
  fold     a kerb comes back within FOLD_D of itself more than FOLD_ALONG further along (fold-back, strands)
  dup      two kerbs run side by side less than DUP_D apart and within DUP_ANG for DUP_LEN or more (parallel duplicate)
  inside   a kerb lies (INSIDE_SHARE of its length) within INSIDE_D of other kerbs: a kerb within a kerb
  beside   a free kerb end sits within BESIDE_D of another kerb that runs parallel to it for BESIDE_LEN (stops beside a line)
  near     a kerb end NEAR_D or closer to another kerb without touching it (a corner or join left open)
  merge    a kerb end slides into another kerb at under 30 deg, running within 3 m of it for MERGE_LEN (a Y)
           (near capped at 0.05 per km on 8 Nov 2026: in g all 12 near tiles judged wrong, hooks and ends stopping short; merge capped at 0 on 8 Nov 2026: e 5 of 10 judged wrong, f 5 of 7 flagged + 4 of 5 earlier merges)
  gap      two free kerb ends face each other (both within GAP_ANG of the line between them) GAP_MIN-GAP_MAX apart, nothing
           crossing the gap: a broken straight kerb (Jacky 8 Nov 2026, whole-suburb preview). Capped at 0 with --roads (street
           centrelines rule out street mouths; --roads is required since 8 Nov 2026). On e with --roads 190 (12 checked by eye: all broken kerbs or leftover
           main-road pieces); without centrelines 251,
           12 checked by eye, 10 real breaks, 2 false across a junction mouth (needs street centrelines to rule those out).
  loop     a closed kerb ring smaller than LOOP_AREA m2
Fails: any spot within r of a case's point (regression, hard); a kind's rate per km over its cap, where the cap is the lower of its
starting bar (CAP: none at all, fold one per 100 km (7 Nov 2026 2026-11-07-c passed looser caps of one per 20-100 km, yet
every flagged spot on its sheet was a real defect, 12 of 12, so any flag now fails); 7 Nov 2026 a hand check of 12 random flagged spots in 2026-11-07-b found
all 12 really wrong, while Parramatta's council lines only trip dup / inside / cross where the council stores the same kerb twice
or a kerb and its gutter 0.5 m apart, so the council is not used as the bar here) and the best rate any earlier passing version
reached plus RATCHET (so a version can never be worse than the best already shipped).
"""
import gzip
import io
import json
import math
import os
import sys
import time
import urllib.request

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

POKE, FOLD_D, FOLD_ALONG = 6.0, 2.5, 8.0
DUP_D, DUP_ANG, DUP_LEN = 2.0, 20.0, 8.0
INSIDE_D, INSIDE_SHARE, BESIDE_D, BESIDE_LEN, LOOP_AREA = 2.5, 0.8, 3.5, 10.0, 30.0
GAP_MIN, GAP_MAX, GAP_ANG, GAP_CAP = 1.0, 30.0, 10.0, 0.0   # gap: two free ends facing each other along one line (a broken straight kerb)
NEAR_D, MERGE_LEN = 5.0, 8.0         # near: a kerb end 1-5 m from another kerb (a join left open); merge: slides into another line
END_TOUCH = 1.0                       # a crossing this close to a kerb end is a join, not a crossing
KINDS = ('cross', 'poke', 'self', 'fold', 'dup', 'inside', 'beside', 'near', 'merge', 'gap', 'loop')
CAP = {'cross': 0.0, 'poke': 0.0, 'self': 0.0, 'fold': 0.0, 'dup': 0.0, 'inside': 0.0, 'beside': 0.0, 'near': 0.05, 'merge': 0.0, 'gap': 99, 'loop': 0.0}   # near, merge: measured only until a visual run confirms them
RATCHET = 0.10                        # a later version may be at most 10 % worse than the best passing one, per kind
HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, 'kerbreview-cases.json')
IMG = ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={},{},{},{}&bboxSR=7856"
       "&imageSR=7856&size={},{}&format=jpg&f=image")


def load(path):
    d = json.load(gzip.open(path) if path.endswith('.gz') else open(path))
    tr = Transformer.from_crs(7844, 7856, always_xy=True)
    lines = []
    for f in d['features']:
        g = f['geometry']
        parts = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates'] if g['type'] == 'MultiLineString' else []
        for c in parts:
            if len(c) < 2: continue
            if abs(c[0][0]) < 1000: c = [tr.transform(p[0], p[1]) for p in c]
            ln = LineString([(p[0], p[1]) for p in c])
            if ln.length > 0.5: lines.append(ln)
    return lines


def heading(ln, d, step=1.0):
    a, b = ln.interpolate(max(0, d - step)), ln.interpolate(min(ln.length, d + step))
    return math.atan2(b.y - a.y, b.x - a.x)


def angdiff(a, b):
    d = abs(a - b) % math.pi
    return math.degrees(min(d, math.pi - d))


def chunks(ln, step=2.0):
    n = max(1, int(math.ceil(ln.length / step)))
    return [(i * ln.length / n, LineString([ln.interpolate(i * ln.length / n), ln.interpolate((i + 1) * ln.length / n)]))
            for i in range(n)]


def crossings(lines, tree, spots):
    for i, a in enumerate(lines):
        for j in tree.query(a, predicate='intersects'):
            if j <= i: continue
            b = lines[j]; x = a.intersection(b)
            pts = [x] if x.geom_type == 'Point' else [g for g in getattr(x, 'geoms', []) if g.geom_type == 'Point']
            for p in pts:
                da, db = a.project(p), b.project(p)
                ea, eb = min(da, a.length - da), min(db, b.length - db)
                if ea < END_TOUCH or eb < END_TOUCH: continue
                kind = 'poke' if min(ea, eb) < POKE else 'cross'
                spots.append({'kind': kind, 'x': p.x, 'y': p.y, 'size': round(min(ea, eb), 1)})


def selfs(ln, spots):
    if ln.is_simple: return
    segs = [LineString(ln.coords[k:k + 2]) for k in range(len(ln.coords) - 1)]
    t = STRtree(segs)
    for k, s in enumerate(segs):
        for m in t.query(s, predicate='intersects'):
            if m <= k + 1: continue
            if m == len(segs) - 1 and k == 0 and ln.is_ring: continue
            p = s.intersection(segs[m])
            if p.geom_type == 'Point': spots.append({'kind': 'self', 'x': p.x, 'y': p.y, 'size': 0}); return


def folds(ln, spots):
    if ln.length < FOLD_ALONG + 2: return
    cs = chunks(ln, 1.0); t = STRtree([c for _, c in cs]); seen = []
    ring = ln.coords[0] == ln.coords[-1] or Point(ln.coords[0]).distance(Point(ln.coords[-1])) < END_TOUCH
    for k, (d, c) in enumerate(cs):
        for m in t.query(c, predicate='dwithin', distance=FOLD_D):
            along = abs(cs[m][0] - d)
            if ring: along = min(along, ln.length - along)
            if along <= FOLD_ALONG: continue
            p = c.interpolate(0.5, normalized=True)
            if any(p.distance(q) < 15 for q in seen): continue
            seen.append(p); spots.append({'kind': 'fold', 'x': p.x, 'y': p.y, 'size': round(c.distance(cs[m][1]), 2)})


def dups(lines, tree, spots):
    pieces = [(i, d, c, heading(ln, d + 1.0)) for i, ln in enumerate(lines) for d, c in chunks(ln)]
    pt = STRtree([c for _, _, c, _ in pieces]); flag = [False] * len(pieces)
    for k, (i, d, c, h) in enumerate(pieces):
        for m in pt.query(c, predicate='dwithin', distance=DUP_D):
            j = pieces[m][0]
            if j != i and angdiff(h, pieces[m][3]) < DUP_ANG and c.distance(pieces[m][2]) > 0.05: flag[k] = True; break
    run, start = 0.0, None
    for k, (i, d, c, h) in enumerate(pieces + [(-1, 0, None, 0)]):
        if k < len(pieces) and flag[k] and (start is None or pieces[k - 1][0] == i):
            if start is None: start = k
            run += c.length; continue
        if start is not None and run >= DUP_LEN:
            mid = pieces[(start + k - 1) // 2][2].interpolate(0.5, normalized=True)
            if not any(s['kind'] == 'dup' and math.hypot(s['x'] - mid.x, s['y'] - mid.y) < 15 for s in spots):
                spots.append({'kind': 'dup', 'x': mid.x, 'y': mid.y, 'size': round(run, 1)})
        run, start = 0.0, None
        if k < len(pieces) and flag[k]: start, run = k, c.length


def insides(lines, tree, spots):
    for i, ln in enumerate(lines):
        others = [lines[j] for j in tree.query(ln, predicate='dwithin', distance=INSIDE_D) if j != i]
        if not others: continue
        cs = chunks(ln, 1.0)
        near = sum(c.length for _, c in cs if any(o.distance(c) < INSIDE_D for o in others))
        if near >= INSIDE_SHARE * ln.length:
            p = ln.interpolate(0.5, normalized=True)
            spots.append({'kind': 'inside', 'x': p.x, 'y': p.y, 'size': round(ln.length, 1)})


def besides(lines, tree, spots):
    for i, ln in enumerate(lines):
        if ln.length < 3: continue
        for end, d in ((Point(ln.coords[0]), 0.0), (Point(ln.coords[-1]), ln.length)):
            near = [j for j in tree.query(end, predicate='dwithin', distance=BESIDE_D) if j != i]
            if not near or any(lines[j].distance(end) < END_TOUCH for j in near): continue
            h = heading(ln, d, 2.0)
            for j in near:
                o = lines[j]; od = o.project(end)
                lo, hi = max(0, od - BESIDE_LEN / 2), min(o.length, od + BESIDE_LEN / 2)
                if hi - lo < BESIDE_LEN * 0.9 or angdiff(h, heading(o, od, 3.0)) > DUP_ANG: continue
                spots.append({'kind': 'beside', 'x': end.x, 'y': end.y, 'size': round(o.distance(end), 2)}); break


def nears(lines, tree, spots):
    for i, ln in enumerate(lines):
        if ln.length < 3: continue
        for end, d in ((Point(ln.coords[0]), 0.0), (Point(ln.coords[-1]), ln.length)):
            near = [(lines[j].distance(end), j) for j in tree.query(end, predicate='dwithin', distance=NEAR_D) if j != i]
            if not near: continue
            dist, j = min(near)
            if dist < END_TOUCH:                           # touches: a merge if it slides in alongside the other line
                back = ln.interpolate(min(MERGE_LEN, ln.length - 0.1) if d == 0 else max(0.1, ln.length - MERGE_LEN))
                if lines[j].distance(back) < 3.0 and angdiff(heading(ln, d, 2.0), heading(lines[j], lines[j].project(end), 2.0)) < 30:
                    spots.append({'kind': 'merge', 'x': end.x, 'y': end.y, 'size': round(lines[j].distance(back), 2)})
            elif not any(s['kind'] == 'beside' and abs(s['x'] - end.x) < 0.01 and abs(s['y'] - end.y) < 0.01 for s in spots):
                spots.append({'kind': 'near', 'x': end.x, 'y': end.y, 'size': round(dist, 2)})


def load_roads(d):
    """Street centrelines at ground level (EPSG 7856 cell files, kerbaudit.py layout); paths and tracks (functionhierarchy 8-11),
    bridges and tunnels (roadontype 2, 3) left out."""
    import glob
    from shapely.geometry import shape
    out, seen = [], set()
    for fn in sorted(glob.glob(os.path.join(d, '*.json'))):
        for f in json.load(open(fn)).get('features', []):
            pr = f.get('properties') or {}; key = pr.get('OBJECTID', pr.get('objectid', f.get('id')))
            if not f.get('geometry') or key in seen or str(pr.get('functionhierarchy')) in ('8', '9', '10', '11'): continue
            if str(pr.get('roadontype', 1)) in ('2', '3'): continue   # bridges and tunnels do not open a kerb (WestConnex runs under Erskineville)
            if key is not None: seen.add(key)
            g = shape(f['geometry'])
            out += [x for x in (g.geoms if g.geom_type.startswith('Multi') else [g]) if x.geom_type == 'LineString']
    return out


def gaps(lines, tree, spots, roads=None):
    ends = []                                           # free kerb ends with their outward heading
    for i, ln in enumerate(lines):
        if ln.length < 4: continue
        for k, end in ((0, Point(ln.coords[0])), (1, Point(ln.coords[-1]))):
            if any(lines[j].distance(end) < END_TOUCH for j in tree.query(end, predicate='dwithin', distance=END_TOUCH) if j != i):
                continue
            inn = ln.interpolate(3.0 if k == 0 else ln.length - 3.0)
            ends.append((i, end, math.atan2(end.y - inn.y, end.x - inn.x)))
    et = STRtree([e[1] for e in ends]); seen = set()
    for a, (i, p, h) in enumerate(ends):
        for b in et.query(p, predicate='dwithin', distance=GAP_MAX):
            j, q, g = ends[b]
            if j == i or (min(a, b), max(a, b)) in seen: continue
            dist = p.distance(q)
            if dist < GAP_MIN: continue
            to = math.atan2(q.y - p.y, q.x - p.x)
            turn = lambda x, y: math.degrees(abs((x - y + math.pi) % (2 * math.pi) - math.pi))
            if turn(h, to) > GAP_ANG or turn(g, to + math.pi) > GAP_ANG: continue
            bridge = LineString([p, q])
            if any(bridge.crosses(lines[m]) for m in tree.query(bridge) if m not in (i, j)): continue
            if roads is not None and len(roads[1].query(bridge, predicate='intersects')): continue   # a street mouth
            seen.add((min(a, b), max(a, b)))
            spots.append({'kind': 'gap', 'x': (p.x + q.x) / 2, 'y': (p.y + q.y) / 2, 'size': round(dist, 1)})


def loops(lines, spots):
    for ln in lines:
        if ln.length > 4 and Point(ln.coords[0]).distance(Point(ln.coords[-1])) < END_TOUCH:
            a = Polygon(ln.coords).area
            if a < LOOP_AREA:
                c = ln.centroid; spots.append({'kind': 'loop', 'x': c.x, 'y': c.y, 'size': round(a, 1)})


def review(lines, roads=None):
    tree, spots = STRtree(lines), []
    crossings(lines, tree, spots)
    for ln in lines: selfs(ln, spots); folds(ln, spots)
    dups(lines, tree, spots); insides(lines, tree, spots); besides(lines, tree, spots); nears(lines, tree, spots); gaps(lines, tree, spots, roads); loops(lines, spots)
    km = sum(ln.length for ln in lines) / 1000
    count = {k: sum(1 for s in spots if s['kind'] == k) for k in KINDS}
    return spots, km, count


def caps(prev):
    c = dict(CAP)
    if prev and os.path.exists(prev):
        p = json.load(open(prev))
        for k, v in p.get('best_per_km', {}).items():
            if k in c: c[k] = min(c[k], round(v * (1 + RATCHET) + 0.01, 3))
    return c


def against_cases(spots, cases_path, fails):
    hits = []
    for cs in json.load(open(cases_path)) if os.path.exists(cases_path) else []:
        for s in spots:
            if s['kind'] in cs['kinds'] and math.hypot(s['x'] - cs['x'], s['y'] - cs['y']) <= cs.get('r', 20):
                hits.append(cs['id']); fails.append(f"case {cs['id']} ({cs['words']}, {cs['version']}) is back: {s['kind']} at "
                                                    f"{s['x']:.1f} {s['y']:.1f}"); break
    return hits


def photo(x0, y0, x1, y1, px):
    from PIL import Image
    for k in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(IMG.format(x0, y0, x1, y1, px, px),
                                                              headers={'User-Agent': 'openfetch-derive'}), timeout=60)
            return Image.open(io.BytesIO(r.read())).convert('RGB').resize((px, px))
        except Exception:
            time.sleep(2 * (k + 1))
    return Image.new('RGB', (px, px), (60, 60, 60))


def sheet(lines, tree, spots, out, n=12, m=70, px=420, use_photo=True):
    from PIL import Image, ImageDraw
    cols = 4; rows = max(1, math.ceil(min(n, len(spots)) / cols))
    img = Image.new('RGB', (cols * px, rows * (px + 24)), (20, 20, 20)); dr = ImageDraw.Draw(img)
    for t, s in enumerate(spots[:n]):
        x0, y0, x1, y1 = s['x'] - m / 2, s['y'] - m / 2, s['x'] + m / 2, s['y'] + m / 2
        tl = photo(x0, y0, x1, y1, px) if use_photo else Image.new('RGB', (px, px), (60, 60, 60))
        d = ImageDraw.Draw(tl); f = lambda p: ((p[0] - x0) / m * px, (y1 - p[1]) / m * px)
        from shapely.geometry import box
        for j in tree.query(box(x0, y0, x1, y1)):
            d.line([f(p) for p in lines[j].coords], fill=(0, 230, 255), width=3)
        cx, cy = f((s['x'], s['y'])); d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(255, 0, 255), width=3)
        d.line([(px - 10 - 10 / m * px, px - 12), (px - 10, px - 12)], fill=(255, 255, 255), width=3)
        X, Y = (t % cols) * px, (t // cols) * (px + 24)
        img.paste(tl, (X, Y + 24))
        dr.text((X + 6, Y + 6), f"{t + 1}  {s['kind']} ({s['size']})  {s['x']:.0f} {s['y']:.0f}", fill=(255, 255, 255))
    img.save(out, quality=85)


SEVERITY = {'random': 0, 'cross': 5, 'self': 5, 'fold': 4, 'inside': 4, 'poke': 4, 'dup': 3, 'loop': 3, 'merge': 3, 'beside': 2, 'near': 2, 'gap': 3}


def check(a):
    src, out = a[0], a[1]; opt = {k: a[a.index('--' + k) + 1] for k in ('prev', 'cases', 'roads') if '--' + k in a}
    os.makedirs(out, exist_ok=True)
    roads = None
    if opt.get('roads'):
        r = load_roads(opt['roads']); roads = (r, STRtree(r))
    lines = load(src); spots, km, count = review(lines, roads)
    rate = {k: round(count[k] / km, 3) for k in KINDS}
    fails = []; cap = caps(opt.get('prev'))
    if roads: cap['gap'] = min(cap['gap'], GAP_CAP)    # with centrelines, street mouths are ruled out: a gap is a broken kerb
    else: fails.append('no --roads: street centrelines are needed to tell a broken kerb from a street mouth')
    hits = against_cases(spots, opt.get('cases', CASES), fails)
    for k in KINDS:
        if count[k] > cap[k] * km: fails.append(f'{k}: {count[k]} spots, {rate[k]} per km, over the cap {cap[k]}')
    spots.sort(key=lambda s: (-SEVERITY[s['kind']], -s['size'] if s['kind'] in ('dup', 'inside') else s['size']))
    pick, seen = [], set()
    for s in spots:                                     # the sheet shows the worst of every kind first, then the rest
        if s['kind'] not in seen: pick.append(s); seen.add(s['kind'])
    pick += [s for s in spots if s not in pick]
    import random
    rnd, rand = random.Random(os.path.basename(src)), []; tot = sum(ln.length for ln in lines)
    for _ in range(8 if len(spots) >= 12 else 16):      # few flags left: look at more ordinary places
        r, i = rnd.uniform(0, tot), 0
        while r > lines[i].length: r -= lines[i].length; i += 1
        p = lines[i].interpolate(r); rand.append({'kind': 'random', 'x': p.x, 'y': p.y, 'size': 0})
    pick = pick[:12] + rand
    if opt.get('prev') and os.path.exists(opt['prev']):   # the last version's worst spots: fixed, or only deleted?
        was = json.load(open(opt['prev'])).get('sheet_spots', [])
        pick += [dict(s, kind='was ' + s['kind']) for s in was if s['kind'] in KINDS][:8]
    for c in (json.load(open(opt.get('cases', CASES))) if os.path.exists(opt.get('cases', CASES)) else []):
        if c['kinds'] == ['random']:                    # a visual-only case (no geometry rule knows it): re-judged every version
            pick.append({'kind': 'case ' + c['id'], 'x': c['x'], 'y': c['y'], 'size': 0})
    tree = STRtree(lines)
    sheet(lines, tree, pick, os.path.join(out, 'review-sheet.jpg'), n=len(pick), use_photo='--no-photo' not in a)
    best = {}
    if opt.get('prev') and os.path.exists(opt['prev']): best = json.load(open(opt['prev'])).get('best_per_km', {})
    rv = {'check': 'openfetch-derive tools/derive/kerbreview.py', 'source': src, 'km': round(km, 1), 'count': count,
          'per_km': rate, 'caps': cap, 'case_hits': hits, 'fails': fails,
          'result': 'fail' if fails else 'pending visual', 'sheet': 'review-sheet.jpg',
          'sheet_spots': pick, 'spots': spots,
          'best_per_km': best if fails else {k: min(rate[k], best.get(k, rate[k])) for k in KINDS}}
    json.dump(rv, open(os.path.join(out, 'review.json'), 'w'), indent=1)
    print(rv['result'], json.dumps({'km': rv['km'], 'count': count, 'fails': fails}))
    return 1 if fails else 0


def visual(a):
    out, vf = a[0], a[1]; p = os.path.join(out, 'review.json'); rv = json.load(open(p))
    ver = json.load(open(vf)); wrong = [v for v in ver if v.get('verdict') == 'WRONG']
    rv['visual'] = ver
    if rv['result'] == 'fail': pass
    elif wrong:
        rv['result'] = 'fail'
        rv['fails'] += [f"visual tile {v['tile']}: {v.get('why', '')}" for v in wrong]
    else: rv['result'] = 'pass'
    cases = json.load(open(CASES)) if os.path.exists(CASES) else []
    for v in wrong:
        s = rv['sheet_spots'][v['tile'] - 1]
        if s['kind'].startswith('case '): continue
        if s['kind'].startswith('was '): s = dict(s, kind=s['kind'][4:])
        if not any(math.hypot(s['x'] - c['x'], s['y'] - c['y']) < 10 for c in cases):
            cases.append({'id': f"V{len(cases) + 1}", 'x': round(s['x'], 1), 'y': round(s['y'], 1), 'r': 15,
                          'kinds': [s['kind']], 'words': 'visual reviewer: ' + v.get('why', ''), 'version': rv['source'],
                          'by': 'visual reviewer'})
    json.dump(cases, open(CASES, 'w'), indent=1)
    json.dump(rv, open(p, 'w'), indent=1)
    print(rv['result'], len(wrong), 'wrong tiles')
    return 0 if rv['result'] == 'pass' else 1


def selftest(a):
    lines = load(a[0]); spots, _, _ = review(lines); miss = []
    for cs in json.load(open(CASES)):
        if cs['version'] != a[1]: continue
        if not any(s['kind'] in cs['kinds'] and math.hypot(s['x'] - cs['x'], s['y'] - cs['y']) <= cs.get('r', 20) for s in spots):
            near = sorted(spots, key=lambda s: math.hypot(s['x'] - cs['x'], s['y'] - cs['y']))[:3]
            miss.append((cs['id'], cs['words'], [(s['kind'], round(math.hypot(s['x'] - cs['x'], s['y'] - cs['y']), 1)) for s in near]))
    print('selftest', 'pass' if not miss else 'fail', miss)
    return 1 if miss else 0


def addcase(a):
    cases = json.load(open(CASES)) if os.path.exists(CASES) else []
    r = float(a[a.index('--r') + 1]) if '--r' in a else 20
    kinds = a[4].split(',')
    if any(k not in KINDS for k in kinds): sys.exit(f'kinds must be from {KINDS}')
    cases.append({'id': f"J{sum(1 for c in cases if c['id'].startswith('J')) + 1}", 'x': float(a[0]), 'y': float(a[1]), 'r': r,
                  'kinds': kinds, 'words': a[3], 'version': a[2], 'by': 'Jacky'})
    json.dump(cases, open(CASES, 'w'), indent=1); print('added', cases[-1]['id'])
    return 0


def sample(a):
    """Headline score (Jacky 9 Nov 2026): N random places on our lines, judged whole-tile by a fresh reviewer; clean % =
    OK tiles / judged tiles. Same seed per file, so a rerun shows the same places."""
    import random
    src, out, n = a[0], a[1], int(a[2]) if len(a) > 2 else 40
    os.makedirs(out, exist_ok=True); lines = load(src)
    rnd, tot, pick = random.Random(os.path.basename(src)), sum(ln.length for ln in lines), []
    for _ in range(n):
        r, i = rnd.uniform(0, tot), 0
        while r > lines[i].length: r -= lines[i].length; i += 1
        p = lines[i].interpolate(r); pick.append({'kind': 'random', 'x': p.x, 'y': p.y, 'size': 0})
    sheet(lines, STRtree(lines), pick, os.path.join(out, 'random-sheet.jpg'), n=n)
    json.dump({'source': src, 'spots': pick}, open(os.path.join(out, 'random.json'), 'w'), indent=1)
    print('random sheet', n, 'tiles; judge with kerbreview-prompt.md, then: kerbreview.py score', out, 'verdicts.json')
    return 0


def score(a):
    out, vf = a[0], a[1]; v = json.load(open(vf)); rj = os.path.join(out, 'random.json'); r = json.load(open(rj))
    judged = [x for x in v if x['verdict'] in ('OK', 'WRONG')]
    r['visual'] = v; r['clean_pct'] = round(100.0 * sum(x['verdict'] == 'OK' for x in judged) / max(1, len(judged)), 1)
    json.dump(r, open(rj, 'w'), indent=1); print('clean', r['clean_pct'], '% of', len(judged), 'judged random places')
    return 0


if __name__ == '__main__':
    cmd = {'sample': sample, 'score': score, 'check': check, 'visual': visual, 'selftest': selftest, 'addcase': addcase}
    if len(sys.argv) < 3 or sys.argv[1] not in cmd: sys.exit(__doc__)
    sys.exit(cmd[sys.argv[1]](sys.argv[2:]))
