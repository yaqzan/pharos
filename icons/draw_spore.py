"""The Spore app icon: an Obsidian-style faceted crystal mushroom with a smaller
crystal one beside it (they grow in clusters), on a deep violet night.
Spore's own palette, deliberately apart from the gold/dusk family.
Owner-approved 2026-09-23 (mock round 2 "f", kept as-is in round 3 "1").

    py -3.11 icons\draw_spore.py      # writes icons/spore.png
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "spore.png"
S = 512
R = S // 5
LIGHT = (-0.55, -0.8)    # light from top-left
BASE = (124, 92, 232)    # Obsidian-ish violet
STALK = (236, 226, 208)
NIGHT = [(0, (30, 24, 52)), (1, (12, 10, 20))]


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


def rounded(img):
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def layer():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def shade(color, tri, light=LIGHT, strength=0.55):
    """Flat-shade a facet: brighter the more its centroid-from-apex direction faces the light."""
    (x0, y0), (x1, y1), (x2, y2) = tri
    # facet 'normal' approximated by the direction of the edge midpoint from the apex
    mx, my = (x1 + x2) / 2 - x0, (y1 + y2) / 2 - y0
    n = math.hypot(mx, my) or 1
    dot = (mx / n) * light[0] + (my / n) * light[1]
    f = 1 + strength * dot
    return tuple(max(0, min(255, int(c * f))) for c in color)


def faceted_dome(d, cx, base_y, w, h, apex=(0.0, 0.0), n=6, color=BASE, lip=True, jag=None, strength=0.55):
    """A cap: a dome outline of n+1 points, fanned from an apex point into facets."""
    pts = []
    for i in range(n + 1):
        a = math.pi - math.pi * i / n
        j = jag[i] if jag else 1.0
        pts.append((cx + (w / 2) * math.cos(a) * j, base_y - h * math.sin(a) * j))
    ax, ay = cx + apex[0] * w, base_y - h * (0.62 + apex[1])
    for i in range(n):
        tri = ((ax, ay), pts[i], pts[i + 1])
        d.polygon(tri, fill=shade(color, tri, strength=strength))
    # base triangle closing the dome from the apex to the rim
    d.polygon([(ax, ay), pts[-1], pts[0]], fill=shade(color, ((ax, ay), (cx, base_y + 40), (cx, base_y + 40)), strength=0.2))
    if lip:
        d.polygon([pts[0], pts[-1], (pts[-1][0] - w * 0.08, base_y + h * 0.1), (pts[0][0] + w * 0.08, base_y + h * 0.1)],
                  fill=tuple(int(c * 0.55) for c in color))
    return pts


def faceted_stalk(d, cx, top, bot, w, color=STALK, crystal=False):
    if not crystal:
        d.rounded_rectangle((cx - w / 2, top, cx + w / 2, bot), radius=w * 0.4, fill=color)
        d.rectangle((cx + w * 0.1, top, cx + w / 2 - 4, bot - w * 0.3), fill=tuple(int(c * 0.86) for c in color))
        return
    mid = (top + bot) / 2
    d.polygon([(cx - w * 0.45, top), (cx, top), (cx - w * 0.1, mid), (cx - w * 0.55, bot)], fill=tuple(min(255, int(c * 1.06)) for c in color))
    d.polygon([(cx, top), (cx + w * 0.45, top), (cx + w * 0.55, bot), (cx - w * 0.1, mid)], fill=tuple(int(c * 0.82) for c in color))
    d.polygon([(cx - w * 0.1, mid), (cx + w * 0.55, bot), (cx - w * 0.55, bot)], fill=tuple(int(c * 0.93) for c in color))


def centred(art, t, fill=0.72, dy=0.0):
    a = art.crop(art.getbbox())
    k = (S * fill) / max(a.size)
    a = a.resize((int(a.width * k), int(a.height * k)), Image.LANCZOS)
    t.alpha_composite(a, ((S - a.width) // 2, (S - a.height) // 2 + int(S * dy)))


def render(size=128):
    t = gradient(NIGHT)
    art = layer()
    d = ImageDraw.Draw(art)
    faceted_stalk(d, 226, 250, 440, 58)
    faceted_dome(d, 226, 262, 300, 180, apex=(-0.08, 0.05), n=7)
    faceted_stalk(d, 392, 360, 440, 34)
    faceted_dome(d, 392, 368, 150, 90, apex=(-0.1, 0.05), n=5, color=(150, 118, 244))
    centred(art, t, fill=0.76)
    return rounded(t).resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    render().save(OUT)
    print("icon spore ->", OUT)
