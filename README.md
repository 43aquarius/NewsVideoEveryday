# 资讯视频生成项目

**把流程告诉 AI，让 Agent 从 RSS 线索完成一支资讯视频**

RSS / RSSHub → 原文核验与选题 → 截图 / 演示 → 自然口播 → MiniMax 配音 → 逐句字幕 → Remotion 动画 → 检查与本地交付

这是一套从实际资讯视频流程抽离的独立工作流与脚本，适用于 AI、科技、财经、游戏等资讯领域。Codex 可执行整套流程；其他具备文件、命令行和浏览能力的 Agent 也可使用同一入口。**不是安装后无人值守、自动判断一切的新闻机器人**：事实核验、事件合并、内容选择和实际看图由 Agent 按任务完成，脚本负责可重复执行的采集、音频、时序和渲染。

仓库不包含原作者的人物、Logo、私人音色、密钥、订阅清单、历史稿件或视频。默认提供蓝白 16:9、60fps 的通用模板；静音示例只用于验证布局，不是真实新闻或真实配音。

## 先跑通模板

需要 Node.js 22+、npm；交付检查另需 FFmpeg 与 ffprobe。安装只发生在当前项目目录。

```bash
npm ci
npm run demo
npm run check
npm test
npx playwright install chromium
npm run dev
```

打开终端显示的 Studio 地址，选择 `NewsVideo`。`npm run demo` 生成约 12 秒的**静音示例**，不调用网络 API，不花费配音费用。它会替换 `public/` 的当前预览，正式工程输入和音频缓存仍保留在 `runs/`，重新 assemble 即可切回。

## 让 Agent 制作一期

把以下要求和本仓库交给 Agent：

> 阅读 skills/news-video-generator/SKILL.md，使用 examples/feeds.json 的 RSS 做一次采集，制作一支资讯视频，保留关键产品的用途、实例和开放条件。先给我预览，再按我的要求导出。不要上传我的私人素材

Agent 入口：[SKILL.md](skills/news-video-generator/SKILL.md)；详细约定：[工作流与编辑](docs/workflow.md)、[数据格式](docs/data.md)、[制作命令](docs/production.md)。该入口不依赖其他本机技能或固定用户目录。

