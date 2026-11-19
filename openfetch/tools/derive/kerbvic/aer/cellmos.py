import sys, os
sys.path.insert(0, sys.argv[1]); from mosaic import mosaic
from PIL import Image
S = sys.argv[1]; M = 64
for l in open(f"{S}/allcells.txt"):
    x, y = map(int, l.split()); fn = f"{S}/kg/mos/m_{x}_{y}.jpg"
    if os.path.exists(fn): continue
    a = mosaic(x * 1000 - M, y * 1000 - M, x * 1000 + 1000 + M, y * 1000 + 1000 + M, 0.25, 19)
    Image.fromarray(a).save(fn + ".tmp.jpg", quality=93); os.rename(fn + ".tmp.jpg", fn); print(x, y, flush=True)
