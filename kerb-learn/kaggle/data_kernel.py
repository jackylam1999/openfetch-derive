# Kaggle CPU notebook: fetch every box in kerb-learn/boxes.json (photo as JPEG, council kerbs, lots, LGA, roads, water) into
# /kaggle/working/kp. Its output is the data cache the GPU notebook mounts. Pushed by kerb-learn/kaggle/kaggle.py data.
import subprocess, glob, os
REF = "__REF__"
subprocess.run(f"git clone -q https://github.com/jackylam1999/openfetch-derive /kaggle/temp/r && cd /kaggle/temp/r && git checkout -q {REF}",
               shell=True, check=True)
os.makedirs("/kaggle/working/kp", exist_ok=True)
for i in range(4):  # the photo server sometimes answers 500 for a while; data() skips what is already fetched
    r = subprocess.run("cd /kaggle/temp/r/openfetch/tools/derive && python3 kerblearn.py data /kaggle/working/kp", shell=True)
    if r.returncode == 0:
        break
    subprocess.run("sleep 120", shell=True)
for f in glob.glob("/kaggle/working/kp/*"):
    if not f.endswith((".jpg", ".json", ".geojson")):
        os.remove(f)
print("files", len(os.listdir("/kaggle/working/kp")), "exit", r.returncode)
subprocess.run("du -sh /kaggle/working/kp; cat /kaggle/working/kp/*_align.json", shell=True)
