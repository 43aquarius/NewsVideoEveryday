#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时讯视频 TTS 补齐守护: 限流窗口内轮询, 解除后自动补齐语音并组装+出检查帧

流程(自动, 到 stills 为止; VLM 审帧/review/render 由主 agent 人工接手):
  1. 每 170s 尝试 node scripts/tts-zai.mjs ... --execute (缓存自动跳过已合成句)
  2. voice/ 下 audio.wav 数 == edition 句数 → assemble → npm run stills
  3. 成功后写 runs/agi-<issue>/TOPUP_DONE 标记, 退出
"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, "runs", "agi-20261023")
EDITION = os.path.join(RUN_DIR, "edition.json")
MARK = os.path.join(RUN_DIR, "TOPUP_DONE")
LOG = open(os.path.join(RUN_DIR, "topup.log"), "a")


def log(msg):
    LOG.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    LOG.flush()
    print(msg, flush=True)


def total_cues():
    with open(EDITION) as f:
        e = json.load(f)
    return sum(len(s["cues"]) for s in e["stories"])


def done_count():
    return len(glob.glob(os.path.join(RUN_DIR, "voice", "*", "audio.wav")))


def sh(cmd, cwd=HERE):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    log(f"$ {' '.join(cmd[:4])}... rc={r.returncode} | {' / '.join(tail)}")
    return r.returncode == 0


def main():
    need = total_cues()
    log(f"start: need {need} cues, have {done_count()}")
    for attempt in range(40):  # 最多 ~2 小时
        if os.path.exists(MARK):
            log("already done")
            return
        have = done_count()
        if have >= need:
            break
        rc = sh(["node", "scripts/tts-zai.mjs", EDITION, RUN_DIR, "--execute"])
        have = done_count()
        log(f"attempt {attempt+1}: have {have}/{need}")
        if have >= need:
            break
        time.sleep(170)
    else:
        log("GAVE UP after 40 attempts")
        return
    log(f"voice complete: {need} cues")
    if sh(["node", "scripts/assemble.mjs", EDITION, RUN_DIR]):
        if sh(["npm", "run", "stills"]):
            with open(MARK, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            log("TOPUP_DONE ✓ (stills ready, awaiting VLM review + render)")


if __name__ == "__main__":
    main()
