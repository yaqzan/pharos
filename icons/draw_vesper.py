"""The Vesper app icon: a gold microphone on a dusk sky, the capsule lit like a
crescent moon (a crescent of shadow across it), a warm glow and a thin halo.
Owner-approved 2026-09-23 (mock round 5, glow step "1_half glow").

PRESETS keeps the glow steps the owner also liked, so switching later is a
one-word change:  py -3.11 icons\draw_vesper.py [preset]
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "vesper.png"
S = 512
R = S // 5
GOLD, GOLD_HI, GOLD_SH = (214, 178, 98), (240, 212, 146), (168, 132, 64)
DUSK = [(0, (18, 22, 52)), (0.7, (46, 40, 92)), (1, (122, 76, 118))]
DARKMIC = (26, 24, 50)
STARS = ((64, 78, 5), (446, 64, 4), (96, 430, 3), (452, 404, 4), (54, 250, 3), (300, 48, 3), (420, 250, 3))

# (glow radius, glow alpha, halo alpha, halo width, halo blur); 0 alpha = off
PRESETS = {
    "half-glow": (150, 80, 60, 6, 3),      # shipped 2026-09-23
    "faint": (120, 50, 55, 6, 2),
    "whisper-ring": (110, 30, 90, 4, 0),
    "ring-only": (0, 0, 100, 4, 0),
}
DEFAULT = "half-glow"


def gradient(stops, size=S):
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / (p1 - p0) if p1 > p0 else 0
                d.line([(0, y), (size, y)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3)) + (255,))
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


def disc(cx, cy, r):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return m


def paint(img, mask, color, alpha=255):
    img.paste(Image.new("RGBA", (S, S), color + (alpha,)), (0, 0), mask)


def sky(stars=True):
    t = gradient(DUSK)
    if stars:
        d = ImageDraw.Draw(t)
        for sx, sy, sr in STARS:
            d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(250, 240, 210, 255))
    return t


def glow(t, cx, cy, r, alpha=130, color=(255, 206, 130)):
    g = layer()
    ImageDraw.Draw(g).ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (alpha,))
    return Image.alpha_composite(t, g.filter(ImageFilter.GaussianBlur(r * 0.42)))


def mic_masks(cx, top, w, h):
    """(capsule, stand) masks for the standard mic glyph."""
    cap = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cap).rounded_rectangle((cx - w / 2, top, cx + w / 2, top + h), radius=w / 2, fill=255)
    st = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(st)
    yw = w * 1.62
    ytop = top + h * 0.35
    d.arc((cx - yw / 2, ytop, cx + yw / 2, ytop + h * 0.95), 0, 180, fill=255, width=int(w * 0.15))
    stem_top = ytop + h * 0.95
    d.rectangle((cx - w * 0.085, stem_top - 6, cx + w * 0.085, stem_top + h * 0.22), fill=255)
    d.rounded_rectangle((cx - w * 0.52, stem_top + h * 0.22, cx + w * 0.52, stem_top + h * 0.22 + w * 0.17),
                        radius=w * 0.085, fill=255)
    return cap, st


def gold_fill(mask, top_c=GOLD_HI, bot_c=GOLD_SH):
    """Mask filled with a top-to-bottom gold gradient (the 'metal')."""
    g = gradient([(0, top_c), (1, bot_c)])
    out = layer()
    out.paste(g, (0, 0), mask)
    return out


def glossy_mic(cx, top, w, h, *, gloss=True, rim=False, dark=False):
    """Round 4 #4's moonlit capsule: a crescent of shadow across the capsule
    (the moon), plus optional specular highlight and rim light."""
    cap, st = mic_masks(cx, top, w, h)
    art = layer()
    if dark:
        paint(art, st, DARKMIC)
        paint(art, cap, DARKMIC)
    else:
        art.alpha_composite(gold_fill(st, GOLD, GOLD_SH))
        art.alpha_composite(gold_fill(cap, GOLD_HI, GOLD))
        # the moon: shadow on the capsule outside a lit disc offset up-left
        shade = ImageChops.multiply(cap, ImageChops.invert(disc(cx - w * 0.2, top + h * 0.37, w * 0.78)))
        paint(art, shade, GOLD_SH)
        # soft terminator between lit and shadow
        soft = shade.filter(ImageFilter.GaussianBlur(10))
        tmp = layer(); paint(tmp, ImageChops.multiply(soft, cap), GOLD_SH, 120)
        art.alpha_composite(tmp)
    if gloss and not dark:
        hl = layer()
        ImageDraw.Draw(hl).ellipse((cx - w * 0.34, top + h * 0.1, cx - w * 0.08, top + h * 0.42), fill=(255, 246, 220, 170))
        hl = hl.filter(ImageFilter.GaussianBlur(9))
        hl2 = layer(); hl2.paste(hl, (0, 0), cap)
        art.alpha_composite(hl2)
    if rim:
        # moonlight catching the right edge of the capsule
        edge = ImageChops.subtract(cap, ImageChops.offset(cap, -10, 4))
        paint(art, edge, (255, 236, 186) if dark else (255, 244, 214))
    return art


def centred(art, t, dy=-0.01, fill=0.66):
    box = art.getbbox()
    a = art.crop(box)
    k = (S * fill) / max(a.size)
    a = a.resize((int(a.width * k), int(a.height * k)), Image.LANCZOS)
    pos = ((S - a.width) // 2, (S - a.height) // 2 + int(S * dy))
    t.alpha_composite(a, pos)
    return pos, a.size


def render(size=128, preset=DEFAULT, square=False):
    """square=True: full-bleed, no rounded corners -- for iOS apple-touch-icon and
    Android maskable icons, where the OS applies its own mask."""
    glow_r, glow_a, ring_a, ring_w, ring_blur = PRESETS[preset]
    t = sky()
    if glow_a:
        t = glow(t, 256, 205, glow_r, alpha=glow_a)
    if ring_a:
        ring = layer()
        ImageDraw.Draw(ring).ellipse((256 - 170, 205 - 170, 256 + 170, 205 + 170), outline=(255, 226, 170, ring_a), width=ring_w)
        t = Image.alpha_composite(t, ring.filter(ImageFilter.GaussianBlur(ring_blur)) if ring_blur else ring)
    centred(glossy_mic(256, 60, 150, 230, gloss=False), t)
    return (t if square else rounded(t)).resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    preset = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    render(preset=preset).save(OUT)
    print("icon vesper (%s) ->" % preset, OUT)
