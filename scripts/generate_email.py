# scripts/generate_email.py
# Optional local-preview utility: read enriched JSON → write HTML + plain text
# to data/ so you can open the HTML in a browser before sending.
# Not used in the GitHub workflow — send_email.py does this in-memory.

import json
from pathlib import Path
from datetime import date

# Reuse the same builders from send_email
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_email import build_html, build_plain

DATA_DIR = Path("data")
ENRICHED_FILE = DATA_DIR / "enriched_news.json"


def main():
    today = date.today().isoformat()

    with open(ENRICHED_FILE, encoding="utf-8") as f:
        data = json.load(f)

    html_content = build_html(data)
    txt_content = build_plain(data)

    html_file = DATA_DIR / f"{today}.html"
    txt_file = DATA_DIR / f"{today}.txt"

    html_file.write_text(html_content, encoding="utf-8")
    txt_file.write_text(txt_content, encoding="utf-8")

    print(f"Preview HTML → {html_file}")
    print(f"Preview text → {txt_file}")


if __name__ == "__main__":
    main()
