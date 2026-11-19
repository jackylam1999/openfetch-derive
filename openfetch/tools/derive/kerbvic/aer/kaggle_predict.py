import glob, os, numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from PIL import Image
dev = "cuda"
def blk(a, b): return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))
class UNet(nn.Module):
    def __init__(s, arch="resnet34"):
        super().__init__(); import torchvision
        r = getattr(torchvision.models, arch)(weights=None)
        s.l0 = nn.Sequential(r.conv1, r.bn1, r.relu); s.l1 = nn.Sequential(r.maxpool, r.layer1); s.l2, s.l3, s.l4 = r.layer2, r.layer3, r.layer4
        s.d4 = blk(512 + 256, 256); s.d3 = blk(256 + 128, 128); s.d2 = blk(128 + 64, 64); s.d1 = blk(64 + 64, 48); s.d0 = blk(48 + 3, 32); s.o = nn.Conv2d(32, 1, 1)
    def forward(s, x):
        def up(a, b): return torch.cat([F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False), b], 1)
        e0 = s.l0(x); e1 = s.l1(e0); e2 = s.l2(e1); e3 = s.l3(e2); e4 = s.l4(e3)
        d = s.d4(up(e4, e3)); d = s.d3(up(d, e2)); d = s.d2(up(d, e1)); d = s.d1(up(d, e0)); d = s.d0(up(d, x)); return s.o(d)
MEAN = torch.tensor([0.485, 0.456, 0.406], device=dev)[:, None, None]; STD = torch.tensor([0.229, 0.224, 0.225], device=dev)[:, None, None]
m = UNet().to(dev); m.load_state_dict(torch.load(glob.glob("/kaggle/input/**/unet.pt", recursive=True)[0], map_location=dev)); m.eval()
os.makedirs("/kaggle/working/prob", exist_ok=True)
for f in sorted(glob.glob("/kaggle/input/**/m_*.jpg", recursive=True)):
    img = np.asarray(Image.open(f).convert("RGB")); H, W = img.shape[:2]
    x = (torch.from_numpy(img).to(dev).permute(2, 0, 1).float() / 255 - MEAN) / STD; out = torch.zeros(H, W, device=dev)
    T, P = 1024, 64
    with torch.no_grad():
        for r in range(0, H, T):
            for c in range(0, W, T):
                r0, c0 = max(0, r - P), max(0, c - P); r1, c1 = min(H, r + T + P), min(W, c + T + P)
                p = torch.sigmoid(m(x[None, :, r0:r1, c0:c1]))[0, 0]
                out[r:min(H, r + T), c:min(W, c + T)] = p[r - r0:r - r0 + min(T, H - r), c - c0:c - c0 + min(T, W - c)]
    q = (out[256:-256, 256:-256].clamp(0, 1) * 255).round().byte().cpu().numpy()
    Image.fromarray(q).save("/kaggle/working/prob/" + os.path.basename(f).replace("m_", "p_").replace(".jpg", ".png")); print(f, q.shape, flush=True)
