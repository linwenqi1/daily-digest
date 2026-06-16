# scripts/enrich_news.py
# Extract article content and use DeepSeek to produce structured Chinese notes.

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import requests
import trafilatura
from openai import OpenAI

DATA_DIR = Path("data")
RAW_FILE = DATA_DIR / "raw_news.json"
ENRICHED_FILE = DATA_DIR / "enriched_news.json"

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

MAX_ARTICLE_CHARS = 6500
MAX_COMMENT_CHARS = 2500
REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; daily-digest/1.0; "
        "+https://github.com/actions)"
    )
}

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_article(url: str) -> str:
    """Download and extract main article text with RSS/title fallback upstream."""
    if not url:
        return ""

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    Article download failed: {exc}")
        return ""

    try:
        text = trafilatura.extract(
            resp.text,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )
        return clean_text(text)
    except Exception as exc:
        print(f"    Trafilatura extraction failed: {exc}")
        return ""


def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 1100) -> str:
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"    DeepSeek API error: {exc}")
        return ""


def section(text: str, name: str) -> str:
    pattern = rf"【{re.escape(name)}】\s*(.+?)(?=【[^】]+】|$)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_story_sections(text: str) -> dict:
    concepts = section(text, "关键概念")
    summary = section(text, "摘要")
    community = section(text, "社区讨论")

    if not concepts and not summary and not community:
        summary = text.strip()

    return {
        "article_concepts": concepts,
        "article_summary": summary,
        "comment_summary": community,
    }


def format_comments(comments: list[dict]) -> str:
    lines = []
    for i, comment in enumerate(comments, 1):
        text = clean_text(comment.get("text", ""))
        if not text:
            continue
        lines.append(f"[{i}] {comment.get('by', 'anonymous')}: {text[:320]}")
        for reply in comment.get("replies", []):
            reply_text = clean_text(reply.get("text", ""))
            if reply_text:
                lines.append(f"    -> {reply.get('by', 'anonymous')}: {reply_text[:220]}")
    return "\n".join(lines)


def build_story_prompt(story: dict, article_text: str, comments_text: str) -> str:
    source_summary = clean_text(story.get("source_summary", ""))
    source_context = (
        f"来源摘要：\n{source_summary[:1600]}\n\n" if source_summary else ""
    )
    article_context = article_text[:MAX_ARTICLE_CHARS] or "未能提取到正文，请仅基于来源摘要和标题谨慎概括。"
    community_context = (
        f"社区评论：\n{comments_text[:MAX_COMMENT_CHARS]}\n\n"
        if comments_text.strip()
        else "社区评论：无可用评论。\n\n"
    )

    return (
        "请处理下面这条科技新闻，输出必须是中文，并严格使用三个小节。\n\n"
        "【关键概念】要求：列出 3-5 个理解这条新闻所需的关键概念。"
        "每个概念用一行，格式为「- 概念：解释」，解释要具体，不要写空泛背景。\n\n"
        "【摘要】要求：用 3-5 句话说明发生了什么、为什么重要、有哪些关键数据或影响。"
        "如果正文不足，请明确保持谨慎，不要编造未出现的信息。\n\n"
        "【社区讨论】要求：只有存在社区评论时总结主要分歧和有价值观点；"
        "如果没有评论，写「暂无社区评论」。\n\n"
        f"标题：{story.get('title', '')}\n"
        f"来源：{story.get('source', '')}\n"
        f"链接：{story.get('url', '')}\n\n"
        f"{source_context}"
        f"正文：\n{article_context}\n\n"
        f"{community_context}"
        "请严格按以下格式输出：\n"
        "【关键概念】\n- 概念：解释\n\n"
        "【摘要】\n摘要内容\n\n"
        "【社区讨论】\n社区讨论内容"
    )


def summarize_story(story: dict, article_text: str, comments_text: str) -> dict:
    system_prompt = (
        "你是一位严谨的科技新闻编辑。你会优先依据原文和来源摘要，"
        "把复杂概念解释清楚，避免空泛评价和无依据扩写。"
    )
    raw = call_deepseek(system_prompt, build_story_prompt(story, article_text, comments_text))
    return parse_story_sections(raw)


def generate_overall_highlight(stories: list[dict]) -> str:
    lines = "\n".join(
        f"{s['rank']}. {s['title']} - {s['source']}" for s in stories
    )
    system_prompt = (
        "你是科技新闻简报编辑。请用自然中文写一段 2-3 句话的开场，"
        "概括今天这些新闻共同呈现出的趋势。"
    )
    user_prompt = (
        f"今天是 {date.today().isoformat()}，这些是今日入选新闻：\n\n"
        f"{lines}\n\n"
        "请不要逐条复述标题，而是概括主题分布和值得关注的变化。"
    )
    return call_deepseek(system_prompt, user_prompt, max_tokens=400)


def main() -> None:
    today = date.today().isoformat()
    stories = json.loads(RAW_FILE.read_text(encoding="utf-8"))

    print(f"Loaded {len(stories)} stories from {RAW_FILE}")
    print(f"Using DeepSeek model: {DEEPSEEK_MODEL}\n")

    enriched = []
    for idx, story in enumerate(stories, 1):
        title = story.get("title", "")
        print(f"[{idx}/{len(stories)}] {title}")

        article_text = extract_article(story.get("url", ""))
        source_summary = clean_text(story.get("source_summary", ""))
        if len(article_text) < 400 and source_summary:
            article_text = f"{article_text}\n\n{source_summary}".strip()

        if article_text:
            print(f"  Extracted context: {len(article_text)} chars")
        else:
            print("  No article text extracted; summarizing from title only")

        comments_text = format_comments(story.get("comments", []))
        print(f"  Summarizing with comments: {bool(comments_text.strip())}")
        sections = summarize_story(story, article_text, comments_text)

        enriched.append(
            {
                "rank": story["rank"],
                "title": title,
                "url": story.get("url", ""),
                "score": story.get("score", 0),
                "descendants": story.get("descendants", 0),
                "by": story.get("by", ""),
                "source": story.get("source", ""),
                "source_type": story.get("source_type", ""),
                "article_concepts": sections["article_concepts"],
                "article_summary": sections["article_summary"],
                "comment_summary": sections["comment_summary"],
            }
        )

        if idx < len(stories):
            time.sleep(0.8)

    print("\nGenerating overall highlight...")
    output = {
        "date": today,
        "model": DEEPSEEK_MODEL,
        "overall_highlight": generate_overall_highlight(enriched),
        "stories": enriched,
    }
    ENRICHED_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Enriched data saved -> {ENRICHED_FILE}")


if __name__ == "__main__":
    main()