信息源使用 GitHub 上的 [RSSHub](https://github.com/DIYgod/RSSHub) 和标准 RSS / Atom。示例订阅为 RSSHub 仓库的公开 release Atom，**仅演示采集方法**，实际资讯源需自行配置。没有强制订阅服务或聚合平台依赖，也没有定时两轮采集。

## 实际制作命令

```bash
# 一次采集，冻结原始 feed、窗口与去重结果
npm run collect -- examples/feeds.json runs/episode/intake
# Agent 阅读 intake，核对原始公告，编写 edition.json 和 capture-jobs.json
npm run capture -- runs/episode/capture-jobs.json runs/episode/evidence
# 实际看图后，每张图单独确认，不把截图成功当成审核通过
node scripts/capture-review.mjs runs/episode/evidence/source-1.json --approved --notes="已核对正文与截图清晰度"
# 根据 examples/edition.json 写真实文稿后再运行配音
cp .env.example .env
# 仅在本机 .env 中填写你自己的 API Key 和完整 voice_id
npm run tts -- runs/episode/edition.json runs/episode
# 上一句只是 dry run；下面明确执行付费配音
npm run tts -- runs/episode/edition.json runs/episode --execute
npm run assemble -- runs/episode/edition.json runs/episode
npm run dev
npm run stills
# 检查输出目录中全部帧和封面后才记录实际审核
npm run review -- out/STILLS_TIMESTAMP --approved --notes="记录实际检查范围及未检查内容"
npm run render
npm run deliver -- out/RENDER_TIMESTAMP/render-report.json runs/episode/delivery-v1
```

所有时间戳目录均替换成实际命令输出，来源截图 ID 也替换为真实值。每次导出使用新目录，不覆盖交付。付费 TTS 不会由采集、测试、预览或 CI 自动触发。

## 能力与边界

- RSS/Atom 窗口过滤、URL 规范化去重、原始 feed 冻结、失败源记录；不同链接描述同一事件由 Agent 合并
- 隔离 Playwright 原文截图、正文留档、SHA-256 和实际看图记录；不借用个人浏览器登录状态
- MiniMax 完整 voice_id 外置、情绪按语义、统一 1.1 倍速、逐句合成及内容缓存；句间默认 350ms，可按语义调整
- 字幕绑定实际每句 PCM 音频的边界，**不是逐字强制对齐**；需要词级口型/逐字高亮时，可用可选声学复核脚本，再扩展模板，不把按字数估计冒充声学对齐
- 同一企业集中播报、按企业进度条、截图与静音视频素材按 cue 切换、动画要点、顶部快讯、蓝白封面
- 当前通用模板没有个人形象或口型模型；自定义人物和声音应在本地接入，不应提交进开源包
- 输出 1920×1080 / 60fps H.264 / AAC，字幕、双比例封面、来源发布稿和技术检查；不会自动发布视频

## 开源与隐私

本项目自己的代码和工作流采用 MIT；[Remotion](https://www.remotion.dev/docs/license) 使用其独立许可证，不能用本项目 MIT 替代。RSSHub 是独立 AGPL 项目，这里通过标准 feed 使用它，没有复制其源代码。MiniMax、网页截图和第三方素材仍按各自条款使用。

`runs/`、`public/`、`out/`、`dist/`、`.env*`、依赖与缓存默认不提交。发布脚本采用明确文件清单，不靠 `.gitignore` 猜测哪些文件可公开：

```bash
npm run audit
npm run package
```

打包结果在 `dist/`，包括源码 ZIP 与 SHA-256。新增公开文件需同时更新 `release-files.json`。如果 fork 后加入私有素材，发布前仍应人工检查归档内容，扫描不能证明不存在所有未知隐私。

---

# 定制版说明（AI2Everyday 集成 · 2026-10-23）

本仓库 fork 自 [mmsx4717/news-video-generator](https://github.com/mmsx4717/news-video-generator)（MIT），上游的完整文档（README 前半部分、`docs/`、`skills/`）全部保留且仍然有效。本节只说明 **AI2Everyday 矩阵的定制增量**：把它接入现有「时讯」产线，用本环境免费的 z-ai TTS 引擎替代 MiniMax（付费）。

## 定制内容

| 增量 | 位置 | 作用 |
|------|------|------|
| `tts-zai.mjs` | scripts/ | **免费 TTS 通道**：z-ai-web-dev-sdk 引擎，产出与上游 `tts.mjs`（MiniMax）完全兼容的 `voice/` 目录协议（audio.wav + meta.json + voice-manifest.json），`assemble.mjs` 零改动直接消费。内置 429 退避重试与句间 1.5s 限流保护 |
| `edition_maker.py` | 根目录 | **时讯桥**：复用 `AI2HeyboxEveryday/agi_news.py` 的每日 AGI 时讯数据（微信合集页→最新一期→原文切分），LLM 按上游 workflow.md 编辑理念改写为视频口播稿（每句 12~32 字、同企业合并、数字不变），产出 `runs/agi-<期号>/edition.json` |
| `topup_daemon.py` | scripts/ | TTS 补齐守护：限流窗口内每 170s 轮询，解除后自动补齐语音并 assemble + stills |
| `z-ai-web-dev-sdk` | package.json | 新增依赖（上游不含） |

## 与时讯产线的关系

```
腾讯研究院AI速递(每日) ──┬─ AI2HeyboxEveryday: 图文帖(小黑盒, 09:30)
                        └─ 本项目: 时讯视频(1080p/60fps, 手动或半自动)
                              edition_maker → tts-zai → assemble
                              → stills → VLM审帧 → review → render → deliver
```

同一数据源双形态分发；图文帖是日常自动档，视频是增强档。

## 一期完整制作命令

```bash
cd /home/z/my-project/news-video-gen
python3 edition_maker.py                    # 时讯 → edition.json(最新期)
node scripts/tts-zai.mjs runs/agi-<期号>/edition.json runs/agi-<期号> --execute
node scripts/assemble.mjs runs/agi-<期号>/edition.json runs/agi-<期号>
npm run stills                              # 出检查帧 → 逐张实际看图(或 VLM)
npm run review -- out/<STILLS时间戳> --approved --notes="实际审核范围"
npm run render                              # 1920x1080 60fps H.264+AAC
npm run deliver -- out/<RENDER时间戳>/render-report.json runs/agi-<期号>/delivery-v1
```

TTS 被限流时：`detached_run.py` 挂 `topup_daemon.py` 后台补齐（见 scripts/topup_daemon.py 头注释）。

## 凭据与环境

- z-ai TTS：环境内置（`ZAI.create()`），无需 API key，**免费但有限流**（429 时退避重试）。
- 换音色：`ZAI_TTS_VOICE` 环境变量（默认 `tongtong`）。
- 渲染：需要 chromium（`REMOTION_BROWSER_EXECUTABLE` 可指已有二进制）+ ffmpeg/ffprobe。
- 上游 `.env`（MiniMax key）在本定制版**不需要**。
