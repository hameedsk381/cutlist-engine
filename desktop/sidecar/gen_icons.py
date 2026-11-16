"""Generate Tauri app icons from a simple vector motif.

One-off helper: writes desktop/src-tauri/icons/{icon.ico,32x32.png,128x128.png,128x128@2x.png,icon.png}
Run from repo root:  py -3 desktop/sidecar/gen_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"
SIZE = 1024

BG = (15, 20, 32, 255)        # deep navy
PANEL = (79, 156, 249, 255)   # engine blue
PART = (63, 201, 143, 255)    # mint green
CUT = (233, 108, 139, 255)    # cutline pink


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], r: int, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def build_base() -> Image.Image:
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # App tile
    rounded(d, (64, 64, SIZE - 64, SIZE - 64), 160, BG)

    # A plywood sheet, slightly tilted
    sheet = [(300, 210), (830, 300), (740, 800), (210, 710)]
    d.polygon(sheet, fill=PANEL)

    # Cut line across the sheet (kerf)
    d.line([(262, 500), (790, 560)], fill=CUT, width=34)

    # A cut part below the line
    part = [(300, 585), (640, 630), (620, 745), (250, 690)]
    d.polygon(part, fill=PART)

    # Screw holes / grain ticks on the sheet
    for x in range(340, 700, 90):
        d.ellipse((x, 330, x + 26, 356), fill=BG)
    for x in range(360, 690, 90):
        d.ellipse((x, 430, x + 26, 456), fill=BG)
    return im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = build_base()

    base.resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    base.resize((256, 256), Image.LANCZOS).save(OUT / "128x128@2x.png")
    base.resize((128, 128), Image.LANCZOS).save(OUT / "128x128.png")
    base.resize((32, 32), Image.LANCZOS).save(OUT / "32x32.png")

    # Windows .ico with several embedded sizes
    base.save(
        OUT / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icons written to {OUT}")


if __name__ == "__main__":
    main()
