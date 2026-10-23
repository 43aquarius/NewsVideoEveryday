// tts-zai.mjs — 用本环境 z-ai-web-dev-sdk TTS 产出与 tts.mjs 完全兼容的
// voice/ 目录协议(audio.wav + meta.json + voice-manifest.json)。
// 与上游 tts.mjs(MiniMax, 收费)平行的免费通道; assemble.mjs 无需改动。
//
// 用法: node scripts/tts-zai.mjs runs/<ep>/edition.json runs/<ep> [--execute]
// 不带 --execute 为 dry run; z-ai TTS 为环境内置免费能力, --execute 无费用。
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { pathToFileURL } from "node:url";
import { ROOT, read, write, hash, wav, pcm, voiceKey, validate, safe, lock } from "./lib.mjs";

const execFileP = promisify(execFile);
const ZAI_VOICE = process.env.ZAI_TTS_VOICE || "tongtong";
const ZAI_SPEED = 1.1; // 与上游口径一致, 直接交给引擎, 不做后期变速
const ENDPOINT = "zai-local-tts";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function ttsWithRetry(zai, { text, tries = 5 }) {
  let delay = 4000;
  for (let i = 0; i < tries; i++) {
    try {
      return await zai.audio.tts.create({
        input: text,
        voice: ZAI_VOICE,
        speed: ZAI_SPEED,
        response_format: "wav",
        stream: false,
      });
    } catch (e) {
      const msg = String(e?.message || e);
      if (i === tries - 1 || !/429|Too many/i.test(msg)) throw e;
      console.log(`  [429] rate-limited, retry in ${delay / 1000}s...`);
      await sleep(delay);
      delay = Math.min(delay * 2, 30000);
    }
  }
}

async function synthesizeOne(zai, { text, dir }) {
  const voice = {
    endpoint: ENDPOINT,
    model: "z-ai-tts",
    voiceId: ZAI_VOICE,
    speed: ZAI_SPEED,
    emotion: "neutral",
    sampleRate: 32000,
  };
  const key = voiceKey(text, voice);
  const target = path.join(dir, key);
  const meta = path.join(target, "meta.json");
  const audio = path.join(target, "audio.wav");
  // 缓存: 输入未变则复用(与上游协议一致)
  if (fs.existsSync(meta) && fs.existsSync(audio)) {
    const m = read(meta), b = fs.readFileSync(audio);
    if (m.key === key && m.sha256 === hash(b)) {
      pcm(b); // 校验格式
      return { ...m, file: audio, cached: true };
    }
    throw Error(`Cache hash mismatch at ${target}; retain and investigate`);
  }
  // 合成(24kHz mono 16bit wav) → ffmpeg 重采样 32kHz s16le → 标准44字节头
  const response = await ttsWithRetry(zai, { text });
  const raw = Buffer.from(new Uint8Array(await response.arrayBuffer()));
  if (!raw.length || raw.toString("ascii", 0, 4) !== "RIFF")
    throw Error(`TTS returned non-WAV payload (${raw.length} bytes)`);
  const tmpIn = path.join(target, "raw-24k.wav");
  fs.mkdirSync(target, { recursive: true });
  fs.writeFileSync(tmpIn, raw);
  const tmpOut = path.join(target, "resampled.pcm");
  await execFileP("ffmpeg", [
    "-y", "-loglevel", "error", "-i", tmpIn,
    "-f", "s16le", "-ar", "32000", "-ac", "1", tmpOut,
  ]);
  const data = fs.readFileSync(tmpOut);
  const bytes = wav(data); // 44字节头 + 32000Hz mono 16bit PCM
  fs.unlinkSync(tmpIn);
  fs.unlinkSync(tmpOut);
  fs.writeFileSync(audio, bytes, { flag: "wx" });
  const m = {
    key,
    text,
    voice,
    duration: (bytes.length - 44) / 64000,
    sha256: hash(bytes),
    timing: "per-phrase-synthesis-boundaries",
    engine: "z-ai-web-dev-sdk",
  };
  write(meta, m);
  return { ...m, file: audio, cached: false };
}

async function main() {
  const [editionFile, runArg, ...flags] = process.argv.slice(2);
  if (!editionFile || !runArg || flags.some((f) => f !== "--execute"))
    throw Error("Usage: tts-zai.mjs runs/<ep>/edition.json runs/<ep> [--execute]");
  const edition = validate(read(editionFile)), run = safe(ROOT, runArg);
  const execute = flags.includes("--execute");
  const { default: ZAI } = await import("z-ai-web-dev-sdk");
  const zai = await ZAI.create();
  const release = lock(run);
  try {
    const cues = [];
    for (const story of edition.stories)
      for (let index = 0; index < story.cues.length; index++) {
        const cue = story.cues[index];
        if (!execute) {
          cues.push({ storyId: story.id, index, status: "would-synthesize", text: cue.text });
          console.log(`${story.id}/${index}: would-synthesize`);
          continue;
        }
        const result = await synthesizeOne(zai, {
          text: cue.text,
          dir: path.join(run, "voice"),
        });
        cues.push({
          storyId: story.id,
          index,
          ...result,
          file: result.file ? path.relative(run, result.file) : undefined,
        });
        console.log(
          `${story.id}/${index}: ${result.cached ? "cached" : "synthesized"} (${result.duration.toFixed(2)}s)`,
        );
        await sleep(1500); // 引擎限流保护: 句间 1.5s
      }
    if (execute) {
      write(path.join(run, "voice-manifest.json"), {
        editionHash: hash(JSON.stringify(edition)),
        cues,
        engine: "z-ai-web-dev-sdk",
      });
      const total = cues.reduce((s, c) => s + (c.duration || 0), 0);
      console.log(`voice-manifest.json written; narration total ${total.toFixed(1)}s`);
    } else {
      console.log("Dry run only; add --execute to synthesize (z-ai engine, no cost)");
    }
  } finally {
    release();
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch((e) => {
    console.error(e.message);
    process.exitCode = 1;
  });
