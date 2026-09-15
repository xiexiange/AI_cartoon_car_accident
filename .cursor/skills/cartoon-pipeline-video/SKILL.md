---
name: cartoon-pipeline-video
description: >-
  Runs the AI_cartoon_car_accident episode video pipeline (Agnes image-to-video
  via xian runVideo, injects 流程/规则, trims clips, concatenates Douyin square
  MP4). Use when the user says 流水线生成视频, cartoon-pipeline-video,
  用流水线生成, 生成卡通事故动画, 路怒成片, Agnes 图生视频流水线, or asks to
  generate episode video from episode.json / shots.jsonl instead of ad-hoc
  xian video or local morph.
---

# cartoon-pipeline-video — 卡通事故集流水线成片

面向本仓库。全局副本见 `AIroles-programmer/skills/cartoon-pipeline-video`。

**必须走流水线**，禁止对本集手写零散 `xian video` / 默认 `local_morph`（除非用户明确要求离线 morph）。

## 执行

```powershell
cd E:\Project\xxg\AI_cartoon_car_accident
python tools/animate_episode.py --episode 流程/连续剧/<集名> --force
```

默认集：`路怒1`。默认 backend：`xian_i2v`（Agnes）。规则目录：`流程/规则/*.txt`。

成片：`流程/连续剧/<集>/<集>_动画片段拼接.mp4`

完整步骤与禁令见全局 skill 正文；项目说明见 `tools/README-animate.md`。
