"""
Normalization layer: every ingestion path calls normalize() to produce a
consistent dict before inserting into the database.

Common article schema produced by normalize():
    title              str
    url                str
    source             str
    bucket             str
    published_at       str | None   (ISO 8601 UTC)
    summary            str
    fetched_at         str          (ISO 8601 UTC)
    paywalled_flag     int          (1 if domain is in PAYWALLED_DOMAINS)
    category_candidate str          ("People", "Processes", or "Tech")
    accessible         int          (1 if we have a usable summary)
    why_it_matters     str          (heuristic one-sentence impact snippet)
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from config import PAYWALLED_DOMAINS

# ---------------------------------------------------------------------------
# Paywall detection
# ---------------------------------------------------------------------------

def detect_paywall(url: str) -> int:
    """Return 1 if the URL's hostname matches a known paywalled domain."""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
    except Exception:
        return 0
    return 1 if any(host == d or host.endswith("." + d) for d in PAYWALLED_DOMAINS) else 0


# ---------------------------------------------------------------------------
# Category classification
# "People" and "Processes" patterns are checked first; "Tech" is the default.
# ---------------------------------------------------------------------------

_PEOPLE_RE = re.compile(
    r"\b(ceo|cto|ciso|cio|chief|officer|hire[sd]?|fired|resign|appoint|"
    r"leadership|executive|founder|workforce|talent|job[s]?|layoff|team|"
    r"employee[s]?|researcher[s]?|scientist[s]?|reskill|upskill|bias|"
    r"ethics|ethic[s]?|responsib|accountability|diversity|inclusion)\b",
    re.IGNORECASE,
)
_PROCESSES_RE = re.compile(
    r"\b(regulation|policy|compliance|governance|framework|workflow|"
    r"deployment|adoption|integration|audit|fda|cms|legislation|standard|"
    r"procedure|protocol|rollout|procurement|vendor|contract|partner|"
    r"automation|enterprise|operation|implement|process)\b",
    re.IGNORECASE,
)


def classify_category(title: str, summary: str) -> str:
    """
    Assign the article to People, Processes, or Tech.
    Checked in priority order: People → Processes → Tech (default).
    """
    text = f"{title} {summary}"
    # Count matches for each category; highest count wins
    people_hits = len(_PEOPLE_RE.findall(text))
    proc_hits = len(_PROCESSES_RE.findall(text))

    if people_hits > proc_hits and people_hits > 0:
        return "People"
    if proc_hits >= people_hits and proc_hits > 0:
        return "Processes"
    return "Tech"


# ---------------------------------------------------------------------------
# "Why it matters" snippet
# ---------------------------------------------------------------------------

_IMPACT_RE = re.compile(
    r"\b(because|means?|results?|effects?|affects?|impacts?|could|may|will|"
    r"risk|lead[s]?|allows?|enables?|forces?|requires?|first|major|new|"
    r"significant|critical|important|transform|break|shift|change[s]?)\b",
    re.IGNORECASE,
)


def why_it_matters(summary: str) -> str:
    """
    Return a short one-sentence 'why it matters' snippet from the summary.
    Prefers sentences with impact-signal words; falls back to the first sentence.
    """
    if not summary:
        return ""

    # Strip HTML
    clean = re.sub(r"<[^>]+>", " ", summary)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Split on sentence boundaries
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    if not sentences:
        return ""

    # Pick the sentence with the most impact-keyword hits
    best = max(sentences, key=lambda s: len(_IMPACT_RE.findall(s)))
    snippet = best if best else sentences[0]

    # Truncate and ensure ends with punctuation
    snippet = snippet[:250]
    if snippet and snippet[-1] not in ".!?":
        snippet += "."
    return snippet


# ---------------------------------------------------------------------------
# Main normalization entry point
# ---------------------------------------------------------------------------

def normalize(
    title: str,
    url: str,
    source: str,
    summary: str,
    published_at: Optional[str],
    bucket: str,
    fetched_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Produce a consistent article dict ready for DB insertion.
    Call this from every fetcher (RSS, Google News, HN, arXiv, Reddit).
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat()

    title = (title or "").strip()
    url = (url or "").strip()
    # Strip HTML from summary for clean storage
    raw_summary = re.sub(r"<[^>]+>", " ", summary or "")
    raw_summary = re.sub(r"\s+", " ", raw_summary).strip()[:1000]

    return {
        "title": title,
        "url": url,
        "source": source,
        "bucket": bucket,
        "published_at": published_at,
        "summary": raw_summary,
        "fetched_at": fetched_at,
        "paywalled_flag": detect_paywall(url),
        "category_candidate": classify_category(title, raw_summary),
        "accessible": 1 if len(raw_summary) > 20 else 0,
        "why_it_matters": why_it_matters(raw_summary),
    }
