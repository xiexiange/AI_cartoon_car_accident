# -*- coding: utf-8 -*-
"""用 imageio-ffmpeg 自带 ffmpeg 做 xfade 拼接。"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg


def trim_clip(src: Path, dest: Path, duration_sec: float, fps: int = 24) -> Path:
    """按脚本时长裁切（Agnes 最短约 81 帧 / 3.4s，长于单镜）。"""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.2, float(duration_sec))
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-t",
        f"{dur:.3f}",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    subprocess.run(cmd, check=True)
    return dest


def concat_with_crossfade(
    *,
    clips: list[Path],
    durations: list[float],
    out_path: Path,
    fps: int = 24,
    size: tuple[int, int] = (1080, 1080),
    crossfade_sec: float = 0.35,
) -> Path:
    if not clips:
        raise ValueError("clips 为空")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if len(clips) == 1 or crossfade_sec <= 0:
        # 直接 concat demuxer
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            for c in clips:
                # ffmpeg concat 需要正斜杠或转义
                p = c.resolve().as_posix().replace("'", r"'\''")
                f.write(f"file '{p}'\n")
            list_path = Path(f.name)
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-r",
            str(fps),
            str(out_path),
        ]
        subprocess.run(cmd, check=True)
        list_path.unlink(missing_ok=True)
        return out_path

    # xfade 链：v0+[1]xfade -> v01; v01+[2]xfade ...
    # offset 累计 = sum(prev durations) - crossfade * n
    n = len(clips)
    inputs: list[str] = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    filter_parts: list[str] = []
    # 统一尺寸/帧率
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,"
            f"crop={size[0]}:{size[1]},fps={fps},format=yuv420p,setsar=1[v{i}]"
        )

    cur = "v0"
    offset = max(0.0, durations[0] - crossfade_sec)
    for i in range(1, n):
        out_label = "vout" if i == n - 1 else f"vx{i}"
        filter_parts.append(
            f"[{cur}][v{i}]xfade=transition=fade:duration={crossfade_sec:.3f}:offset={offset:.3f}[{out_label}]"
        )
        cur = out_label
        if i < n - 1:
            offset += max(0.05, durations[i] - crossfade_sec)

    filt = ";".join(filter_parts)
    cmd = [
        ffmpeg,
        "-y",
        *inputs,
        "-filter_complex",
        filt,
        "-map",
        f"[{cur}]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-r",
        str(fps),
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path
