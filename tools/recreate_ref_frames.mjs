#!/usr/bin/env node
/**
 * 1:1 复刻：
 * - cabin → 原帧夜车内底 + 私家车司机三视图/表情去底换头
 * - lever/hand/pedal/dash/end → 原帧去水印 + 角标身份
 * - pov/exterior/mirror → Agnes 图生图（原帧唯一参考）
 *
 *   node tools/recreate_ref_frames.mjs --all --force
 *   node tools/recreate_ref_frames.mjs --frames 00s,06s --force
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..');
const VPS = path.resolve(ROOT, '..', 'v-p-s-stack');
const { runImage } = await import(
  pathToFileURL(path.join(VPS, 'xian/packages/runtime/src/image/generate.js')).href
);

const MAP = path.join(ROOT, '流程/连续剧/路怒2/1比1复刻/frame_map.json');
const LOCAL_KINDS = new Set(['cabin', 'lever', 'hand', 'pedal', 'dash', 'end']);

function applyEnvFile(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return;
  for (const raw of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const i = line.indexOf('=');
    const key = line.slice(0, i).trim();
    let val = line.slice(i + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = val;
  }
}

applyEnvFile(path.join(VPS, '.env'));
applyEnvFile(path.join(ROOT, '.env'));

function parseArgs(argv) {
  const out = { frames: [], force: false, all: false, sleepMs: 2500 };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === '--all') out.all = true;
    else if (a === '--force') out.force = true;
    else if (a === '--frames') out.frames = next().split(',').map((s) => s.trim()).filter(Boolean);
    else if (a === '--sleep-ms') out.sleepMs = Number(next()) || 2500;
  }
  return out;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function compositeLocal(srcAbs, assetAbsList, outAbs, kind, expression) {
  const assetsArg = assetAbsList.join(';');
  const standing = path.join(ROOT, '流程/人物/私家车司机/三视图_正面.png');
  const py = `
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path

def cut_bg(im):
    im = im.convert('RGBA')
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 235 and g > 230 and b > 210:
                px[x, y] = (0, 0, 0, 0)
            elif r > 220 and g > 220 and b > 220 and abs(r - g) < 12 and abs(g - b) < 12:
                px[x, y] = (0, 0, 0, 0)
    return im

src = Image.open(r'''${srcAbs.replace(/'/g, "\\'")}''').convert('RGBA')
W, H = src.size
out = src.copy()
d = ImageDraw.Draw(out)
# 去抖音水印
d.rectangle([0, 0, int(W * 0.42), int(H * 0.2)], fill=(28, 30, 40, 255))
d.rectangle([int(W * 0.62), int(H * 0.78), W, H], fill=(28, 30, 40, 255))

assets = [p for p in r'''${assetsArg.replace(/'/g, "\\'")}'''.split(';') if p]
kind = r'''${kind}'''
expr_name = r'''${expression || ''}'''

# 选叠加图：表情优先（非冷静闭眼时），否则三视图头肩
overlay = None
face = None
for p in assets:
    name = Path(p).name
    if '表情' in name:
        face = cut_bg(Image.open(p))
        break
if kind == 'cabin':
    # 冷静闭眼不适合开车：用三视图头肩；有怒/惊等表情则用表情
    use_face = face is not None and expr_name and expr_name not in ('冷静',)
    if use_face:
        overlay = face
        bb = overlay.split()[-1].getbbox()
        if bb: overlay = overlay.crop(bb)
    else:
        overlay = cut_bg(Image.open(r'''${standing.replace(/'/g, "\\'")}'''))
        bb = overlay.split()[-1].getbbox()
        if bb: overlay = overlay.crop(bb)
        overlay = overlay.crop((0, 0, overlay.width, int(overlay.height * 0.42)))
    # 盖住原主角脸
    d.ellipse([int(W*0.16), int(H*0.02), int(W*0.84), int(H*0.95)], fill=(36, 38, 52, 255))
    th = int(H * 0.82)
    scale = th / overlay.height
    nw, nh = max(1, int(overlay.width * scale)), max(1, int(overlay.height * scale))
    ov = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (W - nw) // 2, int(H * 0.05)
    out.paste(ov, (x, y), ov.split()[-1])
    d = ImageDraw.Draw(out)
    d.arc([int(W*0.28), int(H*0.78), int(W*0.72), int(H*1.28)], 200, 340, fill=(25, 25, 30, 255), width=12)
elif kind == 'end':
    if face is None:
        face = cut_bg(Image.open(r'''${standing.replace(/'/g, "\\'")}'''))
        bb = face.split()[-1].getbbox()
        if bb: face = face.crop(bb)
        face = face.crop((0, 0, face.width, int(face.height * 0.42)))
    else:
        bb = face.split()[-1].getbbox()
        if bb: face = face.crop(bb)
    # 深蓝底 + 圆形头像
    out = Image.new('RGBA', (W, H), (18, 24, 40, 255))
    side = int(min(W, H) * 0.42)
    scale = side / max(face.width, face.height)
    nw, nh = max(1, int(face.width * scale)), max(1, int(face.height * scale))
    ov = face.resize((nw, nh), Image.Resampling.LANCZOS)
    cx, cy = W // 2, int(H * 0.38)
    # circular mask
    mask = Image.new('L', (nw, nh), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, nw-1, nh-1], fill=255)
    out.paste(ov, (cx - nw // 2, cy - nh // 2), mask)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle([int(W*0.18), int(H*0.62), int(W*0.82), int(H*0.74)], radius=18, outline=(220,220,230,255), width=3)
else:
    # lever/hand/pedal/dash：保原动作构图，左上角贴身份
    badge = face
    if badge is None and assets:
        badge = cut_bg(Image.open(assets[0]))
    if badge is not None:
        bb = badge.split()[-1].getbbox()
        if bb: badge = badge.crop(bb)
        tw = int(W * 0.2)
        scale = tw / badge.width
        nw, nh = max(1, int(badge.width * scale)), max(1, int(badge.height * scale))
        ov = badge.resize((nw, nh), Image.Resampling.LANCZOS)
        out.alpha_composite(ov, (10, int(H * 0.22)))

rgb = ImageEnhance.Contrast(out.convert('RGB')).enhance(1.05)
Path(r'''${outAbs.replace(/'/g, "\\'")}''').parent.mkdir(parents=True, exist_ok=True)
rgb.save(r'''${outAbs.replace(/'/g, "\\'")}''', 'PNG')
`;
  const r = spawnSync('python', ['-c', py], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(r.stderr || r.stdout || 'composite failed');
}

function buildPrompt(fid, meta) {
  const beat = meta.beat || '';
  const kind = meta.kind || '';
  return [
    '只输出一张完整横版卡通镜头，禁止分栏拼贴故事板。',
    '严格保持参考图构图机位透视车道灯光远光位置1:1，仅替换车辆人物外观。',
    '黄车男→戴眼镜深蓝外套私家车司机开银色轿车；红车→白色网约车；蓝货车→大型厢式货车；深色SUV→蓝灰工用车。',
    `镜头:${kind}。节拍:${beat}。`,
    meta.note || '',
    '夜晚高速公路扁平黑描边。去掉抖音水印字幕。禁止写实，禁止修车下车无关人物。',
  ]
    .filter(Boolean)
    .join(' ');
}

async function genAgnes(srcAbs, outAbs, prompt) {
  const rel = path.relative(ROOT, srcAbs).replace(/\\/g, '/');
  const result = await runImage(
    {
      cwd: ROOT,
      workspace: ROOT,
      quiet: false,
      outputDir: '.xian/generated',
      imageSize: '1344x768',
      onProgress: (line) => console.error(line),
    },
    {
      prompt,
      size: '1344x768',
      referencePath: rel,
      model: 'agnes-image-2.0-flash',
    }
  );
  fs.copyFileSync(result.absPath, outAbs);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const map = JSON.parse(fs.readFileSync(MAP, 'utf8'));
  const srcDir = path.join(ROOT, map.source_frames_dir);
  const outDir = path.join(ROOT, map.output_dir);
  fs.mkdirSync(outDir, { recursive: true });

  let ids = Object.keys(map.frames).sort(
    (a, b) => Number(a.replace('s', '')) - Number(b.replace('s', ''))
  );
  if (!args.all) {
    if (!args.frames.length) {
      console.error('请指定 --all 或 --frames 00s,06s');
      process.exit(2);
    }
    ids = args.frames.map((x) => (x.endsWith('s') ? x : `${x}s`));
  }

  let ok = 0;
  let skip = 0;
  let fail = 0;
  for (const fid of ids) {
    const meta = map.frames[fid];
    if (!meta) {
      console.error(`[miss] ${fid}`);
      fail += 1;
      continue;
    }
    const outAbs = path.join(outDir, `${fid}.png`);
    if (fs.existsSync(outAbs) && !args.force) {
      console.log(`[skip] ${fid}`);
      skip += 1;
      continue;
    }
    const srcAbs = path.join(srcDir, `${fid}.png`);
    if (!fs.existsSync(srcAbs)) {
      console.error(`[miss-src] ${srcAbs}`);
      fail += 1;
      continue;
    }
    const assets = (meta.assets || [])
      .map((rel) => path.join(ROOT, rel))
      .filter((p) => fs.existsSync(p));
    try {
      if (LOCAL_KINDS.has(meta.kind)) {
        console.log(`[local] ${fid} kind=${meta.kind}`);
        compositeLocal(srcAbs, assets, outAbs, meta.kind, meta.expression || '');
      } else {
        console.log(`[agnes] ${fid} kind=${meta.kind}`);
        await genAgnes(srcAbs, outAbs, buildPrompt(fid, meta));
        if (args.sleepMs > 0) await sleep(args.sleepMs);
      }
      console.log(`[ok] ${fid}`);
      ok += 1;
    } catch (err) {
      console.error(`[fail] ${fid}: ${err.message || err}`);
      fail += 1;
      if (!LOCAL_KINDS.has(meta.kind) && args.sleepMs > 0) await sleep(args.sleepMs);
    }
  }
  console.log(JSON.stringify({ ok, skip, fail, outDir }, null, 2));
  process.exit(fail ? 1 : 0);
}

main();
