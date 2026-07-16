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
        # Cache economic calendar events (dari Trading Economics & BLS), supaya
        # tidak perlu hit API pihak ketiga tiap kali scheduler cek notifikasi.
        # Di-refresh berkala oleh job terpisah (lihat economic_calendar.py & bot.py).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS economic_events (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                datetime_utc TEXT,
                note TEXT,
                impact TEXT,
                impact_reason TEXT,
                source TEXT,
                country TEXT,
                currency TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Histori snapshot BTC harian (1 baris per hari WIB), dipakai untuk
        # perbandingan "hari ini vs kemarin" di insight pagi supaya narasinya
        # tidak cuma angka absolut tapi juga ada konteks tren.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS btc_snapshots (
                date TEXT PRIMARY KEY,   -- format YYYY-MM-DD (WIB)
                price REAL,
                change_24h REAL,
                market_cap REAL,
                volume_24h REAL,
                btc_dominance REAL,
                eth_dominance REAL,
                fear_greed_value INTEGER,
                altcoin_season_index INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
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


# ---------------------------------------------------------------------------
# Economic calendar cache
# ---------------------------------------------------------------------------

_ECON_EVENT_COLUMNS = [
    "id", "name", "type", "datetime_utc", "note",
    "impact", "impact_reason", "source", "country", "currency",
]


def upsert_economic_events(events: list[dict]):
    """Simpan/update batch event economic calendar ke cache.
    id dipakai sebagai primary key supaya event yang sama (mis. CPI bulan
    ini) tidak dianggap baru tiap kali di-refresh - status "sudah dinotif"
    di tabel sent_notifications tetap konsisten."""
    if not events:
        return
    with get_conn() as conn:
        for e in events:
            conn.execute(
                """
                INSERT INTO economic_events
                    (id, name, type, datetime_utc, note, impact, impact_reason, source, country, currency, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    datetime_utc=excluded.datetime_utc,
                    note=excluded.note,
                    impact=excluded.impact,
                    impact_reason=excluded.impact_reason,
                    source=excluded.source,
                    country=excluded.country,
                    currency=excluded.currency,
                    fetched_at=CURRENT_TIMESTAMP
                """,
                (
                    e["id"], e["name"], e.get("type", "ECON"), e["datetime_utc"],
                    e.get("note", ""), e.get("impact", "Low"), e.get("impact_reason", ""),
                    e.get("source", ""), e.get("country", ""), e.get("currency", ""),
                ),
            )


def get_cached_economic_events() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(_ECON_EVENT_COLUMNS)} FROM economic_events"
        ).fetchall()
    return [dict(zip(_ECON_EVENT_COLUMNS, row)) for row in rows]


def prune_old_economic_events(before_iso: str):
    """Hapus event yang sudah lewat jauh dari cache (housekeeping, supaya
    tabel tidak terus membesar). Tidak menyentuh histori sent_notifications."""
    with get_conn() as conn:
        conn.execute("DELETE FROM economic_events WHERE datetime_utc < ?", (before_iso,))


# ---------------------------------------------------------------------------
# BTC daily snapshot (histori untuk perbandingan "hari ini vs kemarin")
# ---------------------------------------------------------------------------

_BTC_SNAPSHOT_COLUMNS = [
    "date", "price", "change_24h", "market_cap", "volume_24h",
    "btc_dominance", "eth_dominance", "fear_greed_value", "altcoin_season_index",
]


def upsert_btc_snapshot(date_str: str, snapshot: dict):
    """Simpan/update snapshot BTC untuk tanggal `date_str` (format YYYY-MM-DD,
    WIB). Kalau job insight harian sempat jalan 2x di hari yang sama (mis.
    manual trigger buat testing), baris yang sama akan di-overwrite, bukan
    dobel - date dipakai sebagai primary key."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO btc_snapshots
                (date, price, change_24h, market_cap, volume_24h,
                 btc_dominance, eth_dominance, fear_greed_value, altcoin_season_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                price=excluded.price,
                change_24h=excluded.change_24h,
                market_cap=excluded.market_cap,
                volume_24h=excluded.volume_24h,
                btc_dominance=excluded.btc_dominance,
                eth_dominance=excluded.eth_dominance,
                fear_greed_value=excluded.fear_greed_value,
                altcoin_season_index=excluded.altcoin_season_index
            """,
            (
                date_str,
                snapshot.get("price"),
                snapshot.get("change_24h"),
                snapshot.get("market_cap"),
                snapshot.get("volume_24h"),
                snapshot.get("btc_dominance"),
                snapshot.get("eth_dominance"),
                snapshot.get("fear_greed_value"),
                snapshot.get("altcoin_season_index"),
            ),
        )


def get_btc_snapshot_before(date_str: str) -> dict | None:
    """Ambil snapshot BTC paling baru SEBELUM `date_str` (buat perbandingan
    "hari ini vs kemarin"). Return None kalau belum ada histori sama sekali
    (mis. baru pertama kali bot dijalankan)."""
    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT {', '.join(_BTC_SNAPSHOT_COLUMNS)} FROM btc_snapshots
            WHERE date < ? ORDER BY date DESC LIMIT 1
            """,
            (date_str,),
        ).fetchone()
    return dict(zip(_BTC_SNAPSHOT_COLUMNS, row)) if row else None


def prune_old_btc_snapshots(before_date: str):
    """Hapus histori snapshot yang lebih lama dari `before_date` (housekeeping,
    default dipanggil dengan cutoff ~30 hari dari main.py/bot.py)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM btc_snapshots WHERE date < ?", (before_date,))
