"""
Daftar event Fed / ekonomi penting.

Sumber jadwal FOMC RESMI: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
Jadwal FOMC diumumkan Fed di awal tahun untuk 8 meeting setahun, jadi cukup
diperbarui 1x/tahun di sini (lebih stabil daripada scraping tiap hari).

Waktu ditulis dalam UTC supaya tidak ambigu (bebas isu DST).
- Statement FOMC rilis jam 14:00 ET.
  * Saat US Daylight Saving (Mar-Nov)  -> 14:00 ET = 18:00 UTC
  * Saat US Standard Time (Nov-Mar)    -> 14:00 ET = 19:00 UTC

Tambah event baru cukup append ke list FED_EVENTS di bawah, format:
{
    "id": "kode-unik",          # dipakai untuk cek "sudah dinotif atau belum"
    "name": "Nama event",
    "type": "FOMC" / "CPI" / "NFP" / "SPEECH" / dll,
    "datetime_utc": "YYYY-MM-DDTHH:MM:SS",   # ISO format, UTC
    "note": "keterangan singkat (opsional)",
    "impact": "High" / "Medium" / "Low",     # dampak ke USD (opsional, default High utk FOMC)
    "impact_reason": "penjelasan singkat",   # opsional
    "source": "nama sumber",                 # opsional
}

Selain daftar manual di sini, event ekonomi lain (CPI, NFP, PPI, GDP, dll)
diambil OTOMATIS dari Trading Economics + BLS lewat economic_calendar.py,
di-refresh berkala oleh scheduler di bot.py, dan disimpan ke cache SQLite
(lihat database.py). get_upcoming_events() di bawah menggabungkan
FED_EVENTS (manual) dengan cache tersebut.
"""

from datetime import datetime, timezone

import database as db

_FOMC_IMPACT_REASON = (
    "Keputusan & statement FOMC adalah penggerak utama pasar karena berisi "
    "keputusan suku bunga langsung dari The Fed serta sinyal arah kebijakan "
    "moneter ke depan (forward guidance)."
)

FED_EVENTS = [
    {
        "id": "fomc-2026-07",
        "name": "FOMC Meeting - Rate Decision",
        "type": "FOMC",
        "datetime_utc": "2026-07-29T18:00:00",
        "note": "Pengumuman suku bunga + statement, dilanjutkan press conference Powell 30 menit kemudian.",
        "impact": "High",
        "impact_reason": _FOMC_IMPACT_REASON,
        "source": "Federal Reserve (federalreserve.gov)",
    },
    {
        "id": "fomc-2026-09",
        "name": "FOMC Meeting - Rate Decision",
        "type": "FOMC",
        "datetime_utc": "2026-09-16T18:00:00",
        "note": "Meeting ini disertai economic projections (dot plot).",
        "impact": "High",
        "impact_reason": _FOMC_IMPACT_REASON,
        "source": "Federal Reserve (federalreserve.gov)",
    },
    {
        "id": "fomc-2026-10",
        "name": "FOMC Meeting - Rate Decision",
        "type": "FOMC",
        "datetime_utc": "2026-10-28T18:00:00",
        "note": "Pengumuman suku bunga + statement, dilanjutkan press conference Powell 30 menit kemudian.",
        "impact": "High",
        "impact_reason": _FOMC_IMPACT_REASON,
        "source": "Federal Reserve (federalreserve.gov)",
    },
    {
        "id": "fomc-2026-12",
        "name": "FOMC Meeting - Rate Decision",
        "type": "FOMC",
        "datetime_utc": "2026-12-09T19:00:00",
        "note": "Meeting ini disertai economic projections (dot plot). Waktu sudah standard time (UTC+19:00->cek ulang mendekati hari H).",
        "impact": "High",
        "impact_reason": _FOMC_IMPACT_REASON,
        "source": "Federal Reserve (federalreserve.gov)",
    },
]


def get_event_dt(event: dict) -> datetime:
    return datetime.fromisoformat(event["datetime_utc"]).replace(tzinfo=timezone.utc)


def get_all_events() -> list[dict]:
    """Gabungkan daftar FOMC manual + cache economic calendar (CPI, NFP, PPI,
    GDP, dll dari Trading Economics & BLS). Kalau cache belum ada isinya
    (mis. baru pertama kali jalan sebelum scheduler refresh sempat jalan),
    ya cuma dapat FOMC manual saja - tidak crash."""
    combined = list(FED_EVENTS)
    try:
        combined.extend(db.get_cached_economic_events())
    except Exception as e:
        print(f"[events] Gagal load cache economic calendar: {e}")
    return combined


def get_upcoming_events(now: datetime | None = None) -> list[dict]:
    """Return event (FOMC manual + economic calendar) yang waktunya masih
    di masa depan, terurut."""
    now = now or datetime.now(timezone.utc)
    upcoming = [e for e in get_all_events() if get_event_dt(e) > now]
    return sorted(upcoming, key=get_event_dt)
