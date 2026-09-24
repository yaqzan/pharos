"""The Gleaner app icon: a white YouTube-style badge on red whose play triangle
is solid at the top and breaks into lines of text lower down (a video turning
into a transcript). Owner-approved 2026-09-23 (mock round 4 "H3").

    py -3.11 icons\draw_gleaner.py      # writes icons/gleaner.png
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "gleaner.png"
S = 512
R = S // 5
BG = [(0, (236, 38, 34)), (1, (168, 14, 18))]
WHITE = (255, 250, 246)
RED = (224, 30, 28)
FILL = 0.8   # the badge's share of the tile width


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


def art():
    a = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(a)
    w, h = 380, 270
    d.rounded_rectangle((256 - w / 2, 256 - h / 2, 256 + w / 2, 256 + h / 2), radius=h * 0.28, fill=WHITE)
    x0, cy, th, tw = 208, 256, 180, 150
    d.polygon([(x0, cy - th / 2), (x0 + tw, cy), (x0, cy)], fill=RED)       # solid upper half
    for i in range(3):                                                    # lower half as text lines
        y = cy + 14 + i * 26
        frac = 1 - (y - cy) / (th / 2)
        d.rounded_rectangle((x0, y - 9, x0 + tw * frac, y + 9), radius=9, fill=RED)
    return a


def render(size=128, square=False):
    """square=True: full-bleed tile (apple-touch / maskable), the OS rounds it."""
    t = gradient(BG)
    a = art()
    a = a.crop(a.getbbox())
    k = S * FILL / max(a.size)
    a = a.resize((int(a.width * k), int(a.height * k)), Image.LANCZOS)
    t.alpha_composite(a, ((S - a.width) // 2, (S - a.height) // 2))
    if not square:
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)
        out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        out.paste(t, (0, 0), mask)
        t = out
    return t.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    render().save(OUT)
    print("wrote", OUT)
