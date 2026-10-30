#!/usr/bin/env python3
"""Round planner and recorder for the kerb photo model that learns round after round (kerblearn.py, kerb-learn GitHub workflow).

Usage:
  python3 kerbloop.py plan state.json            (prints {"variants": [...], "best_run": id, "best_artifact": name} for the round)
  python3 kerbloop.py record state.json log.md results/   (adds the round to the log and state, prints "continue" or "stop: <reason>")

Round 1 starts three variants (later rounds up to WIDTH) from an ImageNet encoder. Every later round fine-tunes the best model so far and feeds it its own
mistakes on the training boxes: each variant puts most of the extra chips on one probable cause of the misses (the biggest causes
first), or on the extra lines it draws. A variant becomes the new best only if it does better on the check boxes (inside the
training councils); the held-out boxes are reported, never used to choose. The log says, per cause, how much more kerb was found
than by the model it started from. Stops at the target on every held-out box, after MAX_ROUNDS, after PLATEAU rounds with no gain
of MIN_GAIN, or when nothing is left to try.
"""
import sys, os, json, glob

TARGET, MAX_ROUNDS, WIDTH, MIN_GAIN, PLATEAU = 0.85, 8, 5, 0.005, 2
TYPES = ("under trees", "in shadow", "cars or clutter", "faint kerb", "clear kerb")
START = {"encoder": "resnet34", "minutes": 150, "chip": 192, "batch": 12, "lr": 1e-3, "pw": 4.0, "skel": 0.0, "mine": 0.0,
         "focus": ""}
FIRST = [("ImageNet start", START), ("ImageNet start + unbroken-line loss", {**START, "skel": 1.0}),
         ("ImageNet start + unbroken-line loss, bigger view", {**START, "skel": 1.0, "chip": 256, "batch": 7})]
TUNE = {"minutes": 100, "lr": 3e-4, "mine": 0.4}
HOLD = ("monavale", "newport", "parramatta")
CHECK = ("nbcheck", "cbcheck", "wocheck")


def load(p):
    if os.path.exists(p):
        return json.load(open(p))
    return {"round": 0, "best": None, "tried": [], "history": [], "stale": 0, "status": "running"}


def moves(best):
    c = {**best["cfg"], **TUNE}
    m = best.get("train_misses", {})
    out = [(f"learn from misses ({t})", {**c, "focus": t}) for t in sorted(m, key=m.get, reverse=True) if m[t]]
    out.insert(2, ("learn from extra lines", {**c, "focus": "extra lines"}))
    if not c.get("context"):
        out.insert(0, ("add road and water map context", {**c, "context": 1, "focus": out[0][1]["focus"] if out else ""}))
    if out and not c.get("skel"):
        out.insert(1, ("learn from misses + unbroken-line loss", {**c, "skel": 1.0, "focus": out[0][1]["focus"]}))
    return out


def plan(a):
    st = load(a[0]); b = st["best"]
    if not b:
        vs = FIRST
    else:
        vs = [v for v in moves(b) if [v[0], b["round"]] not in st["tried"]][:WIDTH]
    print(json.dumps({"variants": [{"name": n, "id": i, "cfg_json": json.dumps(c)} for i, (n, c) in enumerate(vs)],
                      "best_run": str(b["run"]) if b else "", "best_artifact": b["artifact"] if b else ""}))


def f1(v):
    return 2 * v.get("recall", 0) * v.get("precision", 0) / max(v.get("recall", 0) + v.get("precision", 0), 1e-6)


def met(r):
    b = {n: r["boxes"].get(n) or {} for n in HOLD}
    return all(b[n].get("recall", 0) >= TARGET and (b[n].get("offset_median_m") or 9) <= 0.3 and b[n].get("precision", 0) >= 0.7
               for n in HOLD)


def causes(r):
    """Found share per probable cause over the check and held-out boxes, and metres of extra line."""
    tot = {t: [0, 0.0] for t in TYPES}
    for n in CHECK + HOLD:
        for t, (k, f) in r["boxes"].get(n, {}).get("types", {}).items():
            tot[t][0] += k; tot[t][1] += k * (f or 0)
    return {t: (k, f / k if k else None) for t, (k, f) in tot.items()}, sum(r["boxes"].get(n, {}).get("extra_m", 0) for n in CHECK + HOLD)


def learnt(r, prev):
    now, ex = causes(r)
    parts = []
    for t in TYPES:
        k, f = now[t]
        if f is None:
            continue
        was = causes(prev)[0][t][1] if prev else None
        parts.append(f"{t} {f:.0%}" + (f" (was {was:.0%})" if was is not None else "") + f" of {k * 0.5 / 1000:.1f} km")
    was_ex = causes(prev)[1] if prev else None
    wl = sum((r["boxes"].get(n) or {}).get("whole_lines", 0) for n in HOLD) / len(HOLD)
    return ("found by cause: " + "; ".join(parts) + f". Extra lines {ex / 1000:.1f} km" +
            (f" (was {was_ex / 1000:.1f} km)" if was_ex is not None else "") + f". Whole kerb lines found (held-out) {wl:.0%}.")


