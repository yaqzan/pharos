"""The Pharos app icon: the three-tier Pharos of Alexandria at dusk, its fire
broadcasting signal rings sideways where a lighthouse beam would be. The tower
runs off the bottom edge. Chosen by the owner 2026-09-23 (mock round 7, "1b").

    py -3.11 icons\draw_pharos.py      # writes icons/pharos.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 512          # drawn at 4x, downsampled for clean edges
R = S // 5
OUT = Path(__file__).resolve().parent / "pharos.png"


def gradient(stops):
    """Vertical gradient through (position 0..1, rgb) stops."""
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


def rounded(img):
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def glow(img, c, radius, color, alpha):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((c[0] - radius, c[1] - radius, c[0] + radius, c[1] + radius), fill=color + (alpha,))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(radius * 0.5)))




def pharos(img, cx, base_y, stone, shade, columns=False, scale=1.0):
    """Three tiers: square base, octagonal middle, round lantern. Returns fire center."""
    d = ImageDraw.Draw(img)
    s = scale
    w1, h1 = 150 * s, 130 * s        # base
    w2, h2 = 96 * s, 88 * s          # octagon
    w3, h3 = 52 * s, 50 * s          # round top
    y0 = base_y
    # plinth / steps (C)
    d.rectangle((cx - w1 * 0.72, y0, cx + w1 * 0.72, y0 + 16 * s), fill=stone)
    d.rectangle((cx - w1 * 0.62, y0 - 12 * s, cx + w1 * 0.62, y0), fill=stone)
    y0 -= 12 * s
    # base tier, slightly tapered
    top1 = y0 - h1
    d.polygon([(cx - w1 / 2, y0), (cx + w1 / 2, y0), (cx + w1 * 0.44, top1), (cx - w1 * 0.44, top1)], fill=stone)
    d.polygon([(cx, y0), (cx + w1 / 2, y0), (cx + w1 * 0.44, top1), (cx, top1)], fill=shade)
    if columns:  # colonnade cut into the base (C)
        n = 4
        span = w1 * 0.74
        gap = span / (n * 2 - 1)
        for i in range(n - 1):
            x = cx - span / 2 + gap * (2 * i + 1)
            d.rectangle((x, top1 + 22 * s, x + gap, y0 - 10 * s), fill=shade if x >= cx else (shade[0] - 18, shade[1] - 18, shade[2] - 18))
    else:
        d.rectangle((cx - 9 * s, y0 - 40 * s, cx + 9 * s, y0 - 4 * s), fill=(shade[0] - 30, shade[1] - 30, shade[2] - 30))
    # cornice
    d.rectangle((cx - w1 * 0.5, top1 - 8 * s, cx + w1 * 0.5, top1), fill=stone)
    # octagon tier
    y1 = top1 - 8 * s
    top2 = y1 - h2
    d.polygon([(cx - w2 / 2, y1), (cx + w2 / 2, y1), (cx + w2 * 0.44, top2), (cx - w2 * 0.44, top2)], fill=stone)
    d.polygon([(cx + w2 * 0.16, y1), (cx + w2 / 2, y1), (cx + w2 * 0.44, top2), (cx + w2 * 0.14, top2)], fill=shade)
    d.rectangle((cx - w2 * 0.5, top2 - 7 * s, cx + w2 * 0.5, top2), fill=stone)
    # round lantern tier
    y2 = top2 - 7 * s
    top3 = y2 - h3
    d.rectangle((cx - w3 / 2, top3, cx + w3 / 2, y2), fill=stone)
    d.rectangle((cx + w3 * 0.1, top3, cx + w3 / 2, y2), fill=shade)
    d.rectangle((cx - w3 * 0.25, top3 + 12 * s, cx + w3 * 0.25, y2 - 8 * s), fill=(255, 214, 140))  # lit window
    # dome
    d.pieslice((cx - w3 / 2 - 4 * s, top3 - 26 * s, cx + w3 / 2 + 4 * s, top3 + 26 * s), 180, 360, fill=stone)
    return (cx, top3 - 34 * s)


def fire(img, c, s=1.0):
    img = glow(img, c, int(70 * s), (255, 190, 90), 210)
    d = ImageDraw.Draw(img)
    r = 16 * s
    d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=(255, 238, 190))
    return img





def hrings(img, c, radii, color, width, spread=26, alphas=(235, 175, 115)):
    """Signal arcs sideways from the fire, where the lighthouse beam would be."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for r, a in zip(radii, alphas):
        box = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
        d.arc(box, 180 - spread, 180 + spread, fill=color + (a,), width=width)   # left
        d.arc(box, -spread, spread, fill=color + (a,), width=width)              # right
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(1.5)))




STONE, SHADE = (248, 236, 210), (212, 192, 162)
DUSK = [(0, (16, 26, 58)), (0.55, (40, 50, 96)), (0.8, (214, 126, 110)), (1, (240, 170, 120))]

# Round 3's #1 and #2 unchanged except: no island, no water; the tower runs off the bottom edge.

def render(size=128):
    scale, fire_y = 1.35, 150
    img = gradient(DUSK)
    c = pharos(img, 256, fire_y + 329 * scale, STONE, SHADE, scale=scale)
    img = hrings(img, c, (84, 138, 192), (255, 208, 132), 17)
    img = fire(img, c, 1.0)
    return rounded(img).resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    render().save(OUT)
    print("icon pharos ->", OUT)
