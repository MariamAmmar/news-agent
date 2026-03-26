"""
Article ranking: score for impact, detect cross-source pickup,
deduplicate similar headlines, and force one story per category.

Pipeline (called by select_stories):
  1. Score every article (keywords + credibility + recency + paywall penalty)
  2. Add cross-source pickup bonus (same story covered by multiple outlets)
  3. Sort by score descending
  4. Deduplicate near-duplicate headlines
  5. Pick one story per category: People / Processes / Tech
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import HEALTHCARE_BUCKETS, SOURCE_CREDIBILITY
from db import get_connection
from normalize import classify_category

# ---------------------------------------------------------------------------
# Keyword impact scoring
# (pattern, score) – matched case-insensitively against title + summary
# ---------------------------------------------------------------------------
KEYWORD_SCORES: List[Tuple[str, int]] = [
    # High-impact: model releases, AGI, major regulation
    (r"\b(gpt-?\s*\d|claude\s+\d|gemini\s+\d|llama\s+\d|mistral|phi-?\d|model release|new model)\b", 4),
    (r"\b(agi|superintelligence|artificial general intelligence)\b", 4),
    (r"\b(regulation|legislation|executive order|ban|law|fda approval|fda cleared)\b", 4),
    # High-signal events
    (r"\b(breakthrough|landmark|announces?|launch(es|ed)?|release[sd]?|debut[s]?)\b", 3),
    # Business / workflow impact
    (r"\b(enterprise|adoption|deployment|production|workflow|automation|replac(e|es|ing))\b", 2),
    # Risk, safety, governance
    (r"\b(risk|failure|outage|hallucination|bias|safety|alignment|audit|accountability|transparency|governance)\b", 2),
    # Healthcare
    (r"\b(healthcare|clinical|medical|patient|hospital|ehr|health system)\b", 2),
    # Infrastructure / compute
    (r"\b(gpu|chip|compute|data.?center|cloud|infrastructure|semiconductor)\b", 2),
    # General AI (low weight – very common)
    (r"\b(ai|artificial intelligence|machine learning|deep learning|llm|large language model)\b", 1),
    # Major players (low weight)
    (r"\b(openai|anthropic|google|microsoft|meta|amazon|nvidia|apple|deepmind)\b", 1),
]

_HEALTHCARE_RE = re.compile(
    r"\b(health(care)?|clinical|medical|patient|hospital|physician|nurse|nursing|"
    r"ehr|fda|cms|medicare|medicaid|drug|pharma(ceutical)?|genomic|radiology|"
    r"pathology|diagnosis|diagnostic|treatment|therapy|therapist|mental health|"
    r"psychiatr|biomedical|clinical trial|telehealth|telemedicine|health system|"
    r"health it|health data|care delivery|care provider|clinician)\b",
    re.IGNORECASE,
)

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "this", "that", "it", "its", "as", "how", "why",
    "what", "when", "who", "will", "can", "not", "new", "more", "says",
    "said", "about", "after", "before", "into", "over", "than", "then",
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_article(article: Dict[str, Any], now: datetime) -> float:
    """
    Return a composite impact score. Higher = more likely to be selected.

    Factors (roughly in descending weight):
      + keyword matches in title + summary
      + source credibility (from config.SOURCE_CREDIBILITY)
      + cross-source pickup bonus (set externally in _add_cross_source_scores)
      + recency bonus (last 24h or 48h)
      - paywall penalty
      - repeat-featured penalty (already in a recent newsletter)
    """
    text = f"{article.get('title', '')} {article.get('summary') or ''}".lower()
    score = 0.0

    # Keyword impact
    for pattern, weight in KEYWORD_SCORES:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight

    # Source credibility bonus
    source = (article.get("source") or "").lower()
    for key, cred in SOURCE_CREDIBILITY.items():
        if key in source:
            score += cred
            break  # only the best match counts

    # Cross-source pickup bonus (populated by _add_cross_source_scores)
    score += article.get("_cross_source_bonus", 0) * 2

    # Recency bonus
    published_at = article.get("published_at")
    if published_at:
        try:
            pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            age_h = (now - pub.astimezone(timezone.utc)).total_seconds() / 3600
            if age_h <= 24:
                score += 3
            elif age_h <= 48:
                score += 1
        except Exception:
            pass

    # Paywall penalty – deprioritise but don't exclude
    if article.get("paywalled_flag"):
        score -= 3

    # Repeat-featured penalty: already in a newsletter within the last 7 days
    featured_at = article.get("featured_at")
    if featured_at:
        try:
            ft = datetime.fromisoformat(featured_at.replace("Z", "+00:00"))
            if (now - ft.astimezone(timezone.utc)).days < 7:
                score -= 5
        except Exception:
            pass

    return score


# ---------------------------------------------------------------------------
# Cross-source pickup detection
# ---------------------------------------------------------------------------

def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-z]+", title.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def _add_cross_source_scores(
    articles: List[Dict[str, Any]], threshold: float = 0.45
) -> None:
    """
    Mutate articles in-place, adding a '_cross_source_bonus' key.

    Clusters articles that cover the same story (Jaccard similarity >= threshold)
    and counts unique sources per cluster. The bonus is:
        min(unique_sources_in_cluster - 1, 3)
    so a story picked up by 3+ outlets gets a +3 bonus, capped there.
    """
    # Build token sets once
    tokens = [_title_tokens(a["title"]) for a in articles]

    # Find clusters using a greedy union approach
    cluster_id = list(range(len(articles)))  # each article starts in its own cluster

    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            union = tokens[i] | tokens[j]
            if not union:
                continue
            if len(tokens[i] & tokens[j]) / len(union) >= threshold:
                # Merge j's cluster into i's cluster
                old_id = cluster_id[j]
                new_id = cluster_id[i]
                for k in range(len(articles)):
                    if cluster_id[k] == old_id:
                        cluster_id[k] = new_id

    # Count unique sources per cluster
    from collections import defaultdict
    cluster_sources: Dict[int, set] = defaultdict(set)
    for idx, cid in enumerate(cluster_id):
        cluster_sources[cid].add(articles[idx].get("source") or "")

    # Assign bonus
    for idx, article in enumerate(articles):
        unique = len(cluster_sources[cluster_id[idx]])
        article["_cross_source_bonus"] = min(unique - 1, 3)


# ---------------------------------------------------------------------------
# Headline deduplication
# ---------------------------------------------------------------------------

def deduplicate_by_headline(
    articles: List[Dict[str, Any]], threshold: float = 0.55
) -> List[Dict[str, Any]]:
    """
    Remove articles whose titles are too similar to a higher-scoring entry.
    List must be sorted by score descending so the best version always wins.
    """
    kept: List[Dict[str, Any]] = []
    for candidate in articles:
        tc = _title_tokens(candidate["title"])
        if not any(
            (tc | _title_tokens(e["title"])) and
            len(tc & _title_tokens(e["title"])) / len(tc | _title_tokens(e["title"])) >= threshold
            for e in kept
        ):
            kept.append(candidate)
    return kept


# ---------------------------------------------------------------------------
# Category-diverse selection
# ---------------------------------------------------------------------------

def _select_by_category(
    articles: List[Dict[str, Any]],
    categories: List[str],
    max_stories: int,
) -> List[Dict[str, Any]]:
    """
    Pick up to one story per category, then fill remaining slots from the
    leftover pool (still respecting the 2-per-source cap from before).

    Returns a list of length <= max_stories, ordered by score descending.
    """
    # First pass: one best article per category
    picked: Dict[str, Dict[str, Any]] = {}
    remainder: List[Dict[str, Any]] = []

    for article in articles:
        # Re-classify live from text in case the DB value is a migration default
        cat = classify_category(
            article.get("title", ""), article.get("summary") or ""
        )
        article["_category"] = cat  # store resolved category for newsletter

        if cat not in picked:
            picked[cat] = article
        else:
            remainder.append(article)

    selected = sorted(picked.values(), key=lambda a: a["_score"], reverse=True)

    # Fill remaining slots from leftover pool, capping 2 per source
    source_counts: Dict[str, int] = {a.get("source", ""): 1 for a in selected}
    picked_ids = {a["id"] for a in selected}

    for article in remainder:
        if len(selected) >= max_stories:
            break
        if article["id"] in picked_ids:
            continue
        src = article.get("source") or ""
        if source_counts.get(src, 0) < 2:
            selected.append(article)
            picked_ids.add(article["id"])
            source_counts[src] = source_counts.get(src, 0) + 1

    return selected


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _parse_published_at(raw: Any) -> Optional[datetime]:
    """Try to parse a published_at string into a timezone-aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _publication_cutoff() -> datetime:
    """
    Return the earliest allowed published_at as a UTC datetime.
    Window: yesterday at 9am local time through now.
    Uses the system's local timezone so it works correctly whether the
    machine is on EST, EDT, or any other zone.
    """
    local_now = datetime.now().astimezone()  # local time with tz offset
    yesterday = local_now.date() - timedelta(days=1)
    cutoff_local = datetime(
        yesterday.year, yesterday.month, yesterday.day, 9, 0, 0,
        tzinfo=local_now.tzinfo,
    )
    return cutoff_local.astimezone(timezone.utc)


