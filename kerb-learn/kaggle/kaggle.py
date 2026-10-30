#!/usr/bin/env python3
"""Run the kerb-learn loop on Kaggle's free GPU (30 h a week) instead of GitHub runners. Needs KAGGLE_KEY (or KAGGLE_API_TOKEN) in
the environment; the key is never printed or written to a file. Code is pulled from GitHub at the given commit.

Usage (from the repo root):
  python3 kerb-learn/kaggle/kaggle.py data <commit> [com]  (CPU notebook openfetch-kerb-data[-com]: builds the photo and kerb cache once)
  python3 kerb-learn/kaggle/kaggle.py round <commit>    (GPU notebook openfetch-kerb-train: the variants kerbloop.py plan names)
  python3 kerb-learn/kaggle/kaggle.py status [data|train]
  python3 kerb-learn/kaggle/kaggle.py record            (downloads the round, kerbloop.py record, new best model to the dataset)
"""
import sys, os, json, subprocess, shutil, glob

os.environ.setdefault("KAGGLE_API_TOKEN", os.environ.get("KAGGLE_KEY", ""))
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "../.."); USER = "jackylam1999"
STATE, LOG = f"{ROOT}/kerb-learn/state.json", f"{ROOT}/kerb-learn/LOG.md"
LOOP = f"{ROOT}/openfetch/tools/derive/kerbloop.py"
CACHES = ("data", "data-com", "data-villawood")  # NSW, Melbourne, and the box the first NSW cache missed
WORK = os.environ.get("KERB_KAGGLE_WORK", "/tmp/kerb-kaggle")


def kg(*a):
    return subprocess.run(["kaggle", *a], capture_output=True, text=True)


def push(slug, script, gpu, sources):
    d = f"{WORK}/{slug}"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    open(f"{d}/{slug}.py", "w").write(script)
    json.dump({"id": f"{USER}/{slug}", "title": slug.replace("-", " "), "code_file": f"{slug}.py", "language": "python",
               "kernel_type": "script", "is_private": "true", "enable_gpu": str(gpu).lower(), "enable_tpu": "false",
               "enable_internet": "true", "machine_shape": "NvidiaTeslaT4" if gpu else "", "competition_sources": [],
               "model_sources": [], **sources}, open(f"{d}/kernel-metadata.json", "w"))
    r = kg("kernels", "push", "-p", d); print((r.stdout + r.stderr).strip()[-400:])


def data(a):
    only = a[1] if len(a) > 1 else ""  # e.g. com: a separate cache notebook for those councils
    s = open(f"{HERE}/data_kernel.py").read().replace("__REF__", a[0]).replace("__ONLY__", only)
    push("openfetch-kerb-data" + (f"-{only.replace(',', '-')}" if only else ""), s, False, {"dataset_sources": [], "kernel_sources": []})


def round_(a):
    st = json.load(open(STATE))
    p = json.loads(subprocess.run([sys.executable, LOOP, "plan", STATE], capture_output=True, text=True, check=True).stdout)
    print("variants:", ", ".join(v["name"] for v in p["variants"]))
    s = (open(f"{HERE}/train_kernel.py").read().replace("__REF__", a[0]).replace("__ROUND__", str(st["round"]))
         .replace("__VARIANTS__", json.dumps(p["variants"])))
    push("openfetch-kerb-train", s, True, {"dataset_sources": [f"{USER}/openfetch-kerb-best"],
                                            "kernel_sources": [f"{USER}/openfetch-kerb-{k}" for k in CACHES]})


def status(a):
    r = kg("kernels", "status", f"{USER}/openfetch-kerb-{a[0] if a else 'train'}"); print((r.stdout + r.stderr).strip())


def record(a):
    d = f"{WORK}/out"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    r = kg("kernels", "output", f"{USER}/openfetch-kerb-train", "-p", d)
    if r.returncode:
        print(r.stderr[-400:]); return
    print(subprocess.run([sys.executable, LOOP, "record", STATE, LOG, d], capture_output=True, text=True).stdout.strip())
    b = json.load(open(STATE))["best"]
    m = glob.glob(f"{d}/{b['artifact'].split('-')[-1]}/model.pt") if b and b["artifact"].startswith("kaggle-") else []
    if m:
        u = f"{WORK}/best"; shutil.rmtree(u, ignore_errors=True); os.makedirs(u); shutil.copy(m[0], u)
        json.dump({"id": f"{USER}/openfetch-kerb-best"}, open(f"{u}/dataset-metadata.json", "w"))
        r = kg("datasets", "version", "-p", u, "-m", f"best after round {b['round']}: {b['name']}")
        print("best model uploaded" if not r.returncode else r.stderr[-300:])


if __name__ == "__main__":
    {"data": data, "round": round_, "status": status, "record": record}[sys.argv[1]](sys.argv[2:])
