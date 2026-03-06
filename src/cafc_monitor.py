#!/usr/bin/env python3
"""
cafc_monitor.py

Checks the Federal Circuit opinions page for today's precedential opinions,
summarizes each with Claude, and emails the summaries to you.

Setup (one time):
    pip install --user requests beautifulsoup4 pypdf anthropic

Required environment variables:
    ANTHROPIC_API_KEY   - your Anthropic API key
    EMAIL_FROM          - sending address (e.g. you@gmail.com)
    EMAIL_TO            - receiving address
    EMAIL_PASSWORD      - app password for the sending account
    SMTP_HOST           - e.g. smtp.gmail.com  (default: smtp.gmail.com)
    SMTP_PORT           - e.g. 587             (default: 587)

Cron (runs at 11am daily):
    0 11 * * * /usr/bin/python3 /path/to/cafc_monitor.py >> /path/to/cafc.log 2>&1
"""

import io
import os
import smtplib
import textwrap
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OPINIONS_URL = "https://www.cafc.uscourts.gov/home/case-information/opinions-orders/"
BASE_URL     = "https://www.cafc.uscourts.gov"
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; cafc-monitor/1.0)"}
TODAY        = date.today().strftime("%m/%d/%Y")    # e.g. "03/06/2026"


def fetch_todays_precedential_opinions() -> list[dict]:
    resp = requests.get(OPINIONS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    opinions = []
    for row in soup.select("tr, .views-row, .opinion-item"):
        text = row.get_text(" ", strip=True)
        if "Precedential" not in text or TODAY not in text:
            continue
        link = row.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        if not href.startswith("http"):
            href = BASE_URL + href
        opinions.append({"title": link.get_text(strip=True), "url": href})

    return opinions


def fetch_opinion_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if url.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(resp.content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            if sum(len(p) for p in pages) > 15_000:
                break
        return "\n".join(pages)[:15_000]
    return BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)[:15_000]


def summarise(title: str, text: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = textwrap.dedent(f"""
        You are a patent and appellate litigation attorney writing for LinkedIn.
        Summarise the following Federal Circuit precedential opinion in EXACTLY
        100 words. Lead with the key legal holding. Write for IP lawyers and
        in-house counsel. Use plain, confident prose — no bullet points, no hashtags.

        Opinion title: {title}

        Opinion text (excerpt):
        {text}
    """).strip()

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def send_email(subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = os.environ["EMAIL_FROM"]
    msg["To"]      = os.environ["EMAIL_TO"]
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                      int(os.environ.get("SMTP_PORT", 587))) as server:
        server.starttls()
        server.login(os.environ["EMAIL_FROM"], os.environ["EMAIL_PASSWORD"])
        server.sendmail(os.environ["EMAIL_FROM"], os.environ["EMAIL_TO"], msg.as_string())


def main():
    opinions = fetch_todays_precedential_opinions()
    if not opinions:
        print(f"{date.today()} – No precedential opinions today.")
        return

    summaries = []
    for op in opinions:
        print(f"Processing: {op['title']}")
        try:
            summary = summarise(op["title"], fetch_opinion_text(op["url"]))
            summaries.append(f"=== {op['title']} ===\n{op['url']}\n\n{summary}\n")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    if summaries:
        body = f"CAFC precedential opinions – {date.today()}\n\n" + "\n\n".join(summaries)
        send_email(subject=f"CAFC Opinions – {date.today()}", body=body)
        print(f"Emailed {len(summaries)} summaries.")


if __name__ == "__main__":
    main()