def _is_healthcare(article: Dict[str, Any]) -> bool:
    """Return True if the article is healthcare-relevant."""
    if article.get("bucket") in HEALTHCARE_BUCKETS:
        return True
    text = f"{article.get('title', '')} {article.get('summary') or ''}"
    return bool(_HEALTHCARE_RE.search(text))


def select_stories(
    db_path: str = "ai_news.db",
    days_back: int = 2,
    max_stories: int = 5,
    topic: str = "general",
) -> List[Dict[str, Any]]:
    """
    Score and rank recent articles, then return up to max_stories items
    with at most one per category (People / Processes / Tech).

    topic="general"    – all recent articles (default)
    topic="healthcare" – pre-filtered to healthcare-relevant articles only

    Only articles published today or yesterday after 9am (local time) are
    considered. Articles with no parseable published_at are kept so we
    don't silently drop content from feeds that omit dates.

    The first item in the returned list is the top-scoring hero story.
    """
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)
    # Use a generous fetched_at window so the DB scan stays fast,
    # then apply the tighter published_at filter in Python below.
    since = (now - timedelta(days=days_back)).isoformat()

    rows = conn.execute(
        """
        SELECT id, title, url, source, bucket, published_at, summary,
               featured_at, paywalled_flag, category_candidate,
               accessible, why_it_matters
        FROM articles
        WHERE fetched_at >= ?
        ORDER BY fetched_at DESC
        """,
        (since,),
    ).fetchall()
    conn.close()

    all_articles = [dict(row) for row in rows]
    if not all_articles:
        return []

    # Filter to articles published today or yesterday after 9am local time.
    # Articles with no parseable date are kept so we don't silently drop content.
    cutoff = _publication_cutoff()
    articles = []
    skipped = 0
    for a in all_articles:
        pub = _parse_published_at(a.get("published_at"))
        if pub is None or pub >= cutoff:
            articles.append(a)
        else:
            skipped += 1

    print(f"  Date filter ({cutoff.strftime('%b %d %H:%M UTC')} cutoff): "
          f"kept {len(articles)}, skipped {skipped} older articles")

    if not articles:
        return []

    # Healthcare topic: restrict to articles that match healthcare keywords/buckets
    if topic == "healthcare":
        articles = [a for a in articles if _is_healthcare(a)]
        print(f"  Healthcare filter: {len(articles)} articles matched")
        if not articles:
            return []

    # Add cross-source pickup bonus before scoring
    _add_cross_source_scores(articles)

    # Score and sort
    for article in articles:
        article["_score"] = score_article(article, now)
    articles.sort(key=lambda a: a["_score"], reverse=True)

    # Deduplicate near-duplicate headlines
    unique = deduplicate_by_headline(articles)

    # Select with category diversity
    selected = _select_by_category(unique, ["People", "Processes", "Tech"], max_stories)
    selected.sort(key=lambda a: a["_score"], reverse=True)

    # Print selection summary
    print(f"  {len(articles)} articles → {len(unique)} unique → {len(selected)} selected")
    for i, a in enumerate(selected):
        cat = a.get("_category", "?")
        label = "HERO" if i == 0 else f"  #{i + 1}"
        src = (a.get("source") or "")[:30]
        print(f"  {label} [{cat}] (score={a['_score']:.1f}) [{src}]: {a['title'][:55]}")

    return selected
