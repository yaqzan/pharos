"""The Archivist app icon ("The Pantheon"): a brass temple on near-black, with
Archivist's brass diamond in the pediment. Solid shapes only, no thin lines,
so it holds up at 29-40px. Centred by its real bounds. Owner-approved
2026-09-23 (mock round 5, "b").

    py -3.11 icons\draw_archivist.py      # writes icons/archivist.png
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 512          # drawn at 4x, downsampled for clean edges
R = S // 5
FILL = 0.74      # temple's longest side as a share of the tile
OUT = Path(__file__).resolve().parent / "archivist.png"
BRASS, BRASS_HI, BRASS_SH = (201, 162, 94), (228, 194, 128), (160, 122, 64)
VOID = (18, 15, 12)


def bg():
    img = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(img)
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(a + (b - a) * t) for a, b in zip((30, 25, 19), (11, 10, 9)))
        d.line([(0, y), (S, y)], fill=c + (255,))
    return img


def rounded(img):
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def temple(img, *, n, windows, x0=104, x1=408, peak=96, roof=190, fz=48, col=150, steps=2,
           ornament=True, medallion=True, shading=True, interior=True):
    d = ImageDraw.Draw(img)
    cx = (x0 + x1) / 2
    if ornament:
        d.polygon([(cx, peak - 36), (cx + 18, peak - 12), (cx, peak + 4), (cx - 18, peak - 12)], fill=BRASS_HI)
    d.polygon([(x0 - 14, roof), (cx, peak), (x1 + 14, roof)], fill=BRASS)
    if medallion:
        r = 17
        cy = roof - 34
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=VOID)
    y = roof + 10                                     # gap line under the roof
    d.rectangle((x0 - 6, y, x1 + 6, y + fz), fill=BRASS_HI)   # frieze band
    if windows:
        ww = (x1 - x0 - 40) / (windows * 2 - 1)
        for i in range(windows):
            wx = x0 + 20 + i * 2 * ww
            d.rectangle((wx, y + fz * 0.28, wx + ww, y + fz * 0.72), fill=VOID)
    ct = y + fz + 10
    cb = ct + col
    if interior:
        d.rectangle((x0 + 8, ct, x1 - 8, cb), fill=VOID)
    span = x1 - x0 - 16
    cw = span / (n * 2 - 1) * 1.25
    gap = (span - n * cw) / (n - 1)
    for i in range(n):
        x = x0 + 8 + i * (cw + gap)
        d.rectangle((x, ct, x + cw, cb), fill=BRASS)
        if shading:
            d.rectangle((x + cw * 0.62, ct, x + cw, cb), fill=BRASS_SH)
    y = cb + 10
    for k in range(steps):
        pad = 10 + k * 22
        d.rectangle((x0 - pad, y, x1 + pad, y + 20), fill=BRASS_HI if k == 0 else BRASS)
        y += 28
    return img


def render(size=128):
    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    temple(art, n=4, windows=3, ornament=False, medallion=False, fz=44, col=156)
    cx, cy, r = (104 + 408) / 2, 190 - 36, 20       # the diamond, in the pediment
    ImageDraw.Draw(art).polygon([(cx, cy - r), (cx + r * 0.8, cy), (cx, cy + r), (cx - r * 0.8, cy)], fill=VOID)
    art = art.crop(art.getbbox())
    k = (S * FILL) / max(art.size)
    art = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)
    tile = bg()
    tile.alpha_composite(art, ((S - art.width) // 2, (S - art.height) // 2 - int(S * 0.015)))
    return rounded(tile).resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    render().save(OUT)
    print("icon archivist ->", OUT)
