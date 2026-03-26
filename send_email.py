"""
Email dispatch: send the newsletter via SMTP.

Required environment variables (set in .env):
    SMTP_HOST      e.g. smtp.gmail.com
    SMTP_PORT      e.g. 587  (default)
    SMTP_USER      your login address
    SMTP_PASSWORD  app password or SMTP credential
    EMAIL_TO       fallback recipient list (comma-separated); used when no
                   topic-specific list is set

Per-newsletter recipient lists (override EMAIL_TO when set):
    EMAIL_TO_GENERAL     recipients for the general AI newsletter
    EMAIL_TO_HEALTHCARE  recipients for the healthcare AI newsletter

Optional:
    EMAIL_FROM     display/from address; defaults to SMTP_USER
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional


def send_newsletter(
    subject: str,
    html: str,
    text: str,
    recipients: Optional[List[str]] = None,
    unsubscribe_email: str = "",
) -> None:
    """
    Build a multipart/alternative email and send it.

    If *recipients* is provided it is used directly (bypassing EMAIL_TO).
    Otherwise EMAIL_TO is read from the environment.

    Raises an exception (with a descriptive message) on any failure so the
    caller can decide whether to abort or just log the error.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    email_from = os.environ.get("EMAIL_FROM") or smtp_user

    if recipients is None:
        email_to_raw = os.environ.get("EMAIL_TO")
        missing = [k for k, v in {
            "SMTP_HOST": smtp_host,
            "SMTP_USER": smtp_user,
            "SMTP_PASSWORD": smtp_password,
            "EMAIL_TO": email_to_raw,
        }.items() if not v]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in your SMTP credentials."
            )
        recipients = [addr.strip() for addr in email_to_raw.split(",") if addr.strip()]
    else:
        missing = [k for k, v in {
            "SMTP_HOST": smtp_host,
            "SMTP_USER": smtp_user,
            "SMTP_PASSWORD": smtp_password,
        }.items() if not v]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in your SMTP credentials."
            )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)
    if unsubscribe_email:
        mailto = f"mailto:{unsubscribe_email}?subject=Unsubscribe"
        msg["List-Unsubscribe"] = f"<{mailto}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Attach plain text first; email clients prefer the last part (HTML)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(email_from, recipients, msg.as_string())

    print(f"  Email sent to: {', '.join(recipients)}")
