"""Road-surface segmenter: ResNet-34 encoder (ImageNet weights) with a small U-Net decoder; input 0.25 m RGB aerial."""
import torch, torch.nn as nn, torch.nn.functional as F
def blk(a, b): return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))
class UNet(nn.Module):
    def __init__(s, pretrained=False, arch="resnet34"):
        super().__init__()
        import torchvision
        r = getattr(torchvision.models, arch)(weights="IMAGENET1K_V1" if pretrained else None)
        s.l0 = nn.Sequential(r.conv1, r.bn1, r.relu)            # /2, 64
        s.l1 = nn.Sequential(r.maxpool, r.layer1)                # /4, 64
        s.l2, s.l3, s.l4 = r.layer2, r.layer3, r.layer4           # /8 128, /16 256, /32 512
        s.d4 = blk(512 + 256, 256); s.d3 = blk(256 + 128, 128); s.d2 = blk(128 + 64, 64); s.d1 = blk(64 + 64, 48); s.d0 = blk(48 + 3, 32)
        s.o = nn.Conv2d(32, 1, 1)
    def forward(s, x):
        def up(a, b): return torch.cat([F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False), b], 1)
        e0 = s.l0(x); e1 = s.l1(e0); e2 = s.l2(e1); e3 = s.l3(e2); e4 = s.l4(e3)
        d = s.d4(up(e4, e3)); d = s.d3(up(d, e2)); d = s.d2(up(d, e1)); d = s.d1(up(d, e0)); d = s.d0(up(d, x))
        return s.o(d)
MEAN = torch.tensor([0.485, 0.456, 0.406])[:, None, None]; STD = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
def norm(img):
    t = torch.from_numpy(img).float().permute(2, 0, 1) / 255.0
    return (t - MEAN) / STD
def predict(model, img, tile=512, pad=64):
    model.eval(); H, W = img.shape[:2]; out = torch.zeros(H, W); x = norm(img)
    with torch.no_grad():
        for r in range(0, H, tile):
            for c in range(0, W, tile):
                r0, c0 = max(0, r - pad), max(0, c - pad); r1, c1 = min(H, r + tile + pad), min(W, c + tile + pad)
                p = torch.sigmoid(model(x[None, :, r0:r1, c0:c1]))[0, 0]
                out[r:min(H, r + tile), c:min(W, c + tile)] = p[r - r0:r - r0 + min(tile, H - r), c - c0:c - c0 + min(tile, W - c)]
    return out.numpy()
