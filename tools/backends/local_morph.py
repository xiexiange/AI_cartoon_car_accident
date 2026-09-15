# -*- coding: utf-8 -*-
"""本地 start/peak/end 关键帧 morph + 镜头运动，产出真动画片段（非静帧幻灯）。"""
from __future__ import annotations

import os
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# 确保 imageio 使用自带 ffmpeg，不依赖系统 PATH
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", imageio_ffmpeg.get_ffmpeg_exe())


def _fit_square(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    im = im.convert("RGB")
    src_w, src_h = im.size
    scale = max(w / src_w, h / src_h)
    nw, nh = max(1, int(src_w * scale)), max(1, int(src_h * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _zoom_crop(im: Image.Image, zoom: float, cx: float = 0.5, cy: float = 0.5) -> Image.Image:
    """zoom>1 放大；cx/cy 为裁切中心 0~1。"""
    zoom = max(1.0, float(zoom))
    w, h = im.size
    cw, ch = w / zoom, h / zoom
    left = cx * w - cw / 2
    top = cy * h - ch / 2
    left = max(0, min(left, w - cw))
    top = max(0, min(top, h - ch))
    crop = im.crop((int(left), int(top), int(left + cw), int(top + ch)))
    return crop.resize((w, h), Image.Resampling.LANCZOS)


def _motion_params(camera: dict) -> dict:
    motion = (camera or {}).get("motion") or "固定"
    # start_zoom, peak_zoom, end_zoom, pan (dx, dy) over clip
    table = {
        "推": {"z0": 1.00, "z1": 1.12, "z2": 1.22, "pan": (0.00, -0.02)},
        "拉": {"z0": 1.18, "z1": 1.10, "z2": 1.00, "pan": (0.00, 0.02)},
        "跟": {"z0": 1.04, "z1": 1.08, "z2": 1.06, "pan": (0.06, 0.00)},
        "摇": {"z0": 1.05, "z1": 1.06, "z2": 1.05, "pan": (0.08, 0.00)},
        "切": {"z0": 1.00, "z1": 1.10, "z2": 1.04, "pan": (0.00, 0.00)},
        "固定": {"z0": 1.02, "z1": 1.06, "z2": 1.03, "pan": (0.01, 0.005)},
    }
    return table.get(motion, table["固定"])


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    t = max(0.0, min(1.0, t))
    if t <= 0:
        return a
    if t >= 1:
        return b
    return Image.blend(a.convert("RGB"), b.convert("RGB"), t)


def make_keyframes(
    still: Image.Image,
    shot: dict,
    size: tuple[int, int],
) -> tuple[Image.Image, Image.Image, Image.Image]:
    base = _fit_square(still, size)
    mp = _motion_params(shot.get("camera") or {})
    # peak 稍提对比/锐度，模拟动作顶点
    peak_base = ImageEnhance.Contrast(base).enhance(1.08)
    peak_base = ImageEnhance.Sharpness(peak_base).enhance(1.15)
    peak_base = peak_base.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2))

    start = _zoom_crop(base, mp["z0"], 0.5, 0.5)
    peak = _zoom_crop(
        peak_base,
        mp["z1"],
        0.5 + mp["pan"][0] * 0.5,
        0.5 + mp["pan"][1] * 0.5,
    )
    end = _zoom_crop(
        base,
        mp["z2"],
        0.5 + mp["pan"][0],
        0.5 + mp["pan"][1],
    )
    return start, peak, end


def _frame_at(
    start: Image.Image,
    peak: Image.Image,
    end: Image.Image,
    t: float,
    mp: dict,
) -> Image.Image:
    """两段 morph：0~0.45 start→peak，0.45~1 peak→end，再叠加连续 zoom/pan。"""
    if t <= 0.45:
        local = _ease_in_out(t / 0.45)
        morph = _blend(start, peak, local)
        z = _lerp(mp["z0"], mp["z1"], local)
        cx = _lerp(0.5, 0.5 + mp["pan"][0] * 0.5, local)
        cy = _lerp(0.5, 0.5 + mp["pan"][1] * 0.5, local)
    else:
        local = _ease_in_out((t - 0.45) / 0.55)
        morph = _blend(peak, end, local)
        z = _lerp(mp["z1"], mp["z2"], local)
        cx = _lerp(0.5 + mp["pan"][0] * 0.5, 0.5 + mp["pan"][0], local)
        cy = _lerp(0.5 + mp["pan"][1] * 0.5, 0.5 + mp["pan"][1], local)
    # 二次 zoom 强化运镜（在 morph 结果上再裁）
    return _zoom_crop(morph, max(1.0, z / max(mp["z0"], 1.001)), cx, cy)


def render_shot_clip(
    *,
    still_path: Path,
    shot: dict,
    out_path: Path,
    keyframes_dir: Path,
    fps: int = 24,
    size: tuple[int, int] = (1080, 1080),
) -> Path:
    still = Image.open(still_path)
    start, peak, end = make_keyframes(still, shot, size)
    sid = shot.get("shot_id", "Sxx")
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    start.save(keyframes_dir / f"{sid}_start.png")
    peak.save(keyframes_dir / f"{sid}_peak.png")
    end.save(keyframes_dir / f"{sid}_end.png")

    duration = float(shot.get("duration_sec") or 2.0)
    n = max(1, int(round(duration * fps)))
    mp = _motion_params(shot.get("camera") or {})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        str(out_path),
        fps=fps,
        codec="libx264",
        quality=8,
        pixelformat="yuv420p",
        macro_block_size=1,
        ffmpeg_log_level="error",
        output_params=["-movflags", "+faststart"],
    )

    try:
        for i in range(n):
            t = 0.0 if n == 1 else i / (n - 1)
            frame = _frame_at(start, peak, end, t, mp)
            writer.append_data(np.asarray(frame))
    finally:
        writer.close()
    return out_path
