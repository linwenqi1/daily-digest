# scripts/fetch_news.py
# Fetch HN top 10 stories along with their top comments.

import json
import time
import requests
from pathlib import Path

TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
TOP_N = 10
MAX_COMMENTS = 30  # max top-level comments to fetch per story

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def fetch_item(item_id: int) -> dict | None:
    """Fetch a single HN item by id."""
    try:
        resp = requests.get(ITEM_URL.format(item_id), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [WARN] Failed to fetch item {item_id}: {e}")
        return None


def fetch_comments(kids: list[int], max_count: int = MAX_COMMENTS) -> list[dict]:
    """Fetch top-level comments (and one level of replies) for a story."""
    comments = []
    for kid_id in kids[:max_count]:
        comment = fetch_item(kid_id)
        if comment is None or comment.get("deleted") or comment.get("dead"):
            continue
        # Fetch one level of replies
        replies = []
        for reply_id in (comment.get("kids") or [])[:5]:
            reply = fetch_item(reply_id)
            if reply and not reply.get("deleted") and not reply.get("dead"):
                replies.append({
                    "by": reply.get("by", "anonymous"),
                    "text": reply.get("text", ""),
                })
            time.sleep(0.05)  # be gentle to the API
        comments.append({
            "by": comment.get("by", "anonymous"),
            "text": comment.get("text", ""),
            "replies": replies,
        })
        time.sleep(0.05)
    return comments


def main():
    print("Fetching HN top stories...")
    resp = requests.get(TOP_STORIES_URL, timeout=60)
    resp.raise_for_status()
    top_ids = resp.json()

    results = []
    for rank, story_id in enumerate(top_ids[:TOP_N], start=1):
        print(f"  [{rank}/{TOP_N}] Fetching story {story_id}...")
        item = fetch_item(story_id)
        if not item:
            continue

        story = {
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "score": item.get("score", 0),
            "descendants": item.get("descendants", 0),
            "by": item.get("by", ""),
            "source": "Hacker News",
        }

        # Fetch comments
        kids = item.get("kids", [])
        print(f"    Fetching comments ({len(kids)} available)...")
        story["comments"] = fetch_comments(kids)
        print(f"    Got {len(story['comments'])} comments.")

        results.append(story)
        time.sleep(0.1)

    output_path = DATA_DIR / "raw_news.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nFetched {len(results)} stories → {output_path}")


if __name__ == "__main__":
    main()
