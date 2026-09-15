# -*- coding: utf-8 -*-
"""Fix rear riding view: hair above front-left headrest with seat occlusion."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
ASSETS = Path(
    r"C:/Users/xiexiange/.cursor/projects/e-Project-xxg-AI-cartoon-car-accident/assets"
)


def fit_rgba(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    im = im.convert("RGBA")
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def remove_bg(im: Image.Image, thr: int = 235) -> Image.Image:
    im = im.convert("RGBA")
    arr = np.array(im)
    rgb = arr[:, :, :3].astype(np.int16)
    mx, mn = rgb.max(2), rgb.min(2)
    arr[:, :, 3] = np.where(
        (mx > thr) | ((mn > 205) & ((mx - mn) < 20)), 0, 255
    ).astype(np.uint8)
    out = Image.fromarray(arr, "RGBA")
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def fit_rgb(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    im = im.convert("RGB")
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def main() -> None:
    raw = np.array(Image.open(ROOT / "交通工具" / "载具_背面.png").convert("RGBA"))
    h, w = raw.shape[:2]
    g = raw[:, :, :3].mean(2)
    bg = raw[30, w // 2].copy()
    # wipe leftover side fragment on left
    for x in range(0, 140):
        for y in range(h):
            if g[y, x] <= 245:
                raw[y, x] = bg
    empty = Image.fromarray(raw, "RGBA")
    empty.save(ASSETS / "_clean_rear_empty.png")
    ea = np.array(empty)

    row = ea[440, :, :3].mean(axis=1)
    vals = row[250:480]
    darkness = 255 - vals
    peaks: list[int] = []
    for i in range(10, len(darkness) - 10):
        if darkness[i] > 160 and darkness[i] == darkness[i - 10 : i + 11].max():
            if not peaks or i - peaks[-1] > 50:
                peaks.append(i)
    peak_xs = [p + 250 for p in peaks]
    print("headrest peaks", peak_xs)
    left_cx = peak_xs[0] if peak_xs else 300

    lhx0, lhx1 = left_cx - 35, left_cx + 35
    lhy0, lhy1 = 415, 495
    rest = np.zeros((h, w), dtype=bool)
    rest[lhy0:lhy1, lhx0:lhx1] = ea[lhy0:lhy1, lhx0:lhx1, :3].mean(2) < 105
    rm = (
        Image.fromarray((rest.astype(np.uint8) * 255))
        .filter(ImageFilter.MaxFilter(3))
        .filter(ImageFilter.MinFilter(3))
    )
    rest = np.array(rm) > 128
    ys, xs = np.where(rest)
    top_y = int(ys.min()) if len(ys) else 430
    print("driver headrest", lhx0, lhy0, lhx1, lhy1, "top", top_y, "cx", left_cx)

    head = remove_bg(Image.open(ASSETS / "driver_seat_rear_cutout.png"), 240)
    hw, hh = head.size
    head = head.crop((int(hw * 0.18), 0, int(hw * 0.82), int(hh * 0.36)))
    tw = 88
    head = head.resize(
        (tw, max(12, int(head.size[1] * tw / head.size[0]))), Image.Resampling.LANCZOS
    )
    rgb = ImageEnhance.Brightness(head.convert("RGB")).enhance(0.84)
    head = Image.merge("RGBA", (*rgb.split(), head.split()[-1]))

    px = left_cx - head.size[0] // 2
    py = top_y - int(head.size[1] * 0.78)
    print("hair place", px, py, head.size)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.paste(head, (px, py), head)
    la = np.array(layer)
    # hair only ABOVE headrest top — seat occludes body
    la[top_y + 2 :, :, 3] = 0
    la[:, : max(0, lhx0 - 20), 3] = 0
    la[:, min(w, lhx1 + 20) :, 3] = 0
    la[:400, :, 3] = 0
    la[510:, :, 3] = 0
    layer = Image.fromarray(la, "RGBA")
    composed = Image.alpha_composite(empty, layer)

    ov = np.zeros_like(ea)
    ov[rest] = ea[rest]
    ov[:, :, 3] = np.where(rest, 255, 0).astype(np.uint8)
    composed = Image.alpha_composite(composed, Image.fromarray(ov, "RGBA"))

    win = Image.new("L", (w, h), 0)
    ImageDraw.Draw(win).polygon(
        [(230, 400), (470, 400), (510, 510), (200, 510)], fill=255
    )
    tint = np.zeros_like(ea)
    tint[:, :, :3] = ea[:, :, :3]
    tint[:, :, 3] = (np.array(win).astype(np.float32) / 255 * 30).astype(np.uint8)
    composed = Image.alpha_composite(composed, Image.fromarray(tint, "RGBA"))

    result = composed.convert("RGB")
    result.save(OUT / "乘坐_背面.png")
    print("saved rear")

    dbg = result.copy()
    d = ImageDraw.Draw(dbg)
    d.rectangle([lhx0, lhy0, lhx1, lhy1], outline=(255, 0, 0), width=2)
    d.rectangle([px, py, px + head.size[0], top_y + 2], outline=(0, 255, 0), width=2)
    dbg.save(ASSETS / "_debug_rear_final.png")

    front = Image.open(OUT / "乘坐_正面.png")
    side = Image.open(OUT / "乘坐_侧面.png")
    imgs = [
        fit_rgb(front, (682, 1152)),
        fit_rgb(side, (682, 1152)),
        fit_rgb(result, (682, 1152)),
    ]
    sheet = Image.new("RGB", (682 * 3 + 40, 1172), (255, 255, 255))
    for i, im in enumerate(imgs):
        sheet.paste(im, (10 + i * 682, 10))
    sheet.save(OUT / "乘坐_三视图拼合.png")
    print("sheet ok")


if __name__ == "__main__":
    main()
