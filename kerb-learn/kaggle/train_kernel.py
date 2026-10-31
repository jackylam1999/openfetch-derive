# Kaggle GPU notebook: one kerb-learn round. Each variant fine-tunes the best model (dataset openfetch-kerb-best) with its settings
# (kerblearn.py run) and writes /kaggle/working/<id>/{result.json,name.json,model.pt,run.log,*.png}. Pushed by kaggle.py round.
import subprocess, glob, os, json, shutil
REF, VARIANTS, ROUND = "__REF__", json.loads(r'''__VARIANTS__'''), "__ROUND__"
sh = lambda c: subprocess.run(c, shell=True)
sh(f"git clone -q https://github.com/jackylam1999/openfetch-derive /kaggle/temp/r && cd /kaggle/temp/r && git checkout -q {REF}")
srcs = {os.path.dirname(m) for m in glob.glob("/kaggle/input/**/kp/*_meta.json", recursive=True)}  # NSW and Vic caches
best = glob.glob("/kaggle/input/**/model.pt", recursive=True)[0]
for src in srcs:
    shutil.copytree(src, "/kaggle/temp/kp", dirs_exist_ok=True)
sh("nvidia-smi --query-gpu=name --format=csv,noheader; df -h /kaggle/temp | tail -1")
D = "/kaggle/temp/r/openfetch/tools/derive"
for v in VARIANTS:
    o = f"/kaggle/working/{v['id']}"; os.makedirs(o, exist_ok=True)
    json.dump({"name": v["name"], "artifact": f"kaggle-{ROUND}-{v['id']}", "run": "kaggle"}, open(f"{o}/name.json", "w"))
    env = {**os.environ, "KERB_CFG": v["cfg_json"], "KERB_STEPS_PER_MIN": "21"}
    subprocess.run(f"cd {D} && python3 kerblearn.py run /kaggle/temp/kp {o}/result.json {best} 2> {o}/run.log", shell=True, env=env)
    sh(f"tail -n 5 {o}/run.log")
    try:
        th = json.load(open(f"{o}/result.json"))["thresh"]
        for n in ("monavale", "newport", "parramatta", "paddington", "kensington", "nbcheck", "cbcheck", "wocheck", "olympicpark", "melbcbd"):
            if os.path.exists(f"/kaggle/temp/kp/{n}_{th}.png"):
                shutil.copy(f"/kaggle/temp/kp/{n}_{th}.png", o)
        shutil.copy("/kaggle/temp/kp/model.pt", o)
    except Exception as e:
        print(v["name"], "failed:", e)
