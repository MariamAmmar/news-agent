"""
Shared database utilities: connection factory, schema creation,
live migration for new columns, and the shared insert_articles function.
"""
import sqlite3
from typing import Any, Dict, List

DB_PATH = "ai_news.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist, then apply any pending migrations."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            title              TEXT NOT NULL,
            url                TEXT NOT NULL UNIQUE,
            source             TEXT,
            bucket             TEXT NOT NULL,
            published_at       TEXT,
            summary            TEXT,
            fetched_at         TEXT NOT NULL,
            relevance_score    REAL    DEFAULT 0,
            featured_at        TEXT,
            paywalled_flag     INTEGER DEFAULT 0,
            category_candidate TEXT    DEFAULT 'Tech',
            accessible         INTEGER DEFAULT 1,
            why_it_matters     TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS newsletters (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            subject      TEXT,
            body_html    TEXT,
            body_text    TEXT,
            article_ids  TEXT
        );
        """
    )
    conn.commit()
    # Ensure existing databases get the new columns
    migrate_tables(conn)


def migrate_tables(conn: sqlite3.Connection) -> None:
    """
    Idempotent migration: add new columns to an existing database.
    SQLite raises OperationalError if the column already exists; we ignore it.
    Each column is attempted separately so a partial migration is resumable.
    """
    new_columns = [
        ("paywalled_flag",     "INTEGER DEFAULT 0"),
        ("category_candidate", "TEXT DEFAULT 'Tech'"),
        ("accessible",         "INTEGER DEFAULT 1"),
        ("why_it_matters",     "TEXT DEFAULT ''"),
    ]
    for col, definition in new_columns:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists – safe to continue


def insert_articles(conn: sqlite3.Connection, articles: List[Dict[str, Any]]) -> int:
    """
    Insert normalized article dicts into the DB.
    Silently skips duplicates (same URL via UNIQUE constraint).
    Returns the number of newly inserted rows.
    """
    inserted = 0
    for a in articles:
        try:
            conn.execute(
                """
                INSERT INTO articles
                    (title, url, source, bucket, published_at, summary, fetched_at,
                     paywalled_flag, category_candidate, accessible, why_it_matters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a["title"],
                    a["url"],
                    a["source"],
                    a["bucket"],
                    a.get("published_at"),
                    a.get("summary", ""),
                    a["fetched_at"],
                    a.get("paywalled_flag", 0),
                    a.get("category_candidate", "Tech"),
                    a.get("accessible", 1),
                    a.get("why_it_matters", ""),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # duplicate URL – skip silently
    conn.commit()
    return inserted