def row(rnd, r):
    b = r["boxes"]
    cell = lambda n: f"{b[n]['recall']:.0%} / {b[n]['precision']:.0%} / {b[n].get('offset_median_m')} m" if b.get(n) else "-"
    return (f"| {rnd} | {r['name']} | {r['val_f1']:.3f} | {cell('monavale')} | {cell('newport')} | {cell('parramatta')} | "
            f"{r['thresh']} | {r.get('minutes')} |\n")


def record(a):
    sp, lp, rd = a
    st = load(sp); st["round"] += 1; prev = st["best"]
    res = []
    for p in sorted(glob.glob(f"{rd}/**/result.json", recursive=True)):
        r = json.load(open(p)); r.update(json.load(open(os.path.join(os.path.dirname(p), "name.json")))); res.append(r)
    new = not os.path.exists(lp) or os.path.getsize(lp) == 0
    with open(lp, "a") as f:
        if new:
            f.write("# Kerb photo model: learning log\n\nEach round starts from the best model so far and trains on its mistakes. "
                    "Check F1 = balance of found and precise on the check boxes (inside the training councils), used to keep or drop "
                    "a model. Held-out boxes (never trained on, Parramatta a council never seen): found / precise / median offset "
                    "within 1 m. Bar: 85% found, 0.3 m, every held-out box.\n")
        start = f"round {prev['round']} model ({prev['name']})" if prev else "ImageNet encoder"
        f.write(f"\n## Round {st['round']} (started from the {start})\n\n| round | change | check F1 | Mona Vale | Newport | "
                "Parramatta | threshold | minutes |\n|---|---|---|---|---|---|---|---|\n")
        for r in res:
            f.write(row(st["round"], r))
        for r in res:
            f.write(f"\n- {r['name']}: {learnt(r, prev)}")
    for r in res:
        if prev:
            st["tried"].append([r["name"], prev["round"]])
        st["history"].append({"round": st["round"], "name": r["name"], "val_f1": r["val_f1"], "score": r["score"]})
    top = max(res, key=lambda r: r["val_f1"]) if res else None
    if top and (not prev or top["val_f1"] >= prev["val_f1"] + MIN_GAIN):
        st["best"] = {k: top.get(k) for k in ("name", "cfg", "val_f1", "score", "mean_recall", "thresh", "boxes", "train_misses",
                                             "train_extra_points", "artifact", "run")}
        st["best"]["round"] = st["round"]; st["stale"] = 0
        m = top["train_misses"]
        verdict = (f"Kept: {top['name']} (check F1 {top['val_f1']:.3f}" + (f", was {prev['val_f1']:.3f}" if prev else "") +
                   f"). Its biggest misses on the training boxes: " +
                   ", ".join(f"{t} {m[t] * 0.5 / 1000:.1f} km" for t in sorted(m, key=m.get, reverse=True)[:3]) +
                   "; the next round trains on those.")
    else:
        st["stale"] += 1
        verdict = (f"Nothing kept: no variant beat check F1 {prev['val_f1']:.3f} by {MIN_GAIN}; the round {prev['round']} model "
                   "stays and the next round tries the next causes." if prev else "No results.")
    with open(lp, "a") as f:
        f.write(f"\n\n**{verdict}**\n")
    why = None
    if st["best"] and met(st["best"]):
        why = "target reached"
    elif st["round"] >= MAX_ROUNDS:
        why = f"round cap ({MAX_ROUNDS}) reached"
    elif st["stale"] >= PLATEAU:
        why = f"plateau ({PLATEAU} rounds without a check F1 gain of {MIN_GAIN})"
    elif not res:
        why = "no results this round (jobs failed)"
    elif not [v for v in moves(st["best"]) if [v[0], st["best"]["round"]] not in st["tried"]]:
        why = "every change tried"
    if why:
        st["status"] = "stopped: " + why
        b = st["best"] or {}
        with open(lp, "a") as f:
            f.write(f"\n**Stopped after round {st['round']}: {why}.** Best: {b.get('name')} (round {b.get('round')}), held-out mean "
                    f"found {b.get('mean_recall', 0):.1%}, model: run {b.get('run')} artifact {b.get('artifact')}.\n")
    json.dump(st, open(sp, "w"), indent=1)
    print("stop: " + why if why else "continue")


if __name__ == "__main__":
    {"plan": plan, "record": record}[sys.argv[1]](sys.argv[2:])
