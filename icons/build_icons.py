"""Build the 128x128 Pushover app icons, one per project, from each project's
own icon.

Pushover shows an icon per *application*, not per message, so every project
gets its own Pushover app (token in config.json `pushover.apps`, keyed by
source) with the matching icon uploaded. Pharos's own app (the lighthouse,
draw_pharos.py) is the default for anything without one. Arbiter, Archivist,
Gleaner, Spore and Vesper are drawn by draw_arbiter.py / draw_archivist.py /
draw_gleaner.py / draw_spore.py / draw_vesper.py.

    py -3.11 icons\\build_icons.py

SVGs are rendered with headless Edge (no cairo on this box).
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import draw_arbiter
import draw_archivist
import draw_gleaner
import draw_pharos
import draw_spore
import draw_vesper

DEV = Path(r"C:\Development")
OUT = Path(__file__).resolve().parent
SIZE = 128
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FOYER = DEV / "Foyer/site/icons"  # the portfolio site's project badges

# source name (as passed to pharos.send) -> that project's own icon (png or svg)
SOURCES = {
    "trader": DEV / "Trader/public/icons/icon-192.png",
    "spice": DEV / "Spice/frontend/public/icon-192.png",
    "gamenight": DEV / "GameNight/frontend/public/icons/icon-192.png",
    "fantasy": DEV / "Fantasy/frontend/public/favicon.svg",
    "wayfinder": DEV / "Wayfinder/templates/live/worker/app/icon.svg",
}

# Artwork with a transparent background, set on a tile: source -> (file, tile colour).
TILED: dict = {}

# Projects with no icon anywhere yet: a drawn stand-in (emoji, background).
DRAWN: dict = {}


def render_svg(src: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "out.png"
        subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", "--window-size=512,512",
             f"--screenshot={png}", src.resolve().as_uri()],
            check=True, capture_output=True, timeout=60,
        )
        return Image.open(png).convert("RGBA")


def from_icon(src: Path, dst: Path) -> None:
    img = render_svg(src) if src.suffix.lower() == ".svg" else Image.open(src).convert("RGBA")
    box = img.getbbox()  # trim transparent margins so the badge fills the icon
    if box:
        img = img.crop(box)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(dst, optimize=True)


def tiled(src: Path, bg: tuple, dst: Path) -> None:
    art = Image.open(src)
    if art.format == "ICO":
        art.size = max(art.info.get("sizes", {art.size}))
    art = art.convert("RGBA")
    art = art.crop(art.getbbox())
    scale = 4
    big = SIZE * scale
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=bg + (255,))
    inner = int(big * 0.72)
    art = art.resize((inner, int(inner * art.height / art.width)), Image.LANCZOS)
    tile.alpha_composite(art, ((big - art.width) // 2, (big - art.height) // 2))
    tile.resize((SIZE, SIZE), Image.LANCZOS).save(dst, optimize=True)


def drawn(emoji: str, bg: tuple, dst: Path) -> None:
    scale = 4
    big = SIZE * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=bg + (255,))
    font = ImageFont.truetype(r"C:\Windows\Fonts\seguiemj.ttf", int(big * 0.6))
    draw.text((big / 2, big / 2), emoji, font=font, anchor="mm", embedded_color=True)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(dst, optimize=True)


if __name__ == "__main__":
    draw_pharos.render(SIZE).save(OUT / "pharos.png")
    print("icon pharos (drawn)")
    draw_arbiter.render(SIZE).save(OUT / "arbiter.png")
    print("icon arbiter (drawn)")
    draw_archivist.render(SIZE).save(OUT / "archivist.png")
    print("icon archivist (drawn)")
    draw_gleaner.render(SIZE).save(OUT / "gleaner.png")
    print("icon gleaner (drawn)")
    draw_spore.render(SIZE).save(OUT / "spore.png")
    print("icon spore (drawn)")
    draw_vesper.render(SIZE).save(OUT / "vesper.png")
    print("icon vesper (drawn, preset %s)" % draw_vesper.DEFAULT)
    for name, src in SOURCES.items():
        from_icon(src, OUT / f"{name}.png")
        print("icon", name, "<-", src)
    for name, (src, bg) in TILED.items():
        tiled(src, bg, OUT / f"{name}.png")
        print("icon", name, "<-", src, "(tiled)")
    for name, (emoji, bg) in DRAWN.items():
        drawn(emoji, bg, OUT / f"{name}.png")
        print("icon", name, "(drawn stand-in)")
