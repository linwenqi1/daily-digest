# scripts/fetch_news.py
# Fetch a balanced set of technology stories from HN plus editorial RSS feeds.

from __future__ import annotations

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

MAX_COMMENTS = 8
TOTAL_LIMIT = 12
REQUEST_TIMEOUT = 12
HEADERS = {
    "User-Agent": (
        "daily-digest/1.0 "
        "(https://github.com/actions; +https://github.com)"
    )
}

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    limit: int


RSS_SOURCES = [
    FeedSource("Lobsters", "https://lobste.rs/rss", 3),
    FeedSource("The Verge Tech", "https://www.theverge.com/rss/tech/index.xml", 3),
    FeedSource("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab", 2),
    FeedSource("MIT Technology Review", "https://www.technologyreview.com/feed/", 2),
]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    cleaned_query = "&".join(
        part for part in parsed.query.split("&")
        if part and not part.startswith(("utm_", "fbclid=", "gclid="))
    )
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            cleaned_query,
            "",
        )
    )


def story_key(story: dict) -> str:
    url = canonical_url(story.get("url", ""))
    if url:
        return f"url:{url}"
    title = re.sub(r"\W+", "", story.get("title", "").lower())
    return f"title:{title}"


def fetch_json(url: str) -> dict | list | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  [WARN] Failed to fetch JSON {url}: {exc}")
        return None


def fetch_hn_item(item_id: int) -> dict | None:
    item = fetch_json(HN_ITEM_URL.format(item_id))
    return item if isinstance(item, dict) else None


def fetch_hn_comments(kids: list[int], max_count: int = MAX_COMMENTS) -> list[dict]:
    comments = []
    for kid_id in kids[:max_count]:
        comment = fetch_hn_item(kid_id)
        if not comment or comment.get("deleted") or comment.get("dead"):
            continue

        replies = []
        for reply_id in (comment.get("kids") or [])[:1]:
            reply = fetch_hn_item(reply_id)
            if reply and not reply.get("deleted") and not reply.get("dead"):
                replies.append(
                    {
                        "by": reply.get("by", "anonymous"),
                        "text": clean_text(reply.get("text", "")),
                    }
                )
            time.sleep(0.05)

        comments.append(
            {
                "by": comment.get("by", "anonymous"),
                "text": clean_text(comment.get("text", "")),
                "replies": replies,
            }
        )
        time.sleep(0.05)
    return comments


def fetch_hn_stories(limit: int = 4) -> list[dict]:
    print("Fetching Hacker News top stories...")
    top_ids = fetch_json(HN_TOP_STORIES_URL)
    if not isinstance(top_ids, list):
        return []

    stories = []
    for story_id in top_ids[: limit * 3]:
        if len(stories) >= limit:
            break
        item = fetch_hn_item(story_id)
        if not item or item.get("type") != "story" or not item.get("title"):
            continue

        url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        comments = fetch_hn_comments(item.get("kids", []))
        stories.append(
            {
                "title": clean_text(item.get("title")),
                "url": url,
                "score": item.get("score", 0),
                "descendants": item.get("descendants", 0),
                "by": item.get("by", ""),
                "source": "Hacker News",
                "source_type": "community",
                "source_summary": "",
                "comments": comments,
            }
        )
        print(f"  HN: {stories[-1]['title']} ({len(comments)} comments)")
        time.sleep(0.1)
    return stories


def child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        tag = child.tag.split("}", 1)[-1].lower()
        if tag in names and child.text:
            return clean_text(child.text)
    return ""


def child_link(element: ET.Element) -> str:
    for child in element.iter():
        tag = child.tag.split("}", 1)[-1].lower()
        if tag == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def parse_feed_items(xml_text: str) -> list[ET.Element]:
    root = ET.fromstring(xml_text)
    items = [
        element
        for element in root.iter()
        if element.tag.split("}", 1)[-1].lower() in {"item", "entry"}
    ]
    return items


def fetch_rss_source(source: FeedSource) -> list[dict]:
    print(f"Fetching {source.name} feed...")
    try:
        resp = requests.get(source.url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        items = parse_feed_items(resp.text)
    except Exception as exc:
        print(f"  [WARN] Failed to fetch {source.name}: {exc}")
        return []

    stories = []
    for item in items:
        if len(stories) >= source.limit:
            break
        title = child_text(item, ("title",))
        url = child_link(item)
        summary = child_text(item, ("description", "summary", "content", "encoded"))
        if not title or not url:
            continue

        stories.append(
            {
                "title": title,
                "url": url,
                "score": 0,
                "descendants": 0,
                "by": "",
                "source": source.name,
                "source_type": "editorial",
                "source_summary": summary[:1200],
                "comments": [],
            }
        )
        print(f"  {source.name}: {title}")
    return stories


def dedupe_and_rank(stories: list[dict], limit: int = TOTAL_LIMIT) -> list[dict]:
    seen = set()
    unique = []
    for story in stories:
        key = story_key(story)
        if not key or key in seen:
            continue
        seen.add(key)
        story["rank"] = len(unique) + 1
        unique.append(story)
        if len(unique) >= limit:
            break
    return unique


def main() -> None:
    stories = fetch_hn_stories(limit=4)
    for source in RSS_SOURCES:
        stories.extend(fetch_rss_source(source))
        time.sleep(0.2)

    results = dedupe_and_rank(stories)
    output_path = DATA_DIR / "raw_news.json"
    if not results:
        if output_path.exists() and output_path.stat().st_size > 10:
            print(f"\nNo stories fetched; keeping existing {output_path}")
            return
        raise RuntimeError("No stories fetched from any source; aborting without writing raw_news.json.")

    tmp_path = output_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)

    sources = sorted({story["source"] for story in results})
    print(f"\nFetched {len(results)} stories from {', '.join(sources)} -> {output_path}")


if __name__ == "__main__":
    main()
