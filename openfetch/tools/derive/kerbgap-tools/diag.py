import sys, json, io, urllib.request, glob
sys.path.insert(0, sys.argv[5])
import kerbaudit as ka
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import box, LineString
x, y, M, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
S = "/tmp/claude-0/-home-user/17bc20c6-45f6-5bb3-8440-d43306115c12/scratchpad/k"
x0, y0, PX = x - M/2, y - M/2, 900
u = (f"https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/export?bbox={x0},{y0},{x0+M},{y0+M}&bboxSR=7856&imageSR=7856&size={PX},{PX}&format=jpg&f=image")
im = Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=120).read())).convert("RGB"); d = ImageDraw.Draw(im); s = PX/M
q = lambda a, b: ((a-x0)*s, (y0+M-b)*s); B = box(x0, y0, x0+M, y0+M)
fhcol = {5: (255,255,255), 6: (200,200,200), 7: (150,150,150)}
for g, fh in ka.load_roads(S + "/in/roads"):
    if g.intersects(B): d.line([q(*c) for c in g.coords], fill=fhcol.get(fh, (255,0,0) if fh <= 4 else (0,0,255)), width=1)
tr = Transformer.from_crs(4326, 7856, always_xy=True).transform
for t in ka.read_kerbs(S + "/in/nsw-traced-raw.json"):
    if len(t) > 1 and LineString(t).intersects(B): d.line([q(*c) for c in t], fill=(0,255,0), width=1)
COL = {"main": (255,140,0), "cross": (255,0,255), "lot": (255,0,0), "unseen": (255,255,0), "small": (150,150,150), "official": (0,128,0)}
cx, cy = int(x//1000), int(y//1000)
for f in glob.glob(f"{S}/cells/*.why.json"):
    for ft in json.load(open(f))["features"]:
        g = LineString(ft["geometry"]["coordinates"])
        if g.intersects(B): d.line([q(*c) for c in g.coords], fill=COL[ft["properties"]["why"]], width=2)
for ft in json.load(open(S + "/gap-v1.json"))["features"]:
    g = LineString([tr(*c) for c in ft["geometry"]["coordinates"]])
    if g.intersects(B): d.line([q(*c) for c in g.coords], fill=(0,255,255), width=3)
im.save(out)
