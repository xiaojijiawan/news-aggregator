import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "news.db"

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            title_hash TEXT,
            category TEXT,
            source TEXT,
            summary TEXT DEFAULT "",
            content TEXT DEFAULT "",
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_title_hash ON news_history(title_hash)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fetched_at ON news_history(fetched_at)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries_cache (
            date TEXT,
            category TEXT,
            content TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, category)
        )
    """)
    conn.commit()
    return conn

def is_duplicate(url: str, title: str) -> bool:
    """Check if a news item already exists by URL or similar title."""
    conn = get_conn()
    title_hash = hashlib.md5(title.strip().encode()).hexdigest()
    row = conn.execute(
        "SELECT id FROM news_history WHERE url = ? OR title_hash = ?",
        (url, title_hash)
    ).fetchone()
    return row is not None

def insert_news(url: str, title: str, category: str, source: str, summary: str = "", content: str = ""):
    conn = get_conn()
    title_hash = hashlib.md5(title.strip().encode()).hexdigest()
    conn.execute(
        "INSERT OR IGNORE INTO news_history (url, title, title_hash, category, source, summary, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, title, title_hash, category, source, summary or "", content or "")
    )
    conn.commit()

def get_recent_titles(days: int = 7) -> list[str]:
    cutoff = datetime.now() - timedelta(days=days)
    conn = get_conn()
    rows = conn.execute(
        "SELECT title FROM news_history WHERE fetched_at >= ?",
        (cutoff,)
    ).fetchall()
    return [r["title"] for r in rows]


def get_today_news() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM news_history WHERE date(fetched_at) = ? ORDER BY fetched_at DESC",
        (today,)
    ).fetchall()
    return [dict(r) for r in rows]


def save_summaries(summaries: dict[str, str], overall: str):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    for cat, text in summaries.items():
        conn.execute(
            "INSERT OR REPLACE INTO summaries_cache (date, category, content, generated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (today, cat, text),
        )
    if overall:
        conn.execute(
            "INSERT OR REPLACE INTO summaries_cache (date, category, content, generated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (today, "__overall__", overall),
        )
    conn.commit()


def get_cached_summaries() -> dict[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT category, content FROM summaries_cache WHERE date = ?",
        (today,)
    ).fetchall()
    result = {}
    for r in rows:
        result[r["category"]] = r["content"]
    return result
