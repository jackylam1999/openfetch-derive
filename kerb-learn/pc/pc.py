#!/usr/bin/env python3
"""Run kerb-learn rounds on Jacky's PC (RTX 3070 Laptop, 8 GB) instead of Kaggle. Same steps as kaggle/train_kernel.py.
Run from C:\\kerb\\repo with the venv python. Needs a Kaggle key in %USERPROFILE%\\.kaggle (never printed).

  python kerb-learn/pc/pc.py data            (download the photo/kerb/LiDAR caches + best model from Kaggle to C:\\kerb\\data)
  python kerb-learn/pc/pc.py round [side.json] (side.json: own variants instead of the variants kerbloop.py plan names; output C:\\kerb\\out\\<id>, log C:\\kerb\\round.log)
  python kerb-learn/pc/pc.py record          (kerbloop.py record on C:\\kerb\\out; then commit state.json + LOG.md)
"""
import sys, os, json, glob, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(f"{HERE}/../..")
W = os.environ.get("KERB_PC_WORK", r"C:\kerb"); USER = "jackylam1999"
CACHES = ("data", "data-com", "data-villawood", "data-new", "lidar")
STATE, LOG, LOOP = f"{ROOT}/kerb-learn/state.json", f"{ROOT}/kerb-learn/LOG.md", f"{ROOT}/openfetch/tools/derive/kerbloop.py"
D = f"{ROOT}/openfetch/tools/derive"
KG = os.path.join(os.path.dirname(sys.executable), "kaggle")


def data(a):
    for k in CACHES:
        d = f"{W}/data/{k}"; os.makedirs(d, exist_ok=True)
        r = subprocess.run([KG, "kernels", "output", f"{USER}/openfetch-kerb-{k}", "-p", d], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(k, "ok" if not r.returncode else r.stderr[-300:])
    b = f"{W}/data/best"; os.makedirs(b, exist_ok=True)
    r = subprocess.run([KG, "datasets", "download", f"{USER}/openfetch-kerb-best", "-p", b, "--unzip"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("best", "ok" if not r.returncode else r.stderr[-300:])
    kp = f"{W}/kp"; os.makedirs(kp, exist_ok=True)
    for m in glob.glob(f"{W}/data/**/kp/*_meta.json", recursive=True):
        shutil.copytree(os.path.dirname(m), kp, dirs_exist_ok=True)
    for f in glob.glob(f"{W}/data/**/lidar/*_dem.npy", recursive=True):
        shutil.copy(f, kp)
    print("kp files:", len(os.listdir(kp)), "| LiDAR grids:", len(glob.glob(f"{kp}/*_dem.npy")))


def round_(a):
    if a:  # a side run while Kaggle runs the planned round: variants from a JSON file, tagged with its name
        p = json.load(open(a[0])); tag = os.path.splitext(os.path.basename(a[0]))[0]
    else:
        p = json.loads(subprocess.run([sys.executable, LOOP, "plan", STATE], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        tag = str(json.load(open(STATE))["round"])
    best = glob.glob(f"{W}/data/best/**/model.pt", recursive=True)[0]
    shutil.rmtree(f"{W}/out", ignore_errors=True)
    with open(f"{W}/round.log", "a") as log:
        for v in p["variants"]:
            o = f"{W}/out/{v['id']}"; os.makedirs(o)
            json.dump({"name": v["name"], "artifact": f"pc-{tag}-{v['id']}", "run": "pc"}, open(f"{o}/name.json", "w"))
            env = {**os.environ, "KERB_CFG": v["cfg_json"], "KERB_STEPS_PER_MIN": os.environ.get("KERB_STEPS_PER_MIN", "21")}
            print("start", v["name"], file=log, flush=True)
            with open(f"{o}/run.log", "w") as rl:
                subprocess.run([sys.executable, "kerblearn.py", "run", f"{W}/kp", f"{o}/result.json", best], cwd=D, env=env,
                               stderr=rl)
            try:
                shutil.copy(f"{W}/kp/model.pt", o); print("done", v["name"], file=log, flush=True)
            except Exception as e:
                print("failed", v["name"], e, file=log, flush=True)


def record(a):
    print(subprocess.run([sys.executable, LOOP, "record", STATE, LOG, f"{W}/out"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())
    b = json.load(open(STATE))["best"]
    if b and b["artifact"].startswith("pc-"):
        m = f"{W}/out/{b['artifact'].split('-')[-1]}/model.pt"
        if os.path.exists(m):
            os.makedirs(f"{W}/data/best", exist_ok=True); shutil.copy(m, f"{W}/data/best/model.pt"); print("best model kept locally")


if __name__ == "__main__":
    {"data": data, "round": round_, "record": record}[sys.argv[1]](sys.argv[2:])
