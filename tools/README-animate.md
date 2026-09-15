# 真动画片段流水线

默认走 xian `runVideo`（Agnes 图生视频 `agnes-video-v2.0`）：

1. 读 `episode.json` / 特写静帧  
2. 注入 `流程/规则/*.txt` + 本集 `style_lock` / `continuity`  
3. 每镜图生视频 → 按 `duration_sec` 裁切  
4. xfade 拼成方屏成片  

## 前置

- 本机已有 `E:\Project\xxg\v-p-s-stack\.env`（含 `XIAN_API_KEY`、`OPENAI_API_BASE`）  
- 本集特写静帧已在：`流程/连续剧/<集>/特写/Sxx_*.png`  
- 依赖：`pip install -r tools/requirements-animate.txt`（一般已装）

## 一键（路怒1 全流程）

在 PowerShell：

```powershell
cd E:\Project\xxg\AI_cartoon_car_accident
python tools/animate_episode.py --episode 流程/连续剧/路怒1 --force
```

约 12 镜；Agnes 免费档大约 1 次/分钟，全集成片可能要十几到几十分钟。已有片段默认会跳过，改提示/规则后要加 `--force`。

## 常用命令

```powershell
# 只试一镜
python tools/animate_episode.py --episode 流程/连续剧/路怒1 --shots S01 --force

# 指定多镜
python tools/animate_episode.py --episode 流程/连续剧/路怒1 --shots S02,S03,S04 --force

# 片段都齐了，只拼接
python tools/animate_episode.py --episode 流程/连续剧/路怒1 --skip-render

# 只渲片段、先不拼
python tools/animate_episode.py --episode 流程/连续剧/路怒1 --skip-concat
```

## 产出

| 路径 | 内容 |
|------|------|
| `流程/连续剧/路怒1/动画片段/Sxx.mp4` | 单镜成片（已裁切） |
| `流程/连续剧/路怒1/动画片段/Sxx_raw.mp4` | Agnes 原始长度 |
| `流程/连续剧/路怒1/路怒1_动画片段拼接.mp4` | 抖音方屏成片 |

## 规则从哪进提示词

- `流程/规则/*.txt`（如 `行驶.txt`）→ 每镜自动注入  
- `episode.json` 的 `style_lock`、`continuity.rules`、`ai_prompt` / `negative_prompt`

改规则后对要重做的镜加 `--force`。

## 参数

| 参数 | 说明 |
|------|------|
| `--backend xian_i2v` | 默认，Agnes 图生视频 |
| `--backend local_morph` | 离线运镜 morph（不调 API） |
| `--shots S01,S03` | 只渲这些镜 |
| `--force` | 覆盖已有片段 |
| `--skip-render` / `--skip-concat` | 只拼 / 只渲 |

## 成片后

当前默认无音轨。发抖音前可用剪映叠 sfx/BGM，片尾加「请勿模仿」。
