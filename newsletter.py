"""
Newsletter generation: build HTML and plain-text versions, save to disk,
record in the DB, and mark featured articles to prevent repeats.

Output format shows up to 3 stories, each labelled with its category
(People / Processes / Tech) and a "Why it matters" impact snippet.
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from db import get_connection

NEWSLETTER_DIR = "newsletters"


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _clean(text: str, max_chars: int = 0) -> str:
    """Strip HTML tags, collapse whitespace, and optionally truncate."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _category_badge(category: str) -> str:
    """Return a coloured inline badge for People / Processes / Tech."""
    colours = {
        "People":    ("#e8f4e8", "#2d7a2d"),
        "Processes": ("#fff3e0", "#b36000"),
        "Tech":      ("#e8f0fe", "#1a56db"),
    }
    bg, fg = colours.get(category, ("#f0f0f0", "#444"))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'background:{bg};color:{fg};font-size:11px;font-weight:bold;'
        f'font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:.4px;">'
        f'{category}</span>'
    )


def _html_card(article: Dict[str, Any]) -> str:
    title = article["title"]
    url = article["url"]
    source = article.get("source") or ""
    summary = _clean(article.get("summary") or "", 280)
    # Prefer AI-generated why-it-matters; fall back to heuristic stored in DB
    wim = _clean(article.get("_why_it_matters_ai") or article.get("why_it_matters") or "", 300)

    why_html = (
        f'<p style="margin:6px 0 0;font-size:13px;color:#5570a0;font-style:italic;'
        f'font-family:Arial,sans-serif;line-height:1.5;">'
        f'<strong>Why it matters:</strong> {wim}</p>'
        if wim else ""
    )

    return f"""\
    <div style="padding:14px 0;border-bottom:1px solid #eef0f4;">
      <h3 style="margin:0 0 6px;font-size:16px;line-height:1.4;font-family:Georgia,serif;">
        <a href="{url}" style="color:#111;text-decoration:none;">{title}</a>
      </h3>
      <p style="margin:0;font-size:13px;color:#555;line-height:1.5;font-family:Arial,sans-serif;">{summary}</p>
      {why_html}
      <p style="margin:6px 0 0;font-size:12px;color:#aaa;font-family:Arial,sans-serif;">{source}</p>
    </div>"""


def _html_section(category: str, articles: List[Dict[str, Any]]) -> str:
    """Render a labelled section block for one category."""
    section_styles = {
        "People":    ("border-left:4px solid #2d7a2d;", "#2d7a2d"),
        "Processes": ("border-left:4px solid #b36000;", "#b36000"),
        "Tech":      ("border-left:4px solid #1a56db;", "#1a56db"),
    }
    border, colour = section_styles.get(category, ("border-left:4px solid #888;", "#888"))
    cards_html = "\n".join(_html_card(a) for a in articles)
    return f"""\
    <div style="margin-bottom:28px;">
      <div style="{border}padding:4px 12px;margin-bottom:12px;">
        <p style="margin:0;font-size:11px;font-weight:bold;text-transform:uppercase;
                  letter-spacing:.8px;color:{colour};font-family:Arial,sans-serif;">{category}</p>
      </div>
      {cards_html}
    </div>"""


