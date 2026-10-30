#!/usr/bin/env python3
"""Round planner and recorder for the kerb photo model (kerblearn.py, kerb-learn workflows), method v2 (docs/handoffs/kerbs-method.md).

Usage:
  python3 kerbloop.py plan state.json              (prints {"variants": [...], "best_run", "best_artifact"} for the round)
  python3 kerbloop.py record state.json log.md results/   (adds the round to the log and state, prints "continue" or "stop: <why>")
  python3 kerbloop.py brief state.json             (at most 25 lines: all a thread reads each round)

Every round trains a control (the best model, same settings, trained on) beside at most two single changes from kerb-learn/queue.json
(read at each plan, edited while a run is live; code waits for a round boundary). A change is kept only if its scenario score beats
the control by more than min_gain (twice the spread of the noise round) and the worst held-out box does not fall. Round 0 trains the
control three times with different seeds to measure that spread. Stops at the target on every held-out box, two rounds within noise
of the control, or MAX_ROUNDS.
"""
import sys, os, json, glob

TARGET, MAX_ROUNDS, PLATEAU = 0.85, 10, 2
HOLD = ("monavale", "newport", "parramatta", "paddington")
QUEUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../kerb-learn/queue.json")


CONTROL = {"minutes": 150, "lr": 3e-4, "mine": 0.0, "focus": ""}
SEEDS = (11, 22, 33)


def load(p):
    if os.path.exists(p):
        return json.load(open(p))
    return {"round": 0, "best": None, "history": [], "done": [], "stale": 0, "status": "running", "min_gain": None, "takeaways": []}


def queue(st):
    q = json.load(open(QUEUE)) if os.path.exists(QUEUE) else []
    return [x for x in q if x["name"] not in st["done"]]


def plan(a):
    st = load(a[0]); b = st["best"]
    base = {**b["cfg"], **CONTROL} if b else {**CONTROL, "encoder": "resnet34", "chip": 256, "batch": 7, "skel": 1.0, "context": 1}
    if st["min_gain"] is None:
        vs = [(f"noise seed {k}", {**base, "seed": k}) for k in SEEDS]
    else:
        vs = [("control", {**base, "seed": 11})] + [(x["name"], {**base, **x["cfg"], "seed": 11}) for x in queue(st)[:2]]
    print(json.dumps({"variants": [{"name": n, "id": i, "cfg_json": json.dumps(c)} for i, (n, c) in enumerate(vs)],
                      "best_run": str(b["run"]) if b else "", "best_artifact": b["artifact"] if b else ""}))


def met(r):
    b = {n: r["boxes"].get(n) or {} for n in HOLD}
    return all(b[n].get("recall", 0) >= TARGET and (b[n].get("offset_median_m") or 9) <= 0.3 and b[n].get("precision", 0) >= 0.7
               for n in HOLD if n in r["boxes"])


def table(f, rs):
    f.write("| model | scenario score | worst held-out F1 | 250 m sites ok | " + " | ".join(rs[0]["scenarios"]) + " |\n|---|---|---|---|" +
            "---|" * len(rs[0]["scenarios"]) + "\n")
    for r in rs:
        f.write(f"| {r['name']} | {r['scenario_score']:.3f} | {r['worst_hold']:.3f} | {r['site_share']:.0%} | " +
                " | ".join(f"{v:.3f}" for v in r["scenarios"].values()) + " |\n")


def row(r):
    return "; ".join(f"{n} {b['recall']:.0%}/{b['precision']:.0%}/{b.get('offset_median_m')} m" for n, b in r["boxes"].items() if b.get("role") == "hold")


