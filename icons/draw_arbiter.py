"""The Arbiter app icon: a cream film reel cradled by festival-award laurels on a
harvest-gold tile (a ranked movie list, crowned). Owner-approved 2026-09-23
(mock round 5 "C2": B2's low-cradle laurels, reel in place of the film frame).

    py -3.11 icons\draw_arbiter.py      # writes icons/arbiter.png
"""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

OUT = Path(__file__).resolve().parent / "arbiter.png"
S = 512
R = S // 5
HARVEST = [(0, (238, 170, 86)), (0.62, (196, 112, 58)), (1, (92, 74, 40))]
CREAM = (250, 238, 214)
HOLE = (150, 86, 44)
LAURELS = dict(radius=205, cy=300, a0=262, a1=150, leaf_len=80, leaf_w=32)
REEL = (256, 240, 140)   # centre x, centre y, radius; clears the laurels by a hair
FILL = 0.8               # the artwork's share of the tile


def gradient(stops):
    img = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(img)
    for y in range(S):
        t = y / (S - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / (p1 - p0) if p1 > p0 else 0
                d.line([(0, y), (S, y)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3)) + (255,))
                break
    return img


def layer():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def leaf(art, x, y, angle_deg, length, width, color):
    """One laurel leaf: a pointed ellipse rotated to `angle_deg` (0 = pointing right)."""
    lw = layer()
    d = ImageDraw.Draw(lw)
    cx, cy = S // 2, S // 2
    d.polygon([(cx - length / 2, cy), (cx - length * 0.1, cy - width / 2), (cx + length / 2, cy),
               (cx - length * 0.1, cy + width / 2)], fill=color)
    d.ellipse((cx - length * 0.42, cy - width / 2, cx + length * 0.2, cy + width / 2), fill=color)
    lw = lw.rotate(angle_deg, center=(cx, cy), resample=Image.BICUBIC)
    art.alpha_composite(lw, (int(x - cx), int(y - cy)))


def laurel_branch(art, side, color, cx=256, cy=270, radius=175, a0=258, a1=128, n=7, leaf_len=78, leaf_w=30,
                  stem_w=9):
    """An arc from the bottom up one side, paired leaves tapering toward a tip leaf.
    side=-1 left, +1 right (mirror)."""
    d = ImageDraw.Draw(art)
    pts = []
    for i in range(60):
        a = math.radians(a0 + (a1 - a0) * i / 59)
        px, py = cx + radius * math.cos(a), cy - radius * math.sin(a)
        pts.append((2 * cx - px if side > 0 else px, py))
    d.line(pts, fill=color, width=stem_w, joint="curve")
    sign = (a1 - a0) / abs(a1 - a0)
    for k in range(n):
        t = (k + 0.6) / (n + 0.4)
        a = math.radians(a0 + (a1 - a0) * t)
        px, py = cx + radius * math.cos(a), cy - radius * math.sin(a)
        tx, ty = -math.sin(a) * sign, -math.cos(a) * sign
        if side > 0:
            px, tx = 2 * cx - px, -tx
        base = math.degrees(math.atan2(-ty, tx))
        scale = 1.0 - 0.35 * t
        for off in (38, -38):
            ang = base + off
            lx = px + math.cos(math.radians(ang)) * leaf_len * 0.45 * scale
            ly = py - math.sin(math.radians(ang)) * leaf_len * 0.45 * scale
            leaf(art, lx, ly, ang, leaf_len * scale, leaf_w * scale, color)
    a = math.radians(a1)
    px, py = cx + radius * math.cos(a), cy - radius * math.sin(a)
    tx, ty = -math.sin(a), -math.cos(a)
    if side > 0:
        px, tx = 2 * cx - px, -tx
    ang = math.degrees(math.atan2(-ty, tx))
    leaf(art, px + math.cos(math.radians(ang)) * 26, py - math.sin(math.radians(ang)) * 26, ang, 64, 26, color)


def reel(d, cx, cy, r, holes=5):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM)
    hr = r * 0.27
    for i in range(holes):
        a = -math.pi / 2 + i * 2 * math.pi / holes
        x, y = cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55
        d.ellipse((x - hr, y - hr, x + hr, y + hr), fill=HOLE)
    h = r * 0.1
    d.ellipse((cx - h, cy - h, cx + h, cy + h), fill=HOLE)


def layers():
    lau = layer()
    laurel_branch(lau, -1, CREAM, **LAURELS)
    laurel_branch(lau, +1, CREAM, **LAURELS)
    sym = layer()
    reel(ImageDraw.Draw(sym), *REEL)
    return lau, sym


def overlap():
    """Pixels where the reel touches the laurels. Must stay 0 (owner: no overlap)."""
    lau, sym = layers()
    a = lau.split()[3].point(lambda v: 255 if v > 40 else 0)
    b = sym.split()[3].point(lambda v: 255 if v > 40 else 0)
    return ImageChops.multiply(a, b).getbbox() is not None


def render(size=128, square=False):
    """square=True: full-bleed tile (apple-touch / maskable), the OS rounds it."""
    t = gradient(HARVEST)
    lau, sym = layers()
    art = layer()
    art.alpha_composite(lau)
    art.alpha_composite(sym)
    art = art.crop(art.getbbox())
    k = S * FILL / max(art.size)
    art = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)
    t.alpha_composite(art, ((S - art.width) // 2, (S - art.height) // 2))
    if not square:
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)
        out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        out.paste(t, (0, 0), mask)
        t = out
    return t.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    assert not overlap(), "reel touches the laurels"
    render().save(OUT)
    print("wrote", OUT)
