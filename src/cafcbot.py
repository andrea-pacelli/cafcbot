#!/usr/bin/env python3
"""
cafcbot.py

Checks the Federal Circuit opinions page for today's precedential opinions,
summarizes each with Claude, and emails the summaries to you.

Setup (one time):
    pip install requests beautifulsoup4 pypdf anthropic

Required environment variables:
    ANTHROPIC_API_KEY   - your Anthropic API key
    EMAIL_FROM          - sending address (e.g. you@gmail.com)
    EMAIL_TO            - receiving address
    EMAIL_PASSWORD      - app password for the sending account
    SMTP_HOST           - e.g. smtp.gmail.com  (default: smtp.gmail.com)
    SMTP_PORT           - e.g. 587             (default: 587)

"""

import io
import os
import smtplib
import textwrap
import re
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OPINIONS_URL = "https://www.cafc.uscourts.gov/home/case-information/opinions-orders/"
BASE_URL     = "https://www.cafc.uscourts.gov"
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; cafcbot/1.0)"}
TODAY        = date.today().strftime("%m/%d/%Y")    # e.g. "03/06/2026"
#TODAY        = "03/06/2026" # for testing


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
        title = link.get_text(strip=True)
        title = re.sub(r'\s*\[OPINION\]\s*', '', title)
        href = link["href"]
        if not href.startswith("http"):
            href = BASE_URL + href
        opinions.append({"title": title, "url": href})

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
        Summarize the following Federal Circuit precedential opinion
        in no more than 200 words, divided into 3 paragraphs: headline;
        summary of facts and outcome; a key quote from the opinion, in
        full and literally, no paraphrasing. Write in a way that is
        understandable by a layperson, while still conveying useful
        information to patent practitioners.

        Opinion title: {title}

        Opinion text (excerpt):
        {text}
    """).strip()

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
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
    print(f"{TODAY} Fetching today's opinions... ", end='')
    opinions = fetch_todays_precedential_opinions()
    if opinions:
        print(f"{len(opinions)} opinions fetched.")
    else:
        print("No precedential opinions today.")
        return

    print("Creating summaries...")
    summaries = []
    for op in opinions:
        print(f"Processing: {op['title']}")
        try:
            summary = summarise(op["title"], fetch_opinion_text(op["url"]))
            print(summary)
            summaries.append(f"=== {op['title']} ===\n{op['url']}\n\n{summary}\n")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    if summaries:
        subject = f"CAFC precedential opinions – {date.today()}"
        body = "\n\n".join(summaries)
        send_email(subject=subject, body=body)
        print(f"Emailed {len(summaries)} summaries.")


if __name__ == "__main__":
    main()