def record(a):
    sp, lp, rd = a
    st = load(sp); prev = st["best"]
    res = []
    for p in sorted(glob.glob(f"{rd}/**/result.json", recursive=True)):
        r = json.load(open(p)); r.update(json.load(open(os.path.join(os.path.dirname(p), "name.json")))); res.append(r)
    res.sort(key=lambda r: r["name"])
    if not res:
        st["status"] = "stopped: no results this round (jobs failed)"
        json.dump(st, open(sp, "w"), indent=1); print(st["status"]); return
    st["round"] += 1
    best = lambda rs: max(rs, key=lambda r: r["scenario_score"])
    if st["min_gain"] is None:
        sc = [r["scenario_score"] for r in res]; st["min_gain"] = round(max(0.005, max(sc) - min(sc)), 3)
        top, ctl, kept = best(res), None, []
        take = (f"Round 0. Question: how much does the score move when nothing changes? Three seeds: {', '.join(f'{x:.3f}' for x in sc)}. "
                f"Noise floor {max(sc) - min(sc):.3f}; a change must beat the control by {st['min_gain']} from now on.")
    else:
        ctl = next(r for r in res if r["name"] == "control"); ch = [r for r in res if r is not ctl]
        kept = [r for r in ch if r["scenario_score"] > ctl["scenario_score"] + st["min_gain"] and r["worst_hold"] >= ctl["worst_hold"] - st["min_gain"]]
        top = best(kept + [ctl])
        q = queue({**st, "done": st["done"] + [r["name"] for r in ch]})
        verdicts = "; ".join(f"{r['name']} {r['scenario_score']:.3f} ({'kept' if r in kept else 'within noise' if r['scenario_score'] > ctl['scenario_score'] - st['min_gain'] else 'dropped'})" for r in ch)
        moved = max(top["scenarios"], key=lambda k: top["scenarios"][k] - ctl["scenarios"][k]) if top is not ctl else "none"
        take = (f"Round {st['round']}. Question: " + "; ".join(f"does {r['name']} raise the scenario score?" for r in ch) +
                f"\nControl: {ctl['scenario_score']:.3f} (noise +-{st['min_gain']}). Changes: {verdicts}." +
                f"\nLearnt: most movement in scenario '{moved}'; site share {top['site_share']:.0%}, worst held-out F1 {top['worst_hold']:.3f}." +
                f"\nNext: {q[0]['name'] + ' (' + q[0].get('why', '') + ')' if q else 'queue empty, add the next change to kerb-learn/queue.json'}.")
        st["stale"] = 0 if kept else st["stale"] + 1
        st["done"] += [r["name"] for r in ch]
    new = not os.path.exists(lp) or os.path.getsize(lp) == 0
    with open(lp, "a") as f:
        if new:
            f.write("# Kerb photo model: log (method v2)\n\nScenario score = mean over scenarios of the mean box F1 (found and precise within 1 m). "
                    "Site share = share of 250 m tiles with 85%+ found and median offset 0.3 m or less.\n")
        f.write(f"\n## Round {st['round']}\n\n"); table(f, res)
        f.write("\nHeld-out (found/precise/median offset): " + row(top) + "\n\n```\n" + take + "\n```\n")
    st["best"] = {k: top.get(k) for k in ("name", "cfg", "thresh", "scenario_score", "worst_hold", "site_share", "scenarios", "boxes", "artifact", "run")}
    st["best"]["round"] = st["round"]
    st["history"].append({"round": st["round"], "scores": {r["name"]: r["scenario_score"] for r in res}})
    st["takeaways"] = (st["takeaways"] + [take])[-3:]
    why = ("target reached" if met(top) else f"round cap ({MAX_ROUNDS})" if st["round"] > MAX_ROUNDS else
           f"plateau ({PLATEAU} rounds within noise of the control)" if st["stale"] >= PLATEAU else None)
    st["status"] = "stopped: " + why if why else "running"
    json.dump(st, open(sp, "w"), indent=1)
    print("stop: " + why if why else "continue")


def brief(a):
    st = load(a[0]); b = st["best"]
    print(f"Round {st['round']} | {st['status']} | noise floor (min_gain) {st['min_gain']} | stale rounds {st['stale']}/{PLATEAU}")
    if b:
        print(f"Best: {b['name']} (round {b['round']}) scenario score {b['scenario_score']:.3f}, worst held-out F1 {b['worst_hold']:.3f}, "
              f"site share {b['site_share']:.0%}, threshold {b['thresh']}")
        print("Scenarios: " + ", ".join(f"{k} {v:.3f}" for k, v in b["scenarios"].items()))
        for n, x in b["boxes"].items():
            if x.get("role") == "hold":
                print(f"  held-out {n}: found {x['recall']:.0%}, precise {x['precision']:.0%}, offset {x.get('offset_median_m')} m, whole lines {x['whole_lines']:.0%}")
        print(f"Target: found >= {TARGET:.0%}, offset <= 0.3 m, precision >= 70% on every held-out box")
    for t in st["takeaways"][-1:]:
        print("Last round:\n" + t)
    q = queue(st)
    print("Queue: " + (", ".join(x["name"] for x in q[:4]) if q else "empty"))


if __name__ == "__main__":
    {"plan": plan, "record": record, "brief": brief}[sys.argv[1]](sys.argv[2:])
