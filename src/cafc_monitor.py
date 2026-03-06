#!/usr/bin/env python3
"""
cafc_monitor.py

Checks the Federal Circuit's opinions page for new precedential opinions,
summarizes each with Claude, and emails the summaries to you.

Setup (one time):
    pip install requests beautifulsoup4 pypdf anthropic

Required environment variables (set in your shell or a .env file):
    ANTHROPIC_API_KEY   - your Anthropic API key
    EMAIL_FROM          - sending address  (e.g. you@gmail.com)
    EMAIL_TO            - receiving address
    EMAIL_PASSWORD      - app password for the sending account
    SMTP_HOST           - e.g. smtp.gmail.com
    SMTP_PORT           - e.g. 587

Scheduling (cron, runs at 11am daily):
    0 11 * * * /usr/bin/python3 /path/to/cafc_monitor.py >> /path/to/cafc.log 2>&1
"""

import os
import json
import smtplib
import textwrap
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_TO          = os.environ["EMAIL_TO"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
SMTP_HOST         = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.environ.get("SMTP_PORT", 587))

# Local file that tracks which opinion URLs we have already processed.
SEEN_FILE = Path(__file__).parent / "cafc_seen.json"

OPINIONS_URL = "https://www.cafc.uscourts.gov/home/case-information/opinions-orders/"
BASE_URL     = "https://www.cafc.uscourts.gov"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cafc-monitor/1.0)"}

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_precedential_opinions() -> list[dict]:
    """
    Returns a list of dicts with keys: title, url, date_str.
    Only includes opinions labeled as Precedential.
    """
    resp = requests.get(OPINIONS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    opinions = []

    # The CAFC page lists opinions in a table or repeated div blocks.
    # We look for any <a> tag whose surrounding context mentions "Precedential".
    # Adjust the selector below if the site's HTML changes.
    for row in soup.select("tr, .views-row, .opinion-item"):
        text = row.get_text(" ", strip=True)
        if "Precedential" not in text:
            continue
        link = row.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        if not href.startswith("http"):
            href = BASE_URL + href
        opinions.append({
            "title": link.get_text(strip=True),
            "url":   href,
            "raw":   text,
        })

    return opinions

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf_url(url: str) -> str:
    """Downloads a PDF and extracts its text (first ~15,000 chars is plenty)."""
    from pypdf import PdfReader
    import io

    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    reader = PdfReader(io.BytesIO(resp.content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
        if sum(len(p) for p in pages) > 15_000:
            break
    return "\n".join(pages)[:15_000]

# ---------------------------------------------------------------------------
# Summarisation
# ---------------------------------------------------------------------------

def summarise(title: str, text: str) -> str:
    """Calls Claude to produce a ~100-word LinkedIn-ready summary."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = textwrap.dedent(f"""
        You are a patent and appellate litigation attorney writing for LinkedIn.
        Summarise the following Federal Circuit precedential opinion in EXACTLY
        100 words. Write for a professional audience of IP lawyers and in-house
        counsel. Lead with the key legal holding. Use plain, confident prose,
        no bullet points, no hashtags.

        Opinion title: {title}

        Opinion text (excerpt):
        {text}
    """).strip()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    seen = load_seen()
    opinions = fetch_precedential_opinions()

    new_opinions = [op for op in opinions if op["url"] not in seen]
    if not new_opinions:
        print(f"{date.today()} – No new precedential opinions found.")
        return

    summaries = []
    for op in new_opinions:
        print(f"Processing: {op['title']}")
        try:
            # Try to fetch the full PDF; fall back to the scraped page text.
            if op["url"].lower().endswith(".pdf"):
                text = extract_text_from_pdf_url(op["url"])
            else:
                r = requests.get(op["url"], headers=HEADERS, timeout=30)
                page_soup = BeautifulSoup(r.text, "html.parser")
                text = page_soup.get_text(" ", strip=True)[:15_000]

            summary = summarise(op["title"], text)
            summaries.append(
                f"=== {op['title']} ===\n{op['url']}\n\n{summary}\n"
            )
            seen.add(op["url"])
        except Exception as exc:
            print(f"  ERROR processing {op['url']}: {exc}")

    if summaries:
        body = (
            f"New Federal Circuit precedential opinions – {date.today()}\n\n"
            + "\n\n".join(summaries)
        )
        send_email(
            subject=f"CAFC Precedential Opinions – {date.today()}",
            body=body,
        )
        print(f"Emailed {len(summaries)} summaries.")

    save_seen(seen)

if __name__ == "__main__":
    main()
