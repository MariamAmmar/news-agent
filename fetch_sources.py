"""
Source ingestion: RSS feeds, Google News RSS, Hacker News, arXiv, and Reddit.

All fetchers normalize their raw data through normalize.normalize() before
inserting via db.insert_articles(), ensuring every article in the DB shares
the same schema regardless of origin.
"""
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import certifi
import feedparser

from config import (
    ARXIV_MAX_RESULTS,
    ARXIV_QUERIES,
    FEEDS,
    GOOGLE_NEWS_QUERIES,
    HEALTHCARE_ARXIV_QUERIES,
    HEALTHCARE_FEEDS,
    HEALTHCARE_GOOGLE_NEWS_QUERIES,
    HEALTHCARE_HN_QUERIES,
    HEALTHCARE_REDDIT_FEEDS,
    HN_MAX_RESULTS,
    HN_QUERIES,
    REDDIT_FEEDS,
)
from db import create_tables, get_connection, insert_articles
from normalize import normalize

# Use certifi's CA bundle so HTTPS feeds work reliably on macOS/Linux
os.environ["SSL_CERT_FILE"] = certifi.where()
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

# Reddit blocks the default Python user-agent
_REDDIT_UA = "Mozilla/5.0 (compatible; news-agent/1.0; +https://github.com/news-agent)"


# ---------------------------------------------------------------------------
# feedparser helpers (shared by RSS, Google News, Reddit, arXiv fetchers)
# ---------------------------------------------------------------------------

