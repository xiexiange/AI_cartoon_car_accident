# -*- coding: utf-8 -*-
"""Finalize 私家车司机 riding three-views: AI front/rear + masked side composite."""
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


def remove_bg(im: Image.Image, thr: int = 225) -> Image.Image:
    im = im.convert("RGBA")
    arr = np.array(im)
    rgb = arr[:, :, :3].astype(np.int16)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    near_gray = (mx - mn) < 20
    light = mx > thr
    mid_light = (mn > 205) & near_gray
    arr[:, :, 3] = np.where(light | mid_light, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr, "RGBA")
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def fit_to_canvas(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center-crop/cover resize to exact size."""
    tw, th = size
    im = im.convert("RGB")
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def polygon_mask(size: tuple[int, int], pts: list[tuple[int, int]]) -> np.ndarray:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    # soft edge
    m = m.filter(ImageFilter.GaussianBlur(0.8))
    return np.array(m).astype(np.float32) / 255.0


def place_in_mask(
    car: Image.Image,
    driver: Image.Image,
    mask: np.ndarray,
    scale_h: float,
    x_frac: float,
    y_frac: float,
    darken: float = 0.90,
    glass_alpha: int = 55,
    crop_legs: bool = False,
) -> Image.Image:
    car = car.convert("RGBA")
    drv = driver.convert("RGBA")
    if crop_legs:
        # keep upper ~62% (torso + wheel)
        w, h = drv.size
        drv = drv.crop((0, 0, w, int(h * 0.62)))

    ys, xs = np.where(mask > 0.3)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bw, bh = x1 - x0 + 1, y1 - y0 + 1

    target_h = max(8, int(bh * scale_h))
    dw, dh = drv.size
    target_w = max(8, int(dw * (target_h / dh)))
    drv = drv.resize((target_w, target_h), Image.Resampling.LANCZOS)

    rgb = ImageEnhance.Brightness(drv.convert("RGB")).enhance(darken)
    rgb = ImageEnhance.Color(rgb).enhance(0.95)
    drv = Image.merge("RGBA", (*rgb.split(), drv.split()[-1]))

    cx = int(x0 + bw * x_frac)
    cy = int(y0 + bh * y_frac)
    px = cx - target_w // 2
    py = cy - target_h // 2

    layer = Image.new("RGBA", car.size, (0, 0, 0, 0))
    layer.paste(drv, (px, py), drv)
    la = np.array(layer)
    la[:, :, 3] = (la[:, :, 3].astype(np.float32) * mask).astype(np.uint8)
    layer = Image.fromarray(la, "RGBA")

    composed = Image.alpha_composite(car, layer)

    # mild original-glass tint on top so driver looks behind glass
    carr = np.array(car)
    ov = np.zeros_like(carr)
    ov[:, :, :3] = carr[:, :, :3]
    ov[:, :, 3] = (mask * glass_alpha).astype(np.uint8)
    composed = Image.alpha_composite(composed, Image.fromarray(ov, "RGBA"))
    return composed.convert("RGB")


def make_side() -> Image.Image:
    car = Image.open(ROOT / "交通工具" / "载具_侧面.png")
    drv = remove_bg(Image.open(ASSETS / "driver_seat_side_cutout.png"), thr=225)
    # Front side window polygon (car faces left, driver window)
    # calibrated from empty 载具_侧面 cabin sampling
    pts = [
        (195, 435),
        (390, 430),
        (395, 520),
        (385, 545),
        (210, 548),
        (185, 500),
    ]
    mask = polygon_mask(car.size, pts)
    # debug
    Image.fromarray((mask * 255).astype(np.uint8)).save(ASSETS / "_debug_mask_side2.png")
    return place_in_mask(
        car,
        drv,
        mask,
        scale_h=0.92,
        x_frac=0.50,
        y_frac=0.55,
        darken=0.88,
        glass_alpha=50,
        crop_legs=True,
    )


def main():
    # FRONT: use validated AI result, match empty-car size
    car_f = Image.open(ROOT / "交通工具" / "载具_正面.png")
    front = fit_to_canvas(Image.open(ASSETS / "乘坐_正面.png"), car_f.size)
    front.save(OUT / "乘坐_正面.png")
    print("saved front", front.size)

    # REAR: use validated AI v2
    car_r = Image.open(ROOT / "交通工具" / "载具_背面.png")
    rear = fit_to_canvas(Image.open(ASSETS / "乘坐_背面_v2.png"), car_r.size)
    rear.save(OUT / "乘坐_背面.png")
    print("saved rear", rear.size)

    # SIDE: masked composite into closed empty-car window
    side = make_side()
    side.save(OUT / "乘坐_侧面.png")
    print("saved side", side.size)

    # optional triptych like other characters
    target_h = 1152
    imgs = [
        fit_to_canvas(front, (682, target_h)),
        fit_to_canvas(side, (682, target_h)),
        fit_to_canvas(rear, (682, target_h)),
    ]
    sheet = Image.new("RGB", (682 * 3 + 40, target_h + 20), (255, 255, 255))
    for i, im in enumerate(imgs):
        sheet.paste(im, (10 + i * 682, 10))
    sheet.save(OUT / "乘坐_三视图拼合.png")
    print("saved sheet", sheet.size)
    print("done")


if __name__ == "__main__":
    main()
