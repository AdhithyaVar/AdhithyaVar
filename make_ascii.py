#!/usr/bin/env python3
"""Turn a photo of you into the ASCII portrait on the left of the card.

    python make_ascii.py me.jpg
    python make_ascii.py me.png --cols 60 --contrast 1.4

Writes assets/ascii_dark.txt (light-on-dark card) and assets/ascii_light.txt (dark-on-light card).
Then run `python build_card.py --offline` and open dark_mode.svg to see it.

Best input: head and shoulders, face well lit, plain background. A PNG with a transparent background
(remove.bg, Canva, Photoshop...) is better still: the background becomes empty space.
Tuning: --crop LEFT,TOP,RIGHT,BOTTOM (pixels) frames the face, --contrast and --gamma add punch,
--cols sets the size (the card grows with it).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    sys.exit("Pillow is needed for this step:  pip install pillow")

ROOT = Path(__file__).resolve().parent
RESAMPLE = getattr(Image, "Resampling", Image)   # Pillow 9.1+ keeps the filters here
RAMP = " .:-=+*#%@"      # empty -> dense
CELL = 0.5               # glyph width / line height of the card's portrait font (6 px by 12 px)
ALPHA_CUT = 40           # pixels more transparent than this stay blank


def shade(path: Path, cols: int, crop, contrast: float, gamma: float, sharpen: float):
    """Photo -> (grayscale, alpha) images exactly cols x rows pixels, one pixel per character."""
    img = ImageOps.exif_transpose(Image.open(path))
    if crop:
        img = img.crop(crop)
    img = img.convert("RGBA")
    rows = max(1, round(cols * img.height / img.width * CELL))

    alpha = img.getchannel("A")
    mask = alpha.point(lambda a: 255 if a >= ALPHA_CUT else 0)
    gray = img.convert("L")
    try:
        gray = ImageOps.autocontrast(gray, cutoff=1, mask=mask)   # judge tones by the subject only
    except TypeError:                                             # very old Pillow
        gray = ImageOps.autocontrast(gray, cutoff=1)
    if contrast != 1:
        gray = ImageEnhance.Contrast(gray).enhance(contrast)
    if gamma != 1:
        gray = gray.point([round(255 * (i / 255) ** (1 / gamma)) for i in range(256)])

    gray = gray.resize((cols * 4, rows * 4), RESAMPLE.LANCZOS)    # sharpen at 4x so detail survives
    if sharpen:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=3, percent=int(120 * sharpen), threshold=2))
    return gray.resize((cols, rows), RESAMPLE.BOX), alpha.resize((cols, rows), RESAMPLE.BOX)


def to_text(gray, alpha, ramp: str, invert: bool) -> str:
    """invert=False: bright pixels get dense characters (light ink on the dark card).
    invert=True: dark pixels get dense characters (dark ink on the light card)."""
    px, al = gray.load(), alpha.load()
    last = len(ramp) - 1
    lines = []
    for y in range(gray.height):
        row = []
        for x in range(gray.width):
            if al[x, y] < ALPHA_CUT:
                row.append(" ")
                continue
            v = 255 - px[x, y] if invert else px[x, y]
            row.append(ramp[round(v / 255 * last)])
        lines.append("".join(row).rstrip())
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Photo -> ASCII portrait for the profile card.")
    ap.add_argument("photo", type=Path)
    ap.add_argument("--cols", type=int, default=56, help="portrait width in characters (default 56)")
    ap.add_argument("--crop", help="LEFT,TOP,RIGHT,BOTTOM in pixels, to frame the face")
    ap.add_argument("--contrast", type=float, default=1.25)
    ap.add_argument("--gamma", type=float, default=1.0, help=">1 brightens the midtones, <1 darkens them")
    ap.add_argument("--sharpen", type=float, default=1.0, help="0 turns sharpening off")
    ap.add_argument("--ramp", default=RAMP, help="characters from empty to dense")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "assets")
    args = ap.parse_args()

    crop = None
    if args.crop:
        try:
            crop = tuple(int(v) for v in args.crop.split(","))
            if len(crop) != 4:
                raise ValueError
        except ValueError:
            return print("error: --crop wants four whole numbers: LEFT,TOP,RIGHT,BOTTOM") or 1
    try:
        gray, alpha = shade(args.photo, args.cols, crop, args.contrast, args.gamma, args.sharpen)
    except OSError as exc:
        return print(f"error: cannot open {args.photo}: {exc}") or 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "ascii_dark.txt").write_text(to_text(gray, alpha, args.ramp, invert=False), encoding="utf-8")
    (args.out_dir / "ascii_light.txt").write_text(to_text(gray, alpha, args.ramp, invert=True), encoding="utf-8")
    print(f"{gray.width} x {gray.height} characters -> {args.out_dir}/ascii_dark.txt and ascii_light.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