def build_html(stories: List[Dict[str, Any]], date_str: str, key_takeaway: str = "", unsubscribe_email: str = "", newsletter_name: str = "AI News") -> str:
    # Group articles by category, preserving score order within each group
    category_order = ["People", "Processes", "Tech"]
    grouped: Dict[str, List[Dict[str, Any]]] = {c: [] for c in category_order}
    for article in stories:
        cat = article.get("_category") or article.get("category_candidate") or "Tech"
        grouped.setdefault(cat, []).append(article)

    sections_html = "\n".join(
        _html_section(cat, grouped[cat])
        for cat in category_order
        if grouped.get(cat)
    )

    # Key takeaway banner – shown below the header when present
    takeaway_html = (
        f'<tr><td style="padding:18px 32px;background:#f7f9ff;border-bottom:1px solid #dde6ff;">'
        f'<p style="margin:0 0 4px;font-size:11px;color:#5570a0;text-transform:uppercase;'
        f'letter-spacing:.6px;font-family:Arial,sans-serif;">Key Takeaway</p>'
        f'<p style="margin:0;font-size:14px;color:#1a1a2e;line-height:1.6;font-family:Georgia,serif;">'
        f'{key_takeaway}</p>'
        f'</td></tr>'
        if key_takeaway else ""
    )

    body = "Please remove me from this newsletter."
    unsubscribe_html = (
        f'<p style="margin:8px 0 0;font-size:11px;color:#bbb;text-align:center;font-family:Arial,sans-serif;">'
        f'Don\'t want these emails? '
        f'<a href="mailto:{unsubscribe_email}?subject=Unsubscribe&body={body}" style="color:#bbb;">Unsubscribe</a>'
        f'</p>'
    ) if unsubscribe_email else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{newsletter_name} Briefing – {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f2f2f2;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f2f2f2;padding:32px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:6px;border:1px solid #ddd;max-width:620px;">
        <tr>
          <td style="background:#0057FF;padding:22px 32px;">
            <p style="margin:0;color:#cce0ff;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-family:Arial,sans-serif;">Daily Briefing</p>
            <h1 style="margin:4px 0 0;color:#fff;font-size:26px;font-weight:bold;font-family:Georgia,serif;">{newsletter_name}</h1>
            <p style="margin:6px 0 0;color:#a8c8ff;font-size:13px;font-family:Arial,sans-serif;">{date_str}</p>
          </td>
        </tr>
        {takeaway_html}
        <tr>
          <td style="padding:30px 32px 24px;">
            {sections_html}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px;background:#f8f8f8;border-top:1px solid #ececec;">
            <p style="margin:0;font-size:11px;color:#aaa;text-align:center;font-family:Arial,sans-serif;">
              {newsletter_name} Briefing &middot; {date_str}
            </p>
            {unsubscribe_html}
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Plain text rendering
# ---------------------------------------------------------------------------

def build_text(stories: List[Dict[str, Any]], date_str: str, key_takeaway: str = "", unsubscribe_email: str = "", newsletter_name: str = "AI News") -> str:
    lines = [
        f"{newsletter_name.upper()} BRIEFING — {date_str}",
        "=" * 60,
        "",
    ]
    if key_takeaway:
        lines += [
            "KEY TAKEAWAY",
            "-" * 40,
            key_takeaway,
            "",
        ]

    # Group by category in consistent order
    category_order = ["People", "Processes", "Tech"]
    grouped: Dict[str, List[Dict[str, Any]]] = {c: [] for c in category_order}
    for article in stories:
        cat = article.get("_category") or article.get("category_candidate") or "Tech"
        grouped.setdefault(cat, []).append(article)

    for cat in category_order:
        articles = grouped.get(cat, [])
        if not articles:
            continue
        lines += [
            cat.upper(),
            "-" * 40,
        ]
        for article in articles:
            wim = _clean(article.get("_why_it_matters_ai") or article.get("why_it_matters") or "")
            summary = _clean(article.get("summary") or "", 280)
            lines += [
                article["title"],
                article["url"],
                summary,
            ]
            if wim:
                lines.append(f"Why it matters: {wim}")
            lines.append("")

    lines.append("=" * 60)
    if unsubscribe_email:
        lines += [
            "",
            f"To unsubscribe, email {unsubscribe_email} with subject: Unsubscribe",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_newsletter(
    html: str,
    text: str,
    stories: List[Dict[str, Any]],
    subject: str,
    db_path: str = "ai_news.db",
) -> str:
    """Write files, record in DB, and mark articles as featured."""
    os.makedirs(NEWSLETTER_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d")

    html_path = os.path.join(NEWSLETTER_DIR, f"{stamp}.html")
    text_path = os.path.join(NEWSLETTER_DIR, f"{stamp}.txt")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    article_ids = [a["id"] for a in stories]
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO newsletters (generated_at, subject, body_html, body_text, article_ids) "
        "VALUES (?, ?, ?, ?, ?)",
        (now.isoformat(), subject, html, text, json.dumps(article_ids)),
    )
    for aid in article_ids:
        conn.execute(
            "UPDATE articles SET featured_at = ? WHERE id = ?",
            (now.isoformat(), aid),
        )
    conn.commit()
    conn.close()

    print(f"  Saved: {html_path}")
    print(f"  Saved: {text_path}")
    return html_path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_newsletter(
    stories: List[Dict[str, Any]],
    key_takeaway: str = "",
    db_path: str = "ai_news.db",
    unsubscribe_email: str = "",
    newsletter_name: str = "AI News",
) -> Dict[str, str]:
    """Build HTML + plain text, save to disk, and return the content dict."""
    date_str = datetime.now(timezone.utc).strftime("%A, %B %-d, %Y")
    subject = f"{newsletter_name} Briefing – {date_str}"
    html = build_html(stories, date_str, key_takeaway, unsubscribe_email, newsletter_name)
    text = build_text(stories, date_str, key_takeaway, unsubscribe_email, newsletter_name)
    save_newsletter(html, text, stories, subject, db_path)
    return {"subject": subject, "html": html, "text": text}
