# scripts/send_email.py
# Send the daily digest as an HTML email via SMTP (Gmail).

import os
import smtplib
from pathlib import Path
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DIGEST_DIR = Path("digests")

today = date.today().isoformat()

# ---------------------------------------------------------------------------
# Load HTML and plain-text versions
# ---------------------------------------------------------------------------
html_path = DIGEST_DIR / f"{today}.html"
txt_path = DIGEST_DIR / f"{today}.txt"

html_content = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
txt_content = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""

if not html_content and not txt_content:
    raise FileNotFoundError(f"No digest file found for {today}")

# ---------------------------------------------------------------------------
# Build multipart message (plain text + HTML)
# ---------------------------------------------------------------------------
msg = MIMEMultipart("alternative")
msg["Subject"] = f"Daily Digest — {today}"
msg["From"] = os.environ["EMAIL_USER"]
msg["To"] = os.environ["EMAIL_TO"]

if txt_content:
    msg.attach(MIMEText(txt_content, "plain", "utf-8"))
if html_content:
    msg.attach(MIMEText(html_content, "html", "utf-8"))

# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------
with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(
        os.environ["EMAIL_USER"],
        os.environ["EMAIL_PASSWORD"],
    )
    server.send_message(msg)

print(f"Email sent to {os.environ['EMAIL_TO']}")
