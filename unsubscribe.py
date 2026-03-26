"""
Unsubscribe processor: checks the inbox for unsubscribe requests and
removes matching addresses from EMAIL_TO_GENERAL and EMAIL_TO_HEALTHCARE
in .env.

Triggered automatically by main.py before each newsletter send.
Can also be run standalone:  python unsubscribe.py

Required env vars (same credentials as SMTP):
    SMTP_USER      Gmail address to log into via IMAP
    SMTP_PASSWORD  App password

Optional:
    IMAP_HOST      defaults to imap.gmail.com
    IMAP_PORT      defaults to 993
"""
import email
import imaplib
import os
import re
from email.header import decode_header

from dotenv import set_key

ENV_FILE = ".env"
UNSUBSCRIBE_SUBJECT_RE = re.compile(r"unsubscribe", re.IGNORECASE)
LIST_VARS = ["EMAIL_TO_GENERAL", "EMAIL_TO_HEALTHCARE", "EMAIL_TO"]


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)


def _extract_address(from_field: str) -> str:
    """Pull bare email address from a From header like 'Name <addr@example.com>'."""
    match = re.search(r"<([^>]+)>", from_field)
    if match:
        return match.group(1).strip().lower()
    return from_field.strip().lower()


def _remove_address(env_var: str, address: str) -> bool:
    """
    Remove *address* from the comma-separated list in *env_var*.
    Returns True if the value changed.
    """
    raw = os.environ.get(env_var, "")
    addresses = [a.strip() for a in raw.split(",") if a.strip()]
    filtered = [a for a in addresses if a.lower() != address]
    if len(filtered) == len(addresses):
        return False  # address wasn't in this list
    new_value = ", ".join(filtered)
    set_key(ENV_FILE, env_var, new_value)
    os.environ[env_var] = new_value
    return True


def process_unsubscribes() -> list[str]:
    """
    Connect to IMAP, find unsubscribe emails, remove senders from .env.
    Returns list of addresses that were removed.
    """
    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    imap_port = int(os.environ.get("IMAP_PORT", "993"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")

    if not user or not password:
        print("  [unsubscribe] Skipping – SMTP_USER or SMTP_PASSWORD not set.")
        return []

    removed = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(user, password)
        mail.select("INBOX")

        # Search for unread emails with "unsubscribe" in the subject
        _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "unsubscribe")')
        ids = msg_ids[0].split()

        if not ids:
            print("  [unsubscribe] No unsubscribe requests found.")
            mail.logout()
            return []

        print(f"  [unsubscribe] Found {len(ids)} unsubscribe request(s).")

        for msg_id in ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_field = _decode_header_value(msg.get("From", ""))
            address = _extract_address(from_field)

            changed = False
            for var in LIST_VARS:
                if _remove_address(var, address):
                    changed = True

            if changed:
                print(f"  [unsubscribe] Removed: {address}")
                removed.append(address)
            else:
                print(f"  [unsubscribe] Not on any list: {address}")

            # Mark as read so it isn't processed again
            mail.store(msg_id, "+FLAGS", "\\Seen")

        mail.logout()

    except Exception as exc:
        print(f"  [unsubscribe] Error checking inbox: {exc}")

    return removed


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    removed = process_unsubscribes()
    if removed:
        print(f"\nRemoved {len(removed)} address(es): {', '.join(removed)}")
    else:
        print("\nNo changes made.")
