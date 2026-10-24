# -*- coding: utf-8 -*-
"""edition_maker.py — 把《AGI 日报》时讯素材转成 news-video-generator 的
edition.json(视频口播稿), 是「时讯图文帖」与「时讯视频」两条产线的桥。

数据链路:
  1. 复用 github-hot-heybox/agi_news.py: 微信合集页(实时) → 最新一期
     元数据 + 原文切分 sections(每条新闻: 标题+要点+原文链接)
     —— 数据源本身即全文, 等价于原项目「RSS线索→回原文核验」的完成态
  2. LLM(z-ai CLI) 按 news-video-generator 的编辑理念(workflow.md)改写
     口播稿: 每句12-32字自然短句、开场悬念、同企业合并、数字状态不变
  3. 产出 runs/agi-<issue>/edition.json(通过上游 lib.mjs validate 规则)
  4. 后续: node scripts/tts-zai.mjs ... --execute → assemble → stills
     → VLM 审帧 → review → render → deliver

用法:
    python3 edition_maker.py                      # 最新一期
    python3 edition_maker.py --stories 4          # 指定正文条数
    python3 edition_maker.py --dry-run            # 只打印不落盘
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HEYBOX_DIR = "/home/z/my-project/github-hot-heybox"
sys.path.insert(0, HEYBOX_DIR)

from agi_news import (latest_issue_meta, fetch_issue_content)  # noqa: E402
from summarizer import _call_llm, _extract_json  # noqa: E402

SYSTEM = (
    "你是资讯视频的编导, 把 AI 日报素材改写成 1080p 资讯视频的口播稿。"
    "观众在视频平台刷到这期视频, 前 5 秒决定去留。输出必须是纯 JSON。"
)

PROMPT = """今天是{today}。把下面《AGI 日报》({issue})的素材改写成资讯视频口播稿。

编辑理念(必须遵守):
- 每句 cue 是自然口播短句, 12~32 个汉字, 绝对不超过 60 个字符
- 开场第 1 句用真实的反差或悬念抓住注意力(用素材里的事实, 不许编);
  严禁「大家好/欢迎收看/今天给大家带来」式播音开场
- 开场最多预告 3 个重点
- 最后一条 story 的最后 1~2 句是专门的收尾: 一句话总结今天最值得
  记住的事 + 一个好回答的互动问题(或「明天同一时间」轻预告);
  平实收束不喊口号, 禁金句禁拔高
- 同一家公司/机构的新闻合并进同一条 story
- 数字、价格、状态、适用条件一个都不能变; 不确定的不说
- 禁新闻腔(据悉/引发广泛关注/或将重塑格局), 禁翻译腔(重要一步/标志着)
- 口播像朋友聊天, 句子有长有短, 信息密度高
- ticker 是一句话快讯(≤16字), 每条配来源链接

素材(sections 每条=一条新闻, points 是官方要点, link 是原文):
{sections_json}

输出 JSON(严格此结构):
{{
  "title": "封面标题, 4~10个汉字, 如'AI圈今日大事'",
  "stories": [
    {{
      "id": "s1",
      "company": "公司或机构名, 2~12字, 如'OpenAI'/'谷歌'",
      "title": "这条新闻的短标题, 10~24字",
      "points": ["要点1, ≤38字符", "要点2, ≤38字符"],
      "sources": ["该条新闻的原文链接, 从素材 link 字段原样复制"],
      "cues": [
        {{"text": "口播句, 12~32字", "pauseMs": 350}},
        {{"text": "口播句", "pauseMs": 400}}
      ]
    }}
  ],
  "ticker": [
    {{"text": "快讯短句≤16字", "source": "来源链接(素材link, 没有可用的就复用第1条的link)"}}
  ]
}}

