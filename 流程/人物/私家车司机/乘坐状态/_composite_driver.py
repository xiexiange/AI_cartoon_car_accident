# -*- coding: utf-8 -*-
"""Composite seated driver cutouts into empty vehicle window masks."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(
    r"C:/Users/xiexiange/.cursor/projects/e-Project-xxg-AI-cartoon-car-accident/assets"
)
OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)


def remove_bg(im: Image.Image, thr: int = 235) -> Image.Image:
    im = im.convert("RGBA")
    arr = np.array(im)
    rgb = arr[:, :, :3].astype(np.int16)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    near_gray = (mx - mn) < 18
    light = mx > thr
    mid_light = (mn > 210) & near_gray
    alpha = np.where(light | mid_light, 0, 255).astype(np.uint8)
    arr[:, :, 3] = alpha
    out = Image.fromarray(arr, "RGBA")
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


def _clean_mask(glass: np.ndarray) -> np.ndarray:
    m = Image.fromarray((glass.astype(np.uint8) * 255))
    m = (
        m.filter(ImageFilter.MaxFilter(3))
        .filter(ImageFilter.MinFilter(5))
        .filter(ImageFilter.MaxFilter(5))
    )
    return np.array(m) > 128


def glass_mask_side(car_rgb: np.ndarray) -> np.ndarray:
    h, w = car_rgb.shape[:2]
    r, g, b = car_rgb[:, :, 0], car_rgb[:, :, 1], car_rgb[:, :, 2]
    gray = car_rgb.mean(axis=2)
    sat = np.maximum(np.maximum(r, g), b).astype(int) - np.minimum(
        np.minimum(r, g), b
    ).astype(int)
    glass = (gray > 70) & (gray < 175) & (sat < 35)
    glass[: int(h * 0.34)] = False
    glass[int(h * 0.55) :] = False
    glass[:, : int(w * 0.08)] = False
    glass[:, int(w * 0.95) :] = False
    return _clean_mask(glass)


def glass_mask_front(car_rgb: np.ndarray) -> np.ndarray:
    h, w = car_rgb.shape[:2]
    r, g, b = car_rgb[:, :, 0], car_rgb[:, :, 1], car_rgb[:, :, 2]
    gray = car_rgb.mean(axis=2)
    sat = np.maximum(np.maximum(r, g), b).astype(int) - np.minimum(
        np.minimum(r, g), b
    ).astype(int)
    glass = (gray > 55) & (gray < 170) & (sat < 40)
    glass[: int(h * 0.30)] = False
    glass[int(h * 0.52) :] = False
    glass[:, : int(w * 0.12)] = False
    glass[:, int(w * 0.88) :] = False
    return _clean_mask(glass)


def glass_mask_rear(car_rgb: np.ndarray) -> np.ndarray:
    h, w = car_rgb.shape[:2]
    r, g, b = car_rgb[:, :, 0], car_rgb[:, :, 1], car_rgb[:, :, 2]
    gray = car_rgb.mean(axis=2)
    sat = np.maximum(np.maximum(r, g), b).astype(int) - np.minimum(
        np.minimum(r, g), b
    ).astype(int)
    glass = (gray > 55) & (gray < 170) & (sat < 40)
    glass[: int(h * 0.32)] = False
    glass[int(h * 0.50) :] = False
    glass[:, : int(w * 0.15)] = False
    glass[:, int(w * 0.85) :] = False
    return _clean_mask(glass)


def place_driver(
    car: Image.Image,
    driver: Image.Image,
    mask: np.ndarray,
    scale_frac: float = 0.72,
    x_frac: float = 0.55,
    y_frac: float = 0.55,
    darken: float = 0.92,
    glass_alpha: int = 70,
):
    car = car.convert("RGBA")
    base = car.copy()
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise RuntimeError("empty glass mask")
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw, bh = x1 - x0 + 1, y1 - y0 + 1

    dw, dh = driver.size
    target_h = max(8, int(bh * scale_frac))
    target_w = max(8, int(dw * (target_h / dh)))
    drv = driver.resize((target_w, target_h), Image.Resampling.LANCZOS)

    rgb = drv.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(darken)
    rgb = ImageEnhance.Color(rgb).enhance(0.95)
    a = drv.split()[-1]
    drv = Image.merge("RGBA", (*rgb.split(), a))

    cx = int(x0 + bw * x_frac)
    cy = int(y0 + bh * y_frac)
    px = cx - target_w // 2
    py = cy - target_h // 2

    layer = Image.new("RGBA", car.size, (0, 0, 0, 0))
    layer.paste(drv, (px, py), drv)

    la = np.array(layer)
    la[:, :, 3] = (
        la[:, :, 3].astype(np.float32) * mask.astype(np.float32)
    ).astype(np.uint8)
    layer = Image.fromarray(la, "RGBA")

    composed = Image.alpha_composite(base, layer)

    carr = np.array(car)
    ov = np.zeros_like(carr)
    ov[mask] = carr[mask]
    ov[:, :, 3] = np.where(mask, glass_alpha, 0).astype(np.uint8)
    glass_overlay = Image.fromarray(ov, "RGBA")
    composed = Image.alpha_composite(composed, glass_overlay)
    return composed.convert("RGB"), (x0, y0, x1, y1), (px, py, target_w, target_h)


def main():
    # SIDE
    car_side = Image.open(ROOT / "交通工具" / "载具_侧面.png")
    drv_side = remove_bg(Image.open(ASSETS / "driver_seat_side_cutout.png"), thr=225)
    mask_s = glass_mask_side(np.array(car_side.convert("RGB")))
    ys, xs = np.where(mask_s)
    x0, x1 = int(xs.min()), int(xs.max())
    front_cut = x0 + int((x1 - x0) * 0.58)
    mask_front_win = mask_s.copy()
    mask_front_win[:, front_cut:] = False
    Image.fromarray((mask_front_win.astype(np.uint8) * 255)).save(
        ASSETS / "_debug_mask_side.png"
    )
    side_out, bbox, pos = place_driver(
        car_side,
        drv_side,
        mask_front_win,
        scale_frac=0.85,
        x_frac=0.48,
        y_frac=0.58,
        darken=0.90,
    )
    print("side bbox", bbox, "pos", pos, "driver", drv_side.size)
    side_out.save(OUT / "乘坐_侧面.png")
    print("saved", OUT / "乘坐_侧面.png")

    # FRONT
    car_f = Image.open(ROOT / "交通工具" / "载具_正面.png")
    drv_f = remove_bg(Image.open(ASSETS / "driver_seat_front_cutout.png"), thr=220)
    mask_f = glass_mask_front(np.array(car_f.convert("RGB")))
    Image.fromarray((mask_f.astype(np.uint8) * 255)).save(ASSETS / "_debug_mask_front.png")
    front_out, bbox, pos = place_driver(
        car_f,
        drv_f,
        mask_f,
        scale_frac=0.70,
        x_frac=0.68,
        y_frac=0.55,
        darken=0.88,
    )
    print("front bbox", bbox, "pos", pos)
    front_out.save(OUT / "乘坐_正面.png")
    print("saved", OUT / "乘坐_正面.png")

    # REAR
    car_r = Image.open(ROOT / "交通工具" / "载具_背面.png")
    drv_r = remove_bg(Image.open(ASSETS / "driver_seat_rear_cutout.png"), thr=240)
    mask_r = glass_mask_rear(np.array(car_r.convert("RGB")))
    Image.fromarray((mask_r.astype(np.uint8) * 255)).save(ASSETS / "_debug_mask_rear.png")
    rear_out, bbox, pos = place_driver(
        car_r,
        drv_r,
        mask_r,
        scale_frac=0.45,
        x_frac=0.35,
        y_frac=0.45,
        darken=0.85,
    )
    print("rear bbox", bbox, "pos", pos)
    rear_out.save(OUT / "乘坐_背面.png")
    print("saved", OUT / "乘坐_背面.png")
    print("done")


if __name__ == "__main__":
    main()
