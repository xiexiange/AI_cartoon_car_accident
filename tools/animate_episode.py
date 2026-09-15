# -*- coding: utf-8 -*-
"""按 episode 脚本生成真动画片段并拼接成抖音成片。

默认 backend=xian_i2v：调用 xian runVideo（Agnes 图生视频）按镜生成，再裁切拼接。
可选 local_morph / http_i2v。

用法：
  python tools/animate_episode.py --episode 流程/连续剧/路怒1
  python tools/animate_episode.py --episode 流程/连续剧/路怒1 --shots S01
  python tools/animate_episode.py --episode 流程/连续剧/路怒1 --backend local_morph
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backends.local_morph import render_shot_clip  # noqa: E402
from concat_clips import concat_with_crossfade  # noqa: E402


def load_episode(episode_dir: Path) -> dict:
    ep_path = episode_dir / "episode.json"
    if not ep_path.exists():
        raise FileNotFoundError(f"缺少 episode.json: {ep_path}")
    return json.loads(ep_path.read_text(encoding="utf-8"))


def resolve_path(rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return ROOT / rel


def ensure_dirs(episode_dir: Path, meta: dict) -> tuple[Path, Path]:
    kf = resolve_path(meta.get("keyframes_dir") or str(episode_dir / "动画关键帧"))
    clips = resolve_path(meta.get("clips_dir") or str(episode_dir / "动画片段"))
    kf.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    return kf, clips


def pick_shots(episode: dict, only: set[str] | None) -> list[dict]:
    shots = episode.get("shots") or []
    if only:
        shots = [s for s in shots if s.get("shot_id") in only]
    return shots


def main() -> int:
    parser = argparse.ArgumentParser(description="路怒连续剧：真动画片段生成 + 拼接")
    parser.add_argument(
        "--episode",
        default="流程/连续剧/路怒1",
        help="分集目录（相对仓库根）",
    )
    parser.add_argument("--shots", default="", help="仅生成这些镜头，逗号分隔，如 S01,S02")
    parser.add_argument(
        "--backend",
        choices=["xian_i2v", "local_morph", "http_i2v"],
        default=os.environ.get("ANIMATE_BACKEND", "xian_i2v"),
    )
    parser.add_argument("--skip-render", action="store_true", help="跳过渲染，只拼接已有片段")
    parser.add_argument("--skip-concat", action="store_true", help="只渲染片段，不拼接")
    parser.add_argument("--force", action="store_true", help="强制重渲已有片段")
    args = parser.parse_args()

    episode_dir = resolve_path(args.episode)
    episode = load_episode(episode_dir)
    anim = episode.get("animation_meta") or {}
    fps = int(anim.get("fps") or 24)
    res = anim.get("resolution") or [1080, 1080]
    size = (int(res[0]), int(res[1]))
    kf_dir, clips_dir = ensure_dirs(episode_dir, anim)

    only = {x.strip() for x in args.shots.split(",") if x.strip()} or None
    shots = pick_shots(episode, only)
    if not shots:
        print("没有可处理的镜头", file=sys.stderr)
        return 1

    print(f"episode={episode.get('episode_id')} shots={len(shots)} backend={args.backend}")
    print(f"keyframes={kf_dir}")
    print(f"clips={clips_dir}")

    clip_paths: list[Path] = []
    durations: list[float] = []

    for shot in shots:
        sid = shot["shot_id"]
        dur = float(shot.get("duration_sec") or 2.0)
        still_rel = shot.get("output_image")
        if not still_rel:
            print(f"[skip] {sid}: 无 output_image", file=sys.stderr)
            continue
        still = resolve_path(still_rel)
        if not still.exists():
            print(f"[skip] {sid}: 特写不存在 {still}", file=sys.stderr)
            continue

        out_clip = clips_dir / f"{sid}.mp4"
        durations.append(dur)
        clip_paths.append(out_clip)

        if args.skip_render:
            continue
        if out_clip.exists() and not args.force:
            print(f"[keep] {sid} -> {out_clip.name}")
            continue

        print(f"[render] {sid} {dur}s motion={shot.get('camera', {}).get('motion')}")
        if args.backend == "xian_i2v":
            from backends.xian_i2v import render_shot_clip_xian

            render_shot_clip_xian(
                still_path=still,
                shot=shot,
                out_path=out_clip,
                workspace=ROOT,
                fps=fps,
                size=size,
                episode=episode,
            )
        elif args.backend == "local_morph":
            render_shot_clip(
                still_path=still,
                shot=shot,
                out_path=out_clip,
                keyframes_dir=kf_dir,
                fps=fps,
                size=size,
            )
        else:
            from backends.http_i2v import render_shot_clip_http

            render_shot_clip_http(
                still_path=still,
                shot=shot,
                out_path=out_clip,
                fps=fps,
                size=size,
            )
        print(f"[ok] {out_clip}")
        gap = int(os.environ.get("ANIMATE_SHOT_GAP_SEC", "60" if args.backend == "xian_i2v" else "0"))
        if gap > 0 and shot is not shots[-1]:
            print(f"[wait] {gap}s（Agnes RPM）", flush=True)
            time.sleep(gap)

    if args.skip_concat:
        print("已跳过拼接")
        return 0

    missing = [p for p in clip_paths if not p.exists()]
    if missing:
        print("缺少片段，无法拼接:", *[str(p) for p in missing], sep="\n  ", file=sys.stderr)
        return 2

    out_video = resolve_path(
        episode.get("output_video_clips_concat")
        or str(episode_dir / f"{episode.get('episode_id', 'episode')}_动画片段拼接.mp4")
    )
    crossfade = float((episode.get("video_meta") or {}).get("crossfade_sec") or 0.35)
    concat_with_crossfade(
        clips=clip_paths,
        durations=durations,
        out_path=out_video,
        fps=fps,
        size=size,
        crossfade_sec=crossfade,
    )
    print(f"[done] {out_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
