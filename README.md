# News Agent

An automated daily newsletter that scans the internet for the most important AI news, writes it up, and emails it to your list every morning at 9am.

## What it does

Every day it:

1. **Pulls in articles** from dozens of sources — news sites, research papers, Reddit, Hacker News, Google News, and RSS feeds
2. **Filters and ranks** them to surface the most relevant and credible stories from the last 24 hours
3. **Writes a summary** of each story using Claude AI, including a "why it matters" blurb
4. **Sends two separate newsletters** — one for general AI news, one specifically for healthcare AI — each to their own mailing list

Stories are grouped into three sections:
- **People** — how AI is affecting jobs, society, and individuals
- **Processes** — policy, regulation, business adoption, and workflows
- **Tech** — model releases, research, and infrastructure

Recipients can unsubscribe by clicking the unsubscribe link in the footer. The system automatically checks for those requests before each send and removes people from the list.

## Setup

1. Clone the repo
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your credentials:
   ```
   cp .env.example .env
   ```
4. Run manually:
   ```
   python main.py
   ```

## Environment variables

| Variable | Description |
|---|---|
| `SMTP_HOST` | Your email provider's SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port, usually `587` |
| `SMTP_USER` | The email address you're sending from |
| `SMTP_PASSWORD` | Your app password (not your regular login password) |
| `EMAIL_FROM` | The display name and address shown in the From field |
| `EMAIL_TO_GENERAL` | Comma-separated list of recipients for the general AI newsletter |
| `EMAIL_TO_HEALTHCARE` | Comma-separated list of recipients for the healthcare AI newsletter |
| `ANTHROPIC_API_KEY` | Your Anthropic API key for AI-generated summaries |

## Scheduling

A cron job runs `main.py` automatically at 9am every day. Logs are saved to `briefing.log`.