def _parse_dt(entry: Dict[str, Any]) -> Optional[str]:
    """Convert feedparser time structs or raw strings to ISO 8601 UTC."""
    for key in ("published_parsed", "updated_parsed"):
        ts = entry.get(key)
        if ts:
            try:
                return datetime(*ts[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            return str(raw)
    return None


def _feed_source(parsed: feedparser.FeedParserDict, fallback: str) -> str:
    title = parsed.get("feed", {}).get("title")
    return str(title).strip() if title else fallback


def _feed_summary(entry: Dict[str, Any]) -> str:
    for key in ("summary", "description"):
        val = entry.get(key)
        if val:
            return str(val).strip()
    content = entry.get("content")
    if content:
        try:
            return str(content[0].get("value", "")).strip()
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
# RSS feed fetcher (existing sources + any new RSS URL)
# ---------------------------------------------------------------------------

def fetch_rss(feed_url: str, bucket: str, fetched_at: str) -> List[Dict[str, Any]]:
    """Fetch a single RSS/Atom feed and return normalized article dicts."""
    parsed = feedparser.parse(feed_url)

    if parsed.bozo:
        # feedparser sets bozo=True for malformed XML but still returns entries
        pass

    source = _feed_source(parsed, feed_url)
    articles = []

    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title")
        if not url or not title:
            continue
        articles.append(
            normalize(
                title=str(title).strip(),
                url=str(url).strip(),
                source=source,
                summary=_feed_summary(entry),
                published_at=_parse_dt(entry),
                bucket=bucket,
                fetched_at=fetched_at,
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Google News RSS (free, no API key)
# Each query string becomes a search feed URL.
# ---------------------------------------------------------------------------

_GNEWS_URL = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)


def fetch_google_news(query: str, fetched_at: str) -> List[Dict[str, Any]]:
    """Fetch Google News RSS results for a search query."""
    url = _GNEWS_URL.format(q=urllib.parse.quote_plus(query))
    parsed = feedparser.parse(url)

    source = f"Google News – {query}"
    articles = []

    for entry in parsed.entries:
        link = entry.get("link")
        title = entry.get("title")
        if not link or not title:
            continue
        articles.append(
            normalize(
                title=str(title).strip(),
                url=str(link).strip(),
                source=source,
                summary=_feed_summary(entry),
                published_at=_parse_dt(entry),
                bucket="google_news",
                fetched_at=fetched_at,
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Hacker News via Algolia search API (free, no auth)
# https://hn.algolia.com/api/v1/search
# ---------------------------------------------------------------------------

_HN_URL = (
    "https://hn.algolia.com/api/v1/search"
    "?query={q}&tags=story&hitsPerPage={n}"
)


def fetch_hn(query: str, fetched_at: str) -> List[Dict[str, Any]]:
    """Fetch top HN stories matching a query via the Algolia API."""
    url = _HN_URL.format(q=urllib.parse.quote_plus(query), n=HN_MAX_RESULTS)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "news-agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"    [HN] Error for '{query}': {exc}")
        return []

    articles = []
    for hit in data.get("hits", []):
        title = hit.get("title") or ""
        if not title:
            continue

        # Use the linked article URL if present; fall back to the HN thread
        link = hit.get("url") or (
            f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        )

        # HN Algolia returns Unix timestamp in created_at_i
        ts_unix = hit.get("created_at_i")
        published_at = (
            datetime.utcfromtimestamp(ts_unix).replace(tzinfo=timezone.utc).isoformat()
            if ts_unix
            else None
        )

        # Ask/Show HN posts carry body text; link posts don't
        summary = hit.get("story_text") or ""

        articles.append(
            normalize(
                title=title,
                url=link,
                source="Hacker News",
                summary=summary,
                published_at=published_at,
                bucket="hacker_news",
                fetched_at=fetched_at,
            )
        )
    return articles


# ---------------------------------------------------------------------------
# arXiv via Atom API (free, no auth)
# feedparser handles Atom natively.
# ---------------------------------------------------------------------------

_ARXIV_URL = (
    "http://export.arxiv.org/api/query"
    "?search_query=all:{q}&sortBy=submittedDate&sortOrder=descending&max_results={n}"
)


def fetch_arxiv(query: str, fetched_at: str) -> List[Dict[str, Any]]:
    """Fetch recent arXiv papers matching a query."""
    url = _ARXIV_URL.format(q=urllib.parse.quote_plus(query), n=ARXIV_MAX_RESULTS)
    parsed = feedparser.parse(url)

    articles = []
    for entry in parsed.entries:
        title = entry.get("title", "").replace("\n", " ").strip()
        link = entry.get("link")
        if not title or not link:
            continue
        # arXiv summaries are full abstracts – excellent signal
        summary = entry.get("summary", "").replace("\n", " ").strip()
        articles.append(
            normalize(
                title=title,
                url=link,
                source="arXiv",
                summary=summary,
                published_at=_parse_dt(entry),
                bucket="arxiv",
                fetched_at=fetched_at,
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Reddit RSS (read-only, no auth)
# Reddit blocks default Python UAs; we set a browser-like User-Agent.
# ---------------------------------------------------------------------------

def fetch_reddit(feed_url: str, bucket: str, fetched_at: str) -> List[Dict[str, Any]]:
    """Fetch a Reddit RSS feed (top posts for today)."""
    parsed = feedparser.parse(
        feed_url, request_headers={"User-Agent": _REDDIT_UA}
    )

    source = _feed_source(parsed, feed_url)
    articles = []

    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title")
        if not url or not title:
            continue
        articles.append(
            normalize(
                title=str(title).strip(),
                url=str(url).strip(),
                source=f"Reddit – {source}",
                summary=_feed_summary(entry),
                published_at=_parse_dt(entry),
                bucket=bucket,
                fetched_at=fetched_at,
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_and_store(db_path: str = "ai_news.db", stream: str = "all") -> None:
    """
    Run all fetchers and persist new articles to the database.

    stream="general"    – broad AI news sources only
    stream="healthcare" – healthcare-specific sources only
    stream="all"        – both streams (default)

    A single fetched_at timestamp is shared across all sources in one run
    so the ranker's days_back filter treats them consistently.
    Articles are deduplicated by URL so running both streams is safe.
    """
    conn = get_connection(db_path)
    create_tables(conn)  # also runs migrate_tables for existing DBs

    fetched_at = datetime.now(timezone.utc).isoformat()
    total_fetched = 0
    total_inserted = 0

    def _run(label: str, articles: List[Dict[str, Any]]) -> None:
        nonlocal total_fetched, total_inserted
        ins = insert_articles(conn, articles)
        total_fetched += len(articles)
        total_inserted += ins
        print(f"    {len(articles)} found, {ins} new")

    run_general = stream in ("general", "all")
    run_healthcare = stream in ("healthcare", "all")

    # --- General: RSS feeds ---
    if run_general:
        for bucket, urls in FEEDS.items():
            print(f"\n  [RSS] {bucket}")
            for url in urls:
                print(f"    {url}")
                try:
                    articles = fetch_rss(url, bucket, fetched_at)
                    _run(url, articles)
                except Exception as exc:
                    print(f"    [ERROR] {exc}")

    # --- Healthcare: RSS feeds ---
    if run_healthcare:
        for bucket, urls in HEALTHCARE_FEEDS.items():
            # Skip buckets already covered by the general stream
            if run_general and bucket in FEEDS:
                continue
            print(f"\n  [RSS/Healthcare] {bucket}")
            for url in urls:
                print(f"    {url}")
                try:
                    articles = fetch_rss(url, bucket, fetched_at)
                    _run(url, articles)
                except Exception as exc:
                    print(f"    [ERROR] {exc}")

    # --- Google News RSS ---
    queries: List[str] = []
    if run_general:
        queries += GOOGLE_NEWS_QUERIES
    if run_healthcare:
        # De-duplicate in case any query appears in both lists
        existing = set(queries)
        queries += [q for q in HEALTHCARE_GOOGLE_NEWS_QUERIES if q not in existing]

    if queries:
        print("\n  [Google News]")
        for query in queries:
            print(f"    Query: {query}")
            try:
                articles = fetch_google_news(query, fetched_at)
                _run(query, articles)
            except Exception as exc:
                print(f"    [ERROR] {exc}")
            time.sleep(0.5)  # avoid hammering Google

    # --- Hacker News ---
    hn_queries: List[str] = []
    if run_general:
        hn_queries += HN_QUERIES
    if run_healthcare:
        existing_hn = set(hn_queries)
        hn_queries += [q for q in HEALTHCARE_HN_QUERIES if q not in existing_hn]

    if hn_queries:
        print("\n  [Hacker News]")
        for query in hn_queries:
            print(f"    Query: {query}")
            try:
                articles = fetch_hn(query, fetched_at)
                _run(query, articles)
            except Exception as exc:
                print(f"    [ERROR] {exc}")
            time.sleep(0.3)  # be polite to the Algolia API

    # --- arXiv ---
    arxiv_queries: List[str] = []
    if run_general:
        arxiv_queries += ARXIV_QUERIES
    if run_healthcare:
        existing_ax = set(arxiv_queries)
        arxiv_queries += [q for q in HEALTHCARE_ARXIV_QUERIES if q not in existing_ax]

    if arxiv_queries:
        print("\n  [arXiv]")
        for query in arxiv_queries:
            print(f"    Query: {query}")
            try:
                articles = fetch_arxiv(query, fetched_at)
                _run(query, articles)
            except Exception as exc:
                print(f"    [ERROR] {exc}")
            time.sleep(0.5)

    # --- Reddit RSS ---
    reddit_feeds: Dict[str, List[str]] = {}
    if run_general:
        reddit_feeds.update(REDDIT_FEEDS)
    if run_healthcare:
        for bucket, urls in HEALTHCARE_REDDIT_FEEDS.items():
            if bucket not in reddit_feeds:
                reddit_feeds[bucket] = urls

    if reddit_feeds:
        print("\n  [Reddit]")
        for bucket, urls in reddit_feeds.items():
            for url in urls:
                print(f"    {url}")
                try:
                    articles = fetch_reddit(url, bucket, fetched_at)
                    _run(url, articles)
                except Exception as exc:
                    print(f"    [ERROR] {exc}")

    print(f"\n  Total: {total_fetched} fetched, {total_inserted} new stored.")
    conn.close()


if __name__ == "__main__":
    fetch_and_store()
