"""Slice the NPC sprite sheet into individual trimmed PNGs.

The sprites are NOT on a clean even grid, so we auto-detect the rows and
columns from the alpha channel's projection profiles (gutters between
sprites are fully transparent) and segment on those gaps.

Reads `attempt_1_alpha (7).png` (RGBA) and writes
`frontend/public/sprites/npc_00.png` ... `npc_NN.png`, row-major order,
each tightly cropped to its non-transparent bounding box.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "attempt_1_alpha (7).png"
OUT = ROOT / "frontend" / "public" / "sprites"

ALPHA_THRESHOLD = 16   # alpha > this counts as "ink"
MIN_BAND = 24          # ignore detected bands thinner than this (px)


def find_bands(profile: np.ndarray, min_band: int) -> list[tuple[int, int]]:
    """Return [start, end) ranges where profile > 0 (contiguous ink runs)."""
    bands: list[tuple[int, int]] = []
    inside = False
    start = 0
    for i, v in enumerate(profile):
        if v > 0 and not inside:
            inside = True
            start = i
        elif v <= 0 and inside:
            inside = False
            if i - start >= min_band:
                bands.append((start, i))
    if inside and len(profile) - start >= min_band:
        bands.append((start, len(profile)))
    return bands


def trim(cell: Image.Image) -> Image.Image:
    alpha = cell.getchannel("A")
    mask = alpha.point(lambda a: 255 if a > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    return cell.crop(bbox) if bbox else cell


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    arr = np.asarray(im)
    ink = arr[:, :, 3] > ALPHA_THRESHOLD  # (H, W) bool

    row_profile = ink.sum(axis=1)  # per-y ink count
    col_profile = ink.sum(axis=0)  # per-x ink count

    row_bands = find_bands(row_profile, MIN_BAND)
    col_bands = find_bands(col_profile, MIN_BAND)
    print(f"detected {len(row_bands)} rows x {len(col_bands)} cols")

    OUT.mkdir(parents=True, exist_ok=True)
    # Clear any stale slices from a previous (wrong) run.
    for old in OUT.glob("npc_*.png"):
        old.unlink()

    idx = 0
    for (y0, y1) in row_bands:
        for (x0, x1) in col_bands:
            cell = im.crop((x0, y0, x1, y1))
            sprite = trim(cell)
            if sprite.width <= 2 or sprite.height <= 2:
                continue
            sprite.save(OUT / f"npc_{idx:02d}.png")
            idx += 1

    print(f"saved {idx} sprites -> {OUT}")


if __name__ == "__main__":
    main()