要求: 正文 story 共 {n_stories} 条(从素材里挑最有讨论价值的), 每条 3~5 句 cue;
ticker 共 {n_ticker} 条(独立一句话能讲清的小变化, 或没进正文的有效新闻);
开场不单独立 story, 第 1 条 story 的第 1 句就是开场钩子。"""


def _validate_and_fix(edition: dict, sections: list, n_stories: int) -> dict:
    """Python 侧按上游 lib.mjs validate 规则校验+自动修复"""
    problems = []
    # title
    if not edition.get("title") or not edition["title"].strip():
        edition["title"] = "AI圈今日大事"
    # date = 期号映射(期号 20261023 → 2026-10-23)
    issue = edition.get("_issue") or datetime.date.today().strftime("%Y%m%d")
    edition["date"] = f"{issue[:4]}-{issue[4:6]}-{issue[6:8]}"
    # stories
    stories = edition.get("stories") or []
    if not stories:
        raise RuntimeError("LLM 未产出任何 story")
    valid_links = [s.get("link") for s in sections if s.get("link")]
    for i, s in enumerate(stories):
        s.setdefault("id", f"s{i+1}")
        s["id"] = re.sub(r"[^a-zA-Z0-9_-]", "-", str(s["id"]))[:40] or f"s{i+1}"
        if not s.get("company"):
            s["company"] = "行业动态"
        if not s.get("title"):
            s["title"] = "本期关注"
        pts = [p for p in (s.get("points") or []) if p][:3]
        s["points"] = [str(p)[:38] for p in pts] or ["本期要点"]
        src = [u for u in (s.get("sources") or [])
               if u.startswith("http")]
        if not src:
            src = [valid_links[i % len(valid_links)]] if valid_links else \
                  ["https://github.com/43aquarius/AI2HeyboxEveryday"]
        s["sources"] = src
        cues = []
        for c in (s.get("cues") or []):
            t = (c.get("text") or "").strip()
            if not t:
                continue
            if len(t) > 65:
                t = t[:65]
            p = c.get("pauseMs", 350)
            if not isinstance(p, (int, float)) or p < 150 or p > 1500:
                p = 350
            cues.append({"text": t, "pauseMs": int(p)})
        if not cues:
            cues = [{"text": f"关于{s['company']}的最新动态", "pauseMs": 350}]
        s["cues"] = cues
    edition["stories"] = stories[:n_stories]
    # ticker
    ticker = []
    for t in (edition.get("ticker") or []):
        txt = (t.get("text") or "").strip()
        src = (t.get("source") or "").strip()
        if not txt or not src.startswith("http"):
            continue
        ticker.append({"text": txt, "source": src})
    edition["ticker"] = ticker[:8]
    for p in problems:
        print(f"  [fix] {p}")
    for k in ("_issue",):
        edition.pop(k, None)
    edition["maxSeconds"] = 420
    return edition


def make_edition(n_stories: int = 5, n_ticker: int = 5, dry_run: bool = False,
                 force: bool = False, sections_file: str = ""):
    """sections_file 非空时用外部素材(周末无速递刊/临时热点时),
    格式: [{"title":..., "points":[...], "link":...}]"""
    if sections_file:
        issue = datetime.date.today().strftime("%Y%m%d")
        sections = json.load(open(sections_file, encoding="utf-8"))
        meta = {"date": issue, "title": "网络热点集纳(周末特辑)"}
    else:
        meta = latest_issue_meta()
        issue = meta.get("date") or datetime.date.today().strftime("%Y%m%d")
        sections = fetch_issue_content(meta)
    run_dir = os.path.join(HERE, "runs", f"agi-{issue}")
    out_path = os.path.join(run_dir, "edition.json")
    print(f"[1/3] 期号: {issue} {meta.get('title', '')[:40]} "
          f"({'外部素材' if sections_file else '微信合集页'})")
    if os.path.exists(out_path) and not force:
        print(f"     edition 已存在: {out_path} (--force 重新生成)")
        return out_path
    print(f"[2/3] 素材 {len(sections)} 条新闻, 交给 LLM 编口播稿...")
    slim = [{"title": s["title"], "points": s["points"][:4],
             "link": s.get("link", "")} for s in sections]
    prompt = PROMPT.format(
        today=datetime.date.today().isoformat(), issue=issue,
        sections_json=json.dumps(slim, ensure_ascii=False),
        n_stories=n_stories, n_ticker=n_ticker)
    raw = _call_llm(prompt, SYSTEM, timeout=420)
    data = _extract_json(raw)
    if not data:
        raise RuntimeError(f"LLM 输出无法解析为 JSON: {raw[:300]}")
    data["_issue"] = issue
    edition = _validate_and_fix(data, sections, n_stories)
    n_cues = sum(len(s["cues"]) for s in edition["stories"])
    print(f"[3/3] 产出 {len(edition['stories'])} 条 story / {n_cues} 句口播 / "
          f"{len(edition['ticker'])} 条快讯; 封面题《{edition['title']}》")
    if dry_run:
        print(json.dumps(edition, ensure_ascii=False, indent=2)[:2000])
        return None
    os.makedirs(run_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(edition, f, ensure_ascii=False, indent=2)
    print(f"     已写入 {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories", type=int, default=5)
    ap.add_argument("--ticker", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sections-file", default="",
                    help="外部素材JSON(周末无刊/热点特辑)")
    a = ap.parse_args()
    make_edition(a.stories, a.ticker, a.dry_run, a.force,
                 sections_file=a.sections_file)


if __name__ == "__main__":
    main()
