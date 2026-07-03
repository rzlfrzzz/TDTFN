"""
Database sederhana pakai SQLite (tidak butuh server tambahan).
Menyimpan:
- subscribers: daftar chat_id yang subscribe notifikasi
- sent_notifications: catatan supaya notifikasi tidak terkirim dobel
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "fedbot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_notifications (
                event_id TEXT,
                stage TEXT,           -- '24h' atau '15m'
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, stage)
            )
            """
        )


def add_subscriber(chat_id: int, username: str | None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, username) VALUES (?, ?)",
            (chat_id, username),
        )


def remove_subscriber(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))


def get_all_subscribers() -> list[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    return [r[0] for r in rows]


def is_subscribed(chat_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return row is not None


def already_sent(event_id: str, stage: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM sent_notifications WHERE event_id = ? AND stage = ?",
            (event_id, stage),
        ).fetchone()
    return row is not None


def mark_sent(event_id: str, stage: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_notifications (event_id, stage) VALUES (?, ?)",
            (event_id, stage),
        )
