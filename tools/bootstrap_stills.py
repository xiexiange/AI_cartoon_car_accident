# -*- coding: utf-8 -*-
"""从角色资产拼夜晚双车道首帧，供 Agnes I2V 使用。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]


def night_road(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (18, 24, 36))
    d = ImageDraw.Draw(im)
    # 天空
    d.rectangle([0, 0, size, int(size * 0.38)], fill=(12, 18, 32))
    # 路面
    d.rectangle([0, int(size * 0.42), size, size], fill=(36, 38, 42))
    # 双车道中线
    y0, y1 = int(size * 0.52), size
    xmid = size // 2
    for y in range(y0, y1, 48):
        d.rectangle([xmid - 4, y, xmid + 4, min(y + 24, y1)], fill=(210, 190, 70))
    # 左右实线
    d.rectangle([int(size * 0.12), y0, int(size * 0.12) + 6, y1], fill=(220, 220, 220))
    d.rectangle([int(size * 0.88) - 6, y0, int(size * 0.88), y1], fill=(220, 220, 220))
    return im


def fit_contain(im: Image.Image, box: tuple[int, int], max_w: int, max_h: int) -> Image.Image:
    im = im.convert("RGBA")
    w, h = im.size
    scale = min(max_w / w, max_h / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def paste_center(base: Image.Image, overlay: Image.Image, cy: float = 0.58) -> None:
    x = (base.width - overlay.width) // 2
    y = int(base.height * cy) - overlay.height // 2
    base.paste(overlay, (x, y), overlay)


def resolve(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / rel


def pick_asset(shot: dict) -> Path | None:
    for sub in shot.get("subjects") or []:
        for key in ("asset_vehicle", "asset_expression", "asset_riding"):
            rel = sub.get(key)
            if rel and resolve(rel).exists():
                return resolve(rel)
    return None


def compose_shot(shot: dict, size: int = 1024) -> Image.Image:
    canvas = night_road(size).convert("RGBA")
    subjects = shot.get("subjects") or []
    n = len(subjects)
    assets: list[Image.Image] = []
    for sub in subjects:
        path = None
        for key in ("asset_vehicle", "asset_riding", "asset_expression"):
            rel = sub.get(key)
            if rel and resolve(rel).exists():
                path = resolve(rel)
                if key == "asset_vehicle":
                    break
        if path:
            assets.append(Image.open(path).convert("RGBA"))
    if not assets:
        primary = pick_asset(shot)
        if not primary:
            raise FileNotFoundError(f"{shot.get('shot_id')} 无可用资产")
        assets = [Image.open(primary).convert("RGBA")]
        n = 1

    if n == 1:
        ov = fit_contain(assets[0], (size, size), int(size * 0.86), int(size * 0.78))
        paste_center(canvas, ov, 0.58)
    else:
        slots = min(3, len(assets))
        max_w = int(size * 0.38)
        max_h = int(size * 0.55)
        xs = [int(size * 0.18), int(size * 0.50), int(size * 0.78)][:slots]
        if slots == 2:
            xs = [int(size * 0.32), int(size * 0.68)]
        for i, asset in enumerate(assets[:slots]):
            ov = fit_contain(asset, (size, size), max_w, max_h)
            x = xs[i] - ov.width // 2
            y = int(size * 0.58) - ov.height // 2
            canvas.paste(ov, (x, y), ov)
    out = canvas.convert("RGB")
    return out.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", default="流程/连续剧/路怒2")
    parser.add_argument("--shots", default="")
    args = parser.parse_args()
    ep_dir = ROOT / args.episode
    episode = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    only = {x.strip() for x in args.shots.split(",") if x.strip()} or None
    shots = episode["shots"]
    if only:
        shots = [s for s in shots if s["shot_id"] in only]
    (ep_dir / "特写").mkdir(parents=True, exist_ok=True)
    for shot in shots:
        out = resolve(shot["output_image"])
        im = compose_shot(shot)
        im.save(out, "PNG")
        print(f"[still] {shot['shot_id']} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
