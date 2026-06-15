# scripts/generate_digest.py
# Generate a rich markdown digest from enriched news data.
# This is the canonical artifact — stored in the repo under digests/.

import json
from pathlib import Path
from datetime import date

DATA_DIR = Path("data")
DIGEST_DIR = Path("digests")
ENRICHED_FILE = DATA_DIR / "enriched_news.json"

DIGEST_DIR.mkdir(exist_ok=True)


def build_markdown(data: dict) -> str:
    today = data.get("date", date.today().isoformat())
    overall = data.get("overall_highlight", "")
    stories = data.get("stories", [])

    lines = [
        f"# Daily Digest ({today})",
        "",
    ]

    if overall:
        lines.append(f"> {overall}")
        lines.append("")

    lines.append("---")
    lines.append("")

    for s in stories:
        title = s["title"]
        url = s.get("url", "")
        score = s.get("score", 0)
        descendants = s.get("descendants", 0)
        article_summary = s.get("article_summary", "")
        comment_summary = s.get("comment_summary", "")

        # Title — linked if URL exists
        if url:
            lines.append(f"## {s['rank']}. [{title}]({url})")
        else:
            lines.append(f"## {s['rank']}. {title}")

        lines.append("")
        lines.append(f"⬆ **{score}** points · 💬 **{descendants}** comments")
        lines.append("")

        if article_summary:
            lines.append("### 📝 文章摘要")
            lines.append("")
            lines.append(article_summary)
            lines.append("")

        if comment_summary:
            lines.append("### 💬 HN 社区讨论")
            lines.append("")
            lines.append(comment_summary)
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("*由 DeepSeek 自动生成 · Hacker News Top 10 摘要*")
    lines.append("")

    return "\n".join(lines)


def main():
    with open(ENRICHED_FILE, encoding="utf-8") as f:
        data = json.load(f)

    md_content = build_markdown(data)

    today = data.get("date", date.today().isoformat())
    digest_file = DIGEST_DIR / f"{today}.md"
    digest_file.write_text(md_content, encoding="utf-8")

    print(f"Digest generated → {digest_file}")
    print(f"  Stories: {len(data.get('stories', []))}")
    print(f"  Overall highlight: {bool(data.get('overall_highlight'))}")


if __name__ == "__main__":
    main()
