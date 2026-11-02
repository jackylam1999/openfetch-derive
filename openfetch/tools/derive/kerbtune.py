#!/usr/bin/env python3
"""Automatic tuning loop for the kerb photo model (kerbphoto.py), run by the kerb-tune GitHub workflow.

Usage:
  python3 kerbtune.py plan state.json            (prints the round's variants as a JSON list for the job matrix)
  python3 kerbtune.py record state.json log.md results/   (adds the round's results, prints "continue" or "stop: <reason>")

Each round tries up to WIDTH variants side by side, each one change (a MOVE) on the best settings so far; round 1 also runs the
settings unchanged. The best variant (mean F1 over the held-out boxes: found and precise within 1 m of council kerbs, so extra
lines cannot buy a better score) becomes the new base. The loop stops when every held-out box reaches TARGET found with a median offset
<= 0.3 m, after MAX_ROUNDS rounds, when two rounds in a row gain under half a point (plateau), or when no move is left to try.
"""
import sys, os, json, glob

TARGET, MAX_ROUNDS, WIDTH, MIN_GAIN, PLATEAU = 0.85, 8, 3, 0.005, 2
BASE = {"minutes": 120, "width": 16, "chip": 192, "batch": 12, "pos": 0.3, "boxes": 4, "lr": 2e-3, "pw": 4.0, "tta": 0,
        "bridge": 0.0}
MOVES = [
    ("more training areas", lambda c: {**c, "boxes": min(8, c["boxes"] * 2)}),
    ("train longer", lambda c: {**c, "minutes": min(280, round(c["minutes"] * 1.6))}),
    ("bridge short gaps", lambda c: {**c, "bridge": min(8.0, c["bridge"] + 4.0)}),
    ("wider network", lambda c: {**c, "width": min(32, c["width"] + 8)}),
    ("bigger view per chip", lambda c: {**c, "chip": min(320, c["chip"] + 64)}),
    ("flip averaging", lambda c: {**c, "tta": 1}),
    ("wider kerb label", lambda c: {**c, "pos": min(0.6, round(c["pos"] + 0.15, 2))}),
    ("narrower kerb label", lambda c: {**c, "pos": max(0.2, round(c["pos"] - 0.1, 2))}),
    ("weight kerbs more", lambda c: {**c, "pw": min(16.0, c["pw"] * 2)}),
    ("lower learning rate", lambda c: {**c, "lr": c["lr"] / 2}),
]


def key(c):
    return json.dumps(c, sort_keys=True)


def load(p):
    if os.path.exists(p):
        return json.load(open(p))
    return {"round": 0, "best": None, "tried": [], "history": [], "stale": 0, "status": "running"}


def plan(a):
    st = load(a[0]); base = st["best"]["cfg"] if st["best"] else BASE
    out = [] if st["best"] else [{"name": "starting settings", "cfg": base}]
    for name, f in MOVES:
        c = f(base)
        if len(out) >= WIDTH:
            break
        if c != base and [name, key(base)] not in st["tried"]:
            out.append({"name": name, "cfg": c})
    print(json.dumps([{**v, "id": i, "cfg_json": json.dumps(v["cfg"])} for i, v in enumerate(out)]))


def score(r):
    return r.get("score") or float(sum(2 * v["recall"] * v["precision"] / max(v["recall"] + v["precision"], 1e-6)
                                       for v in r["boxes"].values()) / max(len(r["boxes"]), 1))


def met(r):
    return all(v.get("recall", 0) >= TARGET and (v.get("offset_median_m") or 9) <= 0.3 and v.get("precision", 0) >= 0.7
               for v in r["boxes"].values())


def record(a):
    sp, lp, rd = a
    st = load(sp); st["round"] += 1; base = st["best"]["cfg"] if st["best"] else BASE
    res = []
    for p in sorted(glob.glob(f"{rd}/**/result.json", recursive=True)):
        r = json.load(open(p)); r.update(json.load(open(os.path.join(os.path.dirname(p), "name.json"))))
        res.append(r)
    new = not os.path.exists(lp)
    with open(lp, "a") as f:
        if new:
            f.write("# Kerb photo model: automatic tuning log\n\nfound / precise / offset per held-out box at the chosen threshold "
                    "(1 m tolerance). Bar: 85% found, 0.3 m offset, every box.\n\n"
                    "| round | change tried | mean found | Mona Vale | Newport | Parramatta | threshold | minutes |\n"
                    "|---|---|---|---|---|---|---|---|\n")
        for r in res:
            b = r["boxes"]
            cell = lambda n: (f"{b[n]['recall']:.0%} / {b[n]['precision']:.0%} / {b[n].get('offset_median_m')} m"
                              if n in b and b[n] else "-")
            f.write(f"| {st['round']} | {r['name']} | {r['mean_recall']:.1%} | {cell('monavale')} | {cell('newport')} | "
                    f"{cell('parramatta')} | {r['thresh']} | {r.get('minutes')} |\n")
    for r in res:
        if r["name"] != "starting settings":
            st["tried"].append([r["name"], key(base)])
        st["history"].append({"round": st["round"], "name": r["name"], "mean_recall": r["mean_recall"], "cfg": r["cfg"]})
    top = max(res, key=score) if res else None
    old = score(st["best"]) if st["best"] else 0
    if top and (not st["best"] or score(top) >= old + MIN_GAIN):
        st["best"] = {"round": st["round"], "name": top["name"], "cfg": top["cfg"], "mean_recall": top["mean_recall"],
                      "score": round(score(top), 3),
                      "thresh": top["thresh"], "boxes": top["boxes"], "run": os.environ.get("GITHUB_RUN_ID"),
                      "artifact": top.get("artifact")}
        st["stale"] = 0
    else:
        st["stale"] += 1
    why = None
    if st["best"] and met(st["best"]):
        why = "target reached"
    elif st["round"] >= MAX_ROUNDS:
        why = f"round cap ({MAX_ROUNDS}) reached"
    elif st["stale"] >= PLATEAU:
        why = f"plateau ({PLATEAU} rounds without a gain of {MIN_GAIN:.1%})"
    elif not res:
        why = "no results this round (jobs failed)"
    else:
        json.dump(st, open(sp, "w"), indent=1)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            plan([sp])
        if not json.loads(buf.getvalue()):
            why = "every change tried"
    if why:
        st["status"] = "stopped: " + why
        b = st["best"]
        with open(lp, "a") as f:
            f.write(f"\n**Stopped after round {st['round']}: {why}.** Best: {b['name']} (round {b['round']}), mean found "
                    f"{b['mean_recall']:.1%}, settings `{key(b['cfg'])}`, model: run {b['run']} artifact {b.get('artifact')}.\n")
    json.dump(st, open(sp, "w"), indent=1)
    print("stop: " + why if why else "continue")


if __name__ == "__main__":
    {"plan": plan, "record": record}[sys.argv[1]](sys.argv[2:])
