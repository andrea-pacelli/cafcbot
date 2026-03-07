# cafcbot

A lightweight Python script that monitors the Court of Appeals for the
Federal Circuit (CAFC) for new precedential opinions, summarizes each
using Claude. You can put it in your crontab to get a daily summary
(around noon-ish to make sure all opinions for the day have been
posted).

## What It Does

The script:

1. Scrapes the [CAFC opinions page]
   (https://www.cafc.uscourts.gov/home/case-information/opinions-orders/)
   for new precedential opinions

2. Downloads and extracts the text of each new opinion

3. Calls the Anthropic API (Claude) to generate a summary for each
   opinion

4. Emails the summaries to you

## Requirements

- Python 3.9+

- An Anthropic API key (https://console.anthropic.com/)

- A Gmail account (or other SMTP server) for sending email

## Installation

```bash
# Clone the repo
git clone https://github.com/yourname/cafcbot.git
cd cafcbot

# Create and activate a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install requests beautifulsoup4 pypdf anthropic
```

## Configuration

The script expects the following environment variables to be set (they
can be in your .profile or, better, in a dedicated .secrets file):

```
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
EMAIL_PASSWORD=your-app-password
SMTP_HOST=smtp.gmail.com # default
SMTP_PORT=587 # default
```

**Note:** If using Gmail, `EMAIL_PASSWORD` should be an [App
Password](https://support.google.com/accounts/answer/185833), not your
regular Gmail password. It's a good idea to create a dedicated email
account for this, just in case.

## Running Manually

```bash
/path/to/python3 cafcbot.py
```

## License

MIT