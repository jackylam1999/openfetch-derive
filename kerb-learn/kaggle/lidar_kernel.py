# Kaggle CPU notebook: ELVIS NSW LiDAR orders (zip links, CC BY 4.0 Spatial Services) -> one ground height grid per kerb box
# (0.25 m cells, mean height of ground points, NaN where none) for the two-judge label check. Pushed by kaggle.py lidar.
import subprocess, os, json, glob, zipfile, numpy as np
REF, LINKS = "__REF__", json.loads(r'''__LINKS__''')
sh = lambda c: subprocess.run(c, shell=True, check=False)
sh("pip install -q laspy[lazrs]")
import laspy
sh(f"git clone -q https://github.com/jackylam1999/openfetch-derive /kaggle/temp/r && cd /kaggle/temp/r && git checkout -q {REF}")
B = [b for b in json.load(open("/kaggle/temp/r/kerb-learn/boxes.json"))["boxes"] if b["council"] != "com"]
G, W = 0.25, 1000.0; n = int(W / G); acc = {}
os.makedirs("/kaggle/temp/z", exist_ok=True); os.makedirs("/kaggle/working/lidar", exist_ok=True)
for u in LINKS:
    z = f"/kaggle/temp/z/{os.path.basename(u)}"; sh(f"curl -sS -o {z} {u}")
    with zipfile.ZipFile(z) as f:
        for m in f.namelist():
            if not m.lower().endswith((".laz", ".las")):
                continue
            p = f.extract(m, "/kaggle/temp/x")
            with laspy.open(p) as r:
                h = r.header; x0, y0, x1, y1 = h.mins[0], h.mins[1], h.maxs[0], h.maxs[1]
                hit = [b for b in B if b["x"] < x1 and b["x"] + W > x0 and b["y"] < y1 and b["y"] + W > y0]
                if hit:
                    for ch in r.chunk_iterator(5_000_000):
                        g = ch.classification == 2; x, y, zz = np.asarray(ch.x)[g], np.asarray(ch.y)[g], np.asarray(ch.z)[g]
                        for b in hit:
                            c = ((x - b["x"]) / G).astype(int); rr = n - 1 - ((y - b["y"]) / G).astype(int)
                            k = (c >= 0) & (c < n) & (rr >= 0) & (rr < n)
                            s, t = acc.setdefault(b["name"], (np.zeros(n * n), np.zeros(n * n)))
                            i = rr[k] * n + c[k]; np.add.at(s, i, zz[k]); np.add.at(t, i, 1)
                print(os.path.basename(m), [b["name"] for b in hit], flush=True)
            os.remove(p)
    os.remove(z)
for nm, (s, t) in acc.items():
    d = np.where(t > 0, s / np.maximum(t, 1), np.nan).reshape(n, n).astype(np.float32)
    np.save(f"/kaggle/working/lidar/{nm}_dem.npy", d)
    print(nm, "ground cells filled", round(float(np.isfinite(d).mean()), 3), "points per m2", round(float(t.sum() / W / W), 2))
