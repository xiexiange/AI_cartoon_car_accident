# -*- coding: utf-8 -*-
"""通过 xian runVideo（Agnes 图生视频）渲一镜。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from concat_clips import trim_clip

XIAN_SCRIPT = Path(
    os.environ.get(
        "XIAN_I2V_SCRIPT",
        r"E:\Project\xxg\v-p-s-stack\xian\scripts\cartoon-shot-i2v.mjs",
    )
)
XIAN_CWD = Path(os.environ.get("XIAN_ROOT", r"E:\Project\xxg\v-p-s-stack\xian"))
RULES_DIR_NAME = "流程/规则"


def load_project_rules(workspace: Path) -> str:
    """读取 流程/规则/*.txt，按文件名排序拼成固定规则段。"""
    rules_dir = workspace / RULES_DIR_NAME
    if not rules_dir.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(rules_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        # 压成单段，避免提示词过碎
        compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
        chunks.append(f"【规则·{path.stem}】{compact}")
    return " ".join(chunks)


def _style_lock_line(episode: dict | None) -> str:
    if not episode:
        return "扁平二次元矢量卡通，干净黑描边，浅色城市道路背景，禁止写实摄影。"
    lock = episode.get("style_lock") or {}
    bits = [
        "扁平二次元矢量卡通，干净黑描边，浅色城市道路背景，禁止写实摄影。",
        "无对白、无字幕、无气泡文字。角色与车辆外观必须锁定参考图，禁止换脸换车。",
    ]
    if lock.get("must_match_assets"):
        bits.append("必须匹配已给定资产外观，禁止换脸换车换型。")
    if lock.get("no_photorealism"):
        bits.append("禁止写实摄影感。")
    cont = episode.get("continuity") or {}
    for rule in cont.get("rules") or []:
        bits.append(str(rule))
    return " ".join(bits)


def _build_prompt(shot: dict, *, workspace: Path, episode: dict | None = None) -> str:
    cam = shot.get("camera") or {}
    motion = cam.get("motion") or "固定"
    angle = cam.get("angle") or "平视"
    size = cam.get("shot_size") or "特写"
    actions = "；".join(
        str(s.get("action") or "") for s in (shot.get("subjects") or []) if s.get("action")
    )
    prompt = (shot.get("ai_prompt") or "").strip()
    neg = (shot.get("negative_prompt") or "").strip()
    project_rules = load_project_rules(workspace)
    parts = [
        _style_lock_line(episode),
        project_rules,
        f"景别{size}，{angle}，镜头{motion}。",
        prompt,
        f"动作：{actions}" if actions else "",
        "只做小幅度真实动作与运镜，保持构图稳定；未写变道/转弯时保持车道内笔直行驶。",
        f"避免：{neg}" if neg else "",
    ]
    return " ".join(p for p in parts if p)


def _extra_refs(shot: dict, still: Path, root: Path) -> list[Path]:
    refs: list[Path] = []
    seen = {still.resolve()}
    for rel in shot.get("reference_images") or []:
        p = Path(rel)
        if not p.is_absolute():
            p = root / rel
        if p.exists() and p.resolve() not in seen:
            refs.append(p)
            seen.add(p.resolve())
        if len(refs) >= 2:
            break
    return refs


def render_shot_clip_xian(
    *,
    still_path: Path,
    shot: dict,
    out_path: Path,
    workspace: Path,
    fps: int = 24,
    size: tuple[int, int] = (1080, 1080),
    episode: dict | None = None,
) -> Path:
    del size  # Agnes 用 1024x1024，拼接时再缩放到成片分辨率
    if not XIAN_SCRIPT.exists():
        raise FileNotFoundError(f"找不到 xian 图生视频脚本: {XIAN_SCRIPT}")

    prompt = _build_prompt(shot, workspace=workspace, episode=episode)
    extras = _extra_refs(shot, still_path, workspace)
    raw_out = out_path.with_name(out_path.stem + "_raw.mp4")

    cmd = [
        "node",
        str(XIAN_SCRIPT),
        "--workspace",
        str(workspace),
        "--still",
        str(still_path),
        "--out",
        str(raw_out),
        "--prompt",
        prompt,
        "--size",
        os.environ.get("XIAN_VIDEO_SIZE", "1024x1024"),
        "--frames",
        os.environ.get("XIAN_VIDEO_FRAMES", "81"),
    ]
    for extra in extras:
        cmd.extend(["--extra-ref", str(extra)])

    print(f"[xian-i2v] {shot.get('shot_id')} refs={1 + len(extras)}", flush=True)
    print(f"[xian-i2v] prompt_len={len(prompt)} rules={'yes' if load_project_rules(workspace) else 'no'}", flush=True)
    proc = subprocess.run(
        cmd,
        cwd=str(XIAN_CWD),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        if not proc.stderr.endswith("\n"):
            sys.stderr.write("\n")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"xian 图生视频失败: {err[-2000:]}")

    last_json = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last_json = line
    if last_json:
        print(f"[xian-i2v] {last_json}", flush=True)
    if not raw_out.exists():
        raise RuntimeError("xian 未写出 raw mp4")

    duration = float(shot.get("duration_sec") or 2.0)
    trim_clip(raw_out, out_path, duration, fps=fps)
    return out_path
