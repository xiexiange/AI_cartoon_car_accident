# -*- coding: utf-8 -*-
"""可选：HTTP 图生视频 backend。

环境变量：
  ANIMATE_I2V_URL     必填，如 https://api.example.com/v1/videos
  ANIMATE_I2V_TOKEN   可选 Bearer token
  ANIMATE_I2V_MODE    sync_b64 | async_url（默认 sync_b64）

sync_b64 约定请求 JSON：
  { "prompt", "image_b64", "duration", "width", "height", "fps" }
响应：
  { "b64_video": "..." } 或 { "video_b64": "..." }

async_url 约定：
  POST 同上（可用 image_url 若服务端支持）
  响应 { "task_id" }
  GET {ANIMATE_I2V_URL}/{task_id} -> { "status":"done", "url":"..." }
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def _build_prompt(shot: dict) -> str:
    prompt = (shot.get("ai_prompt") or "").strip()
    neg = (shot.get("negative_prompt") or "").strip()
    action_bits = []
    for sub in shot.get("subjects") or []:
        if sub.get("action"):
            action_bits.append(str(sub["action"]))
    cam = shot.get("camera") or {}
    motion = cam.get("motion") or "固定"
    extra = f"镜头运动:{motion}。动作:{'；'.join(action_bits)}"
    text = f"{prompt} {extra}".strip()
    if neg:
        text += f" Avoid: {neg}"
    return text


def _post_json(url: str, payload: dict, token: str | None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str | None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_shot_clip_http(
    *,
    still_path: Path,
    shot: dict,
    out_path: Path,
    fps: int = 24,
    size: tuple[int, int] = (1080, 1080),
) -> Path:
    url = os.environ.get("ANIMATE_I2V_URL", "").strip()
    if not url:
        raise RuntimeError("http_i2v 需要环境变量 ANIMATE_I2V_URL")
    token = os.environ.get("ANIMATE_I2V_TOKEN", "").strip() or None
    mode = os.environ.get("ANIMATE_I2V_MODE", "sync_b64").strip()
    duration = float(shot.get("duration_sec") or 2.0)
    image_b64 = base64.b64encode(still_path.read_bytes()).decode("ascii")
    payload = {
        "prompt": _build_prompt(shot),
        "image_b64": image_b64,
        "duration": duration,
        "width": size[0],
        "height": size[1],
        "fps": fps,
        "shot_id": shot.get("shot_id"),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "sync_b64":
        result = _post_json(url, payload, token)
        b64 = result.get("b64_video") or result.get("video_b64")
        if not b64:
            raise RuntimeError(f"响应缺少 b64_video: keys={list(result)[:12]}")
        out_path.write_bytes(base64.b64decode(b64))
        return out_path

    # async_url
    created = _post_json(url, payload, token)
    task_id = created.get("task_id") or created.get("id")
    if not task_id:
        raise RuntimeError(f"响应缺少 task_id: {created}")
    poll_url = created.get("poll_url") or f"{url.rstrip('/')}/{task_id}"
    for _ in range(180):
        time.sleep(5)
        st = _get_json(poll_url, token)
        status = (st.get("status") or "").lower()
        if status in {"done", "success", "succeeded", "completed"}:
            video_url = st.get("url") or st.get("video_url")
            if not video_url:
                raise RuntimeError(f"完成但无 url: {st}")
            with urllib.request.urlopen(video_url, timeout=300) as resp:
                out_path.write_bytes(resp.read())
            return out_path
        if status in {"failed", "error"}:
            raise RuntimeError(f"任务失败: {st}")
    raise TimeoutError(f"轮询超时: {poll_url}")
