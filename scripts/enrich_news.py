# scripts/enrich_news.py
# Use Trafilatura to extract article content, then DeepSeek API to generate
# Chinese summaries for each article and its HN comments.

import json
import os
import re
import time
from pathlib import Path
from datetime import date

import trafilatura
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")
RAW_FILE = DATA_DIR / "raw_news.json"
ENRICHED_FILE = DATA_DIR / "enriched_news.json"

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

MAX_ARTICLE_CHARS = 4000   # truncate extracted article text for the prompt
MAX_COMMENT_CHARS = 3000   # truncate combined comment text for the prompt

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Remove HTML tags from HN comment text."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"&amp;", "&", clean)
    clean = re.sub(r"&lt;", "<", clean)
    clean = re.sub(r"&gt;", ">", clean)
    clean = re.sub(r"&quot;", '"', clean)
    clean = re.sub(r"&#x27;", "'", clean)
    return clean


def extract_article(url: str) -> str | None:
    """Download and extract main text from a URL using Trafilatura."""
    if not url:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            print(f"    Trafilatura: download returned None")
            return None
        text = trafilatura.extract(downloaded, include_comments=False,
                                   include_tables=False, no_fallback=False)
        if text:
            return text.strip()
        else:
            print(f"    Trafilatura: extraction returned empty")
            return None
    except Exception as e:
        print(f"    Trafilatura error: {e}")
        return None


def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    """Call DeepSeek chat API and return the response text."""
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    DeepSeek API error: {e}")
        return ""


def parse_sections(text: str) -> tuple[str, str]:
    """Parse DeepSeek response into (background, summary) using 【】 markers."""
    bg_match = re.search(r"【背景】\s*(.+?)(?=【摘要】|$)", text, re.DOTALL)
    sm_match = re.search(r"【摘要】\s*(.+)", text, re.DOTALL)
    background = bg_match.group(1).strip() if bg_match else ""
    summary = sm_match.group(1).strip() if sm_match else text.strip()
    return background, summary


def summarize_article(title: str, article_text: str) -> tuple[str, str]:
    """Generate background + summary for an article in one DeepSeek call.
    Returns (background, summary)."""
    if not article_text:
        return "", ""

    system_prompt = (
        "你是一位资深的科技新闻编辑，擅长用简洁自然的中文提炼文章精华。"
        "你的读者是忙碌的开发者，他们希望快速了解行业动态。"
    )
    user_prompt = (
        f"请按以下两步处理这篇文章：\n\n"
        f"第一步【背景】：用2-3句话介绍这篇文章涉及的公司、技术或话题的来龙去脉，"
        f"帮助读者理解为什么这件事值得关注。\n\n"
        f"第二步【摘要】：用3-5句话总结文章的核心内容和关键观点，保留重要数据。\n\n"
        f"风格自然流畅，适合在邮件中阅读。\n\n"
        f"标题：{title}\n\n"
        f"文章内容：\n{article_text[:MAX_ARTICLE_CHARS]}\n\n"
        f"请严格按以下格式输出：\n"
        f"【背景】\n（背景内容）\n\n【摘要】\n（摘要内容）"
    )
    raw = call_deepseek(system_prompt, user_prompt, max_tokens=800)
    return parse_sections(raw)


def summarize_comments(title: str, comments_text: str) -> str:
    """Summarize HN comments in Chinese using DeepSeek."""
    if not comments_text.strip():
        return ""

    system_prompt = (
        "你是一位社区运营，擅长从技术社区的讨论中提炼有价值的观点。"
        "你的总结应该覆盖不同的声音，包括赞同和反对意见。"
    )
    user_prompt = (
        f"以下是 Hacker News 上关于文章《{title}》的用户评论。\n"
        f"请用中文总结评论中的主要观点和讨论焦点，3-5 句话即可。\n\n"
        f"评论内容：\n{comments_text[:MAX_COMMENT_CHARS]}\n"
    )
    return call_deepseek(system_prompt, user_prompt)


def format_comments(comments: list[dict]) -> str:
    """Format comment list into a readable string for the prompt."""
    lines = []
    for i, c in enumerate(comments, 1):
        lines.append(f"[{i}] {c['by']}: {strip_html(c['text'])[:300]}")
        for r in c.get("replies", []):
            lines.append(f"    ↳ {r['by']}: {strip_html(r['text'])[:200]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = date.today().isoformat()

    with open(RAW_FILE, encoding="utf-8") as f:
        stories = json.load(f)

    print(f"Loaded {len(stories)} stories from {RAW_FILE}\n")

    enriched = []
    for idx, story in enumerate(stories, 1):
        title = story["title"]
        url = story["url"]
        print(f"[{idx}/{len(stories)}] {title}")

        # --- Article content extraction ---
        print(f"  Extracting article content...")
        article_text = extract_article(url)
        if article_text:
            print(f"  ✓ Extracted {len(article_text)} chars")
        else:
            print(f"  ✗ No content extracted (will summarize from title only)")
            # Fallback: use title as the only context
            article_text = f"[无法获取文章全文，仅提供标题]{title}"

        # --- Article background + summary ---
        print(f"  Generating background + summary...")
        article_background, article_summary = summarize_article(title, article_text)
        if article_background:
            print(f"  ✓ Background: {len(article_background)} chars")
        if article_summary:
            print(f"  ✓ Summary: {len(article_summary)} chars")

        # --- Comments summary ---
        comments = story.get("comments", [])
        comments_text = format_comments(comments)
        print(f"  Generating comment summary ({len(comments)} comments)...")
        comment_summary = summarize_comments(title, comments_text)
        if comment_summary:
            print(f"  ✓ Comment summary: {len(comment_summary)} chars")
        else:
            print(f"  ✗ No comment summary generated")

        enriched.append({
            "rank": story["rank"],
            "title": title,
            "url": url,
            "score": story["score"],
            "descendants": story.get("descendants", 0),
            "by": story.get("by", ""),
            "source": story["source"],
            "article_background": article_background,
            "article_summary": article_summary,
            "comment_summary": comment_summary,
        })

        # Be gentle to the API
        if idx < len(stories):
            time.sleep(1)

    # Add an overall highlight using DeepSeek
    print(f"\nGenerating overall highlight...")
    overall = generate_overall_highlight(enriched)
    if overall:
        print(f"  ✓ Overall highlight: {len(overall)} chars")

    output = {
        "date": today,
        "overall_highlight": overall,
        "stories": enriched,
    }

    with open(ENRICHED_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nEnriched data saved → {ENRICHED_FILE}")


def generate_overall_highlight(stories: list[dict]) -> str:
    """Generate a one-paragraph overall highlight of today's top stories."""
    titles = "\n".join(
        f"{s['rank']}. {s['title']} (score: {s['score']})" for s in stories
    )
    system_prompt = (
        "你是一位邮件新闻简报的编辑。请用自然的中文写一段简短的开场白（2-3句话），"
        "概括今天的 HN 热点主题，语气亲切自然。"
    )
    user_prompt = (
        f"今天是 {date.today().isoformat()}，以下是 Hacker News 的 Top 10 文章：\n\n"
        f"{titles}\n\n"
        f"请写一段简短的开场白，概括今天的科技热点趋势，"
        f"语气像给朋友写邮件一样自然。"
    )
    return call_deepseek(system_prompt, user_prompt)


if __name__ == "__main__":
    main()
