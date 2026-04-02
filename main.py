"""
Daily AI News Briefing – main entry point.

Usage:
    python main.py              # fetch, rank, generate, send
    SKIP_EMAIL=1 python main.py # generate but skip sending (useful for testing)

All configuration lives in .env (copy from .env.example).
All source/query configuration lives in config.py.
"""
import os
import sys

from dotenv import load_dotenv

# Load .env before anything reads os.environ
load_dotenv()

from fetch_sources import fetch_and_store
from newsletter import generate_newsletter
from rank import select_stories, select_icymi
from send_email import send_newsletter
from summarize import enrich_stories
from unsubscribe import process_unsubscribes


def _parse_recipients(env_var: str, fallback_var: str = "EMAIL_TO") -> list[str]:
    """Return a parsed list of email addresses from an env var, with fallback."""
    raw = os.environ.get(env_var) or os.environ.get(fallback_var, "")
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _run_newsletter(
    topic: str,
    label: str,
    newsletter_name: str,
    recipients: list[str],
    db_path: str,
    days_back: int,
    max_stories: int,
    skip_email: bool,
    unsubscribe_email: str = "",
) -> bool:
    """Run one newsletter pipeline (fetch already done). Returns False on fatal error."""
    print(f"\n{'=' * 60}")
    print(f"  [{label}] Ranking and selecting stories")
    print("=" * 60)
    stories = select_stories(db_path, days_back=days_back, max_stories=max_stories, topic=topic)

    if not stories:
        print(f"\n  [{label}] No articles found. Skipping.")
        return True

    icymi = select_icymi(db_path, exclude_ids={a["id"] for a in stories}, topic=topic)
    if icymi:
        print(f"  ICYMI: {icymi['title'][:70]}")

    print(f"\n{'=' * 60}")
    print(f"  [{label}] Generating newsletter")
    print("=" * 60)
    print("  Generating AI summaries and key takeaway...")
    result = enrich_stories(stories)
    key_takeaway = result["takeaway"]
    stories = result["stories"]
    print(f"  Takeaway: {key_takeaway[:80]}...")
    content = generate_newsletter(stories, key_takeaway=key_takeaway, db_path=db_path, unsubscribe_email=unsubscribe_email, newsletter_name=newsletter_name, icymi=icymi)
    print(f"  Subject: {content['subject']}")

    print(f"\n{'=' * 60}")
    if skip_email:
        print(f"  [{label}] Skipping email (SKIP_EMAIL=1)")
    elif not recipients:
        print(f"  [{label}] No recipients configured – skipping send.")
    else:
        print(f"  [{label}] Sending to: {', '.join(recipients)}")
        print("=" * 60)
        try:
            send_newsletter(content["subject"], content["html"], content["text"], recipients, unsubscribe_email)
        except Exception as exc:
            print(f"  [ERROR] Failed to send {label} newsletter: {exc}")
            return False
    print("=" * 60)
    return True


def main() -> None:
    db_path = os.environ.get("DB_PATH", "ai_news.db")
    days_back = int(os.environ.get("NEWSLETTER_DAYS_BACK", "2"))
    max_stories = int(os.environ.get("NEWSLETTER_MAX_STORIES", "5"))
    skip_email = os.environ.get("SKIP_EMAIL", "").strip().lower() in ("1", "true", "yes")

    general_recipients = _parse_recipients("EMAIL_TO_GENERAL")
    healthcare_recipients = _parse_recipients("EMAIL_TO_HEALTHCARE")
    unsubscribe_email = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", "")

    # ------------------------------------------------------------------
    # Step 1: Process unsubscribe requests + ingest all sources
    # ------------------------------------------------------------------
    print("=" * 60)
    print("Step 1/3  Processing unsubscribes & fetching sources")
    print("=" * 60)
    process_unsubscribes()
    fetch_and_store(db_path)

    # ------------------------------------------------------------------
    # Step 2 & 3: Generate and send each newsletter
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Step 2/3  General AI Newsletter")
    ok = _run_newsletter(
        topic="general",
        label="General AI",
        newsletter_name="AI News",
        recipients=general_recipients,
        db_path=db_path,
        days_back=days_back,
        max_stories=max_stories,
        skip_email=skip_email,
        unsubscribe_email=unsubscribe_email,
    )
    if not ok:
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Step 3/3  Healthcare AI Newsletter")
    ok = _run_newsletter(
        topic="healthcare",
        label="Healthcare AI",
        newsletter_name="Healthcare AI News",
        recipients=healthcare_recipients,
        db_path=db_path,
        days_back=days_back,
        max_stories=max_stories,
        skip_email=skip_email,
        unsubscribe_email=unsubscribe_email,
    )
    if not ok:
        sys.exit(1)

    print("\nAll done.")


if __name__ == "__main__":
    main()
