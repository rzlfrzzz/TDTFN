"""
Ambil jadwal economic calendar dari 3 sumber:

1. **BLS (Bureau of Labor Statistics)** - via ICS calendar resmi mereka
   (https://www.bls.gov/schedule/news_release/bls.ics). Ini feed publik
   resmi yang dipakai orang untuk subscribe ke Outlook/Google Calendar,
   jadi jauh lebih stabil & akurat dibanding scraping HTML halaman jadwal
   mereka. Meng-cover rilis seperti CPI, Employment Situation (NFP), PPI,
   JOLTS, Employment Cost Index, Real Earnings, Import/Export Price Index,
   Productivity & Costs, dll. Semua jam di feed ini dalam Eastern Time
   (otomatis di-handle oleh timezone block di dalam file ICS-nya).

2. **Trading Economics** - via REST API (https://api.tradingeconomics.com).
   Meng-cover event ekonomi AS yang lebih luas di luar rilis BLS: GDP,
   Retail Sales, ISM Manufacturing/Services PMI, Consumer Confidence,
   Housing Starts, Durable Goods, PCE, dll. Field "Importance" dari TE
   (0/1/2 = Low/Medium/High) dipakai sebagai salah satu sinyal dampak.
   ⚠️ Kalau tidak diisi API key sendiri (TRADING_ECONOMICS_API_KEY di .env),
   bot pakai key demo publik "guest:guest" yang HANYA mengembalikan data
   sample/terbatas (bukan kalender penuh & real-time). Untuk pemakaian
   serius, daftar API key sendiri di https://developer.tradingeconomics.com/.

3. **Federal Reserve** - via RSS resmi (https://www.federalreserve.gov/feeds/press_all.xml).
   Fed TIDAK punya RSS/API untuk "jadwal ke depan", RSS mereka sifatnya
   reaktif (baru muncul setelah rilis terjadi). Makanya dipakai untuk command
   /fednews (lihat rilis terbaru dari Fed), BUKAN untuk notifikasi H-24/H-15
   karena sifatnya bukan forward-looking. Untuk jadwal FOMC ke depan, tetap
   dipakai daftar manual di events.py (lebih stabil, sesuai penjelasan di
   README).

Event dari BLS & Trading Economics dinormalisasi ke format yang sama dengan
FED_EVENTS di events.py:
{
    "id": str (unik & stabil antar refresh, dipakai buat cek "sudah dinotif"),
    "name": str,
    "type": "ECON",
    "datetime_utc": "YYYY-MM-DDTHH:MM:SS" (ISO, UTC),
    "note": str (info tambahan, misal forecast/previous kalau ada),
    "impact": "High" / "Medium" / "Low"   -> dampak ke USD,
    "impact_reason": str (penjelasan singkat kenapa dampaknya segitu),
    "source": str,
    "country": str,
    "currency": str,
}
"""

import hashlib
from datetime import datetime, timedelta, timezone

import requests

from config import TRADING_ECONOMICS_API_KEY, CALENDAR_COUNTRY

BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
TE_BASE_URL = "https://api.tradingeconomics.com"
FED_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"

REQUEST_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Klasifikasi dampak terhadap USD
# ---------------------------------------------------------------------------
# Urutan dicek dari atas ke bawah, keyword paling spesifik ditaruh duluan
# supaya tidak "ketiban" keyword yang lebih umum (mis. "core cpi" dicek
# sebelum "cpi").
#
# Reasoning ditulis dalam Bahasa Indonesia, dipakai sebagai konteks tambahan
# yang dikirim ke DeepSeek supaya narasinya akurat & konsisten, bukan cuma
# ditampilkan mentah-mentah ke user.

HIGH_IMPACT_INFO = [
    ("nonfarm payrolls", "Data tenaga kerja non-pertanian (NFP) adalah salah satu indikator paling dipantau pasar. Perubahan jumlah lapangan kerja secara langsung memengaruhi ekspektasi arah kebijakan suku bunga The Fed, sehingga rentan memicu pergerakan tajam pada USD."),
    ("employment situation", "Rilis \"Employment Situation\" dari BLS mencakup Non-Farm Payrolls & tingkat pengangguran sekaligus - salah satu data paling krusial bagi The Fed dalam menentukan arah suku bunga, sehingga dampaknya ke USD biasanya besar."),
    ("unemployment rate", "Tingkat pengangguran adalah indikator utama kesehatan pasar tenaga kerja yang jadi salah satu mandat utama The Fed, sehingga pergerakannya kerap memicu reaksi kuat pada USD."),
    ("core cpi", "Core CPI (inflasi inti, tanpa makanan & energi) adalah acuan utama The Fed untuk menilai tekanan inflasi jangka panjang, sehingga datanya sangat memengaruhi ekspektasi suku bunga dan USD."),
    ("consumer price index", "CPI mengukur inflasi dari sisi konsumen dan jadi salah satu variabel utama yang dipantau The Fed dalam menentukan kebijakan moneter, sehingga rilisnya sering memicu volatilitas tinggi pada USD."),
    ("cpi", "Data inflasi (CPI) sangat memengaruhi ekspektasi kebijakan suku bunga The Fed, sehingga berdampak besar pada pergerakan USD."),
    ("core pce", "Core PCE adalah ukuran inflasi favorit The Fed (mandat resmi mereka), sehingga datanya punya pengaruh besar terhadap ekspektasi suku bunga dan USD."),
    ("personal consumption expenditures", "PCE Price Index adalah acuan inflasi resmi yang dipakai The Fed, sehingga datanya berdampak besar terhadap ekspektasi kebijakan moneter dan USD."),
    ("fomc", "Keputusan & statement FOMC adalah penggerak utama pasar karena berisi keputusan suku bunga langsung dari The Fed serta sinyal arah kebijakan ke depan."),
    ("federal funds rate", "Perubahan suku bunga acuan The Fed berdampak langsung & besar terhadap USD karena memengaruhi imbal hasil aset berdenominasi dolar."),
    ("interest rate decision", "Keputusan suku bunga bank sentral berdampak langsung terhadap daya tarik mata uang terkait, termasuk USD kalau ini keputusan The Fed."),
    ("gross domestic product", "GDP adalah indikator utama kesehatan ekonomi secara keseluruhan, jadi rilisnya berdampak besar terhadap ekspektasi kebijakan The Fed dan USD."),
    (" gdp", "GDP adalah indikator utama kesehatan ekonomi secara keseluruhan, jadi rilisnya berdampak besar terhadap ekspektasi kebijakan The Fed dan USD."),
    ("ism manufacturing", "ISM Manufacturing PMI adalah indikator dini (leading indicator) aktivitas sektor manufaktur yang cukup dipantau pasar untuk menilai arah ekonomi AS."),
    ("ism services", "ISM Services PMI mencerminkan aktivitas sektor jasa yang porsinya besar dalam ekonomi AS, sehingga berpengaruh terhadap ekspektasi pertumbuhan & USD."),
    ("producer price index", "PPI mengukur inflasi dari sisi produsen (pipeline inflation) yang sering jadi indikator awal sebelum tekanan itu sampai ke konsumen (CPI), sehingga tetap dipantau ketat pasar."),
    ("ppi", "PPI mengukur inflasi dari sisi produsen yang sering jadi sinyal awal tekanan harga sebelum sampai ke konsumen."),
    ("retail sales", "Retail Sales mencerminkan kekuatan belanja konsumen, komponen terbesar ekonomi AS, sehingga datanya cukup berpengaruh terhadap ekspektasi pertumbuhan & USD."),
    ("job openings", "JOLTS mengukur jumlah lowongan kerja yang jadi salah satu indikator keseimbangan pasar tenaga kerja yang dipantau The Fed."),
    ("jolts", "JOLTS mengukur jumlah lowongan kerja yang jadi salah satu indikator keseimbangan pasar tenaga kerja yang dipantau The Fed."),
]

MEDIUM_IMPACT_INFO = [
    ("durable goods", "Durable Goods Orders mencerminkan niat investasi bisnis jangka menengah, jadi cukup relevan untuk menilai arah ekonomi meski dampaknya ke USD biasanya tidak sebesar data inflasi/tenaga kerja utama."),
    ("housing starts", "Housing Starts mencerminkan aktivitas sektor properti yang sensitif terhadap suku bunga, jadi cukup relevan dipantau meski dampaknya ke USD umumnya moderat."),
    ("building permits", "Building Permits jadi indikator dini aktivitas konstruksi ke depan, dampaknya ke USD umumnya moderat."),
    ("existing home sales", "Existing Home Sales mencerminkan aktivitas pasar properti yang sensitif terhadap suku bunga."),
    ("new home sales", "New Home Sales mencerminkan aktivitas pasar properti yang sensitif terhadap suku bunga."),
    ("consumer confidence", "Consumer Confidence mencerminkan optimisme rumah tangga terhadap ekonomi, cukup berpengaruh terhadap ekspektasi belanja konsumen ke depan."),
    ("michigan consumer sentiment", "Survei sentimen konsumen Michigan sering dipakai sebagai indikator dini arah belanja konsumen."),
    ("initial jobless claims", "Klaim pengangguran mingguan jadi indikator cepat (high-frequency) kondisi pasar tenaga kerja, meski dampaknya ke USD biasanya lebih moderat dibanding data bulanan seperti NFP."),
    ("trade balance", "Data neraca perdagangan memengaruhi ekspektasi terhadap aliran modal & permintaan USD dari sisi perdagangan internasional."),
    ("industrial production", "Industrial Production mencerminkan output sektor manufaktur & pertambangan, relevan untuk menilai kesehatan sektor riil ekonomi."),
    ("employment cost index", "Employment Cost Index mengukur pertumbuhan upah & tunjangan, salah satu indikator tekanan inflasi dari sisi biaya tenaga kerja yang diperhatikan The Fed."),
    ("real earnings", "Real Earnings mencerminkan daya beli riil pekerja setelah memperhitungkan inflasi, relevan untuk menilai kekuatan konsumsi ke depan."),
    ("productivity", "Data produktivitas & biaya tenaga kerja memberi gambaran efisiensi ekonomi & tekanan inflasi dari sisi biaya produksi."),
]

DEFAULT_LOW_REASON = "Event ini umumnya berdampak terbatas/lokal terhadap pergerakan USD dibanding data inflasi, tenaga kerja, atau keputusan suku bunga utama."
DEFAULT_MEDIUM_REASON = "Event ini punya relevansi terhadap arah ekonomi AS, namun dampaknya ke USD biasanya tidak sebesar data inflasi/tenaga kerja/suku bunga utama."
DEFAULT_HIGH_REASON = "Event ini termasuk data-data utama yang jadi acuan The Fed dalam menentukan kebijakan moneter, sehingga berpotensi memicu volatilitas tinggi pada USD."

# Rilis-rilis yang "dimiliki" BLS - dipakai untuk MENGHINDARI duplikasi kalau
# event yang sama juga muncul di hasil Trading Economics (BLS ICS dipakai
# sebagai sumber utama utk timing-nya karena lebih presisi & resmi).
BLS_OWNED_KEYWORDS = [
    "cpi", "consumer price index", "ppi", "producer price index",
    "non farm payrolls", "nonfarm payrolls", "employment situation",
    "jolts", "job openings", "employment cost index", "average hourly earnings",
    "unemployment rate", "real earnings", "import price", "export price",
    "productivity",
]

# Event yang sudah dicover manual di events.py (FOMC) - jangan didobel dari TE.
FOMC_OWNED_KEYWORDS = ["fomc", "fed interest rate", "interest rate decision", "federal funds rate"]


def classify_impact(name: str, te_importance: int | None = None) -> tuple[str, str]:
    """Tentukan level dampak (High/Medium/Low) + alasannya terhadap USD.

    Prioritas: cocokkan dulu ke keyword yang sudah dikurasi manual (lebih
    akurat & reasoning-nya lebih spesifik). Kalau tidak ada yang cocok,
    baru fallback ke field "Importance" dari Trading Economics (kalau ada).
    """
    name_lower = name.lower()

    for keyword, reason in HIGH_IMPACT_INFO:
        if keyword in name_lower:
            return "High", reason

    for keyword, reason in MEDIUM_IMPACT_INFO:
        if keyword in name_lower:
            return "Medium", reason

    if te_importance is not None:
        if te_importance >= 2:
            return "High", DEFAULT_HIGH_REASON
        if te_importance == 1:
            return "Medium", DEFAULT_MEDIUM_REASON
        return "Low", DEFAULT_LOW_REASON

    return "Low", DEFAULT_LOW_REASON


def _stable_id(prefix: str, *parts: str) -> str:
    """Bikin id yang stabil (sama tiap kali di-refresh) dari beberapa bagian,
    supaya event yang sama tidak dianggap event baru tiap kali cache di-refresh
    (penting supaya status "sudah dinotif" di database tetap konsisten)."""
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


# ---------------------------------------------------------------------------
# 1. BLS - via ICS calendar resmi
# ---------------------------------------------------------------------------

def fetch_bls_calendar(lookahead_days: int = 14) -> list[dict]:
    """Ambil jadwal rilis BLS dari ICS calendar resmi mereka.

    Return list of dict (format event standar), atau [] kalau gagal
    (jangan sampai bikin bot crash gara-gara BLS lagi down/format berubah).
    """
    try:
        from icalendar import Calendar
    except ImportError:
        print("[economic_calendar] Package 'icalendar' belum terinstall, skip fetch BLS. "
              "Jalankan: pip install icalendar")
        return []

    try:
        resp = requests.get(BLS_ICS_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"[economic_calendar] Gagal ambil BLS ICS calendar: {e}")
        return []

    try:
        cal = Calendar.from_ical(resp.content)
    except Exception as e:
        print(f"[economic_calendar] Gagal parse BLS ICS calendar: {e}")
        return []

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=lookahead_days)

    events = []
    for component in cal.walk("VEVENT"):
        try:
            summary = str(component.get("summary", "")).strip()
            if not summary:
                continue

            dt_field = component.get("dtstart")
            if dt_field is None:
                continue
            dt_value = dt_field.dt

            # dtstart bisa berupa datetime (dengan tzinfo dari VTIMEZONE US-Eastern
            # yang didefinisikan di dalam file ICS-nya) atau, jarang, date saja.
            if isinstance(dt_value, datetime):
                if dt_value.tzinfo is None:
                    # fallback kalau tidak ada info timezone sama sekali
                    dt_utc = dt_value.replace(tzinfo=timezone.utc)
                else:
                    dt_utc = dt_value.astimezone(timezone.utc)
            else:
                # Cuma tanggal tanpa jam (jarang terjadi di feed ini)
                dt_utc = datetime.combine(dt_value, datetime.min.time()).replace(tzinfo=timezone.utc)

            if not (now <= dt_utc <= horizon):
                continue

            uid = str(component.get("uid", "")) or summary
            impact, reason = classify_impact(summary)

            events.append({
                "id": _stable_id("bls", uid),
                "name": summary,
                "type": "ECON",
                "datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
                "note": reason,
                "impact": impact,
                "impact_reason": reason,
                "source": "BLS (Bureau of Labor Statistics)",
                "country": "United States",
                "currency": "USD",
            })
        except Exception as e:
            print(f"[economic_calendar] Skip 1 event BLS karena error parse: {e}")
            continue

    return events


# ---------------------------------------------------------------------------
# 2. Trading Economics - via REST API
# ---------------------------------------------------------------------------

def _is_bls_owned(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in BLS_OWNED_KEYWORDS)


def _is_fomc_owned(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in FOMC_OWNED_KEYWORDS)


def fetch_trading_economics_calendar(lookahead_days: int = 14) -> list[dict]:
    """Ambil economic calendar dari Trading Economics API untuk negara di
    CALENDAR_COUNTRY (default "united states"), lalu filter supaya hanya
    ambil event yang BELUM dicover oleh BLS ICS (fetch_bls_calendar) atau
    daftar manual FOMC di events.py, supaya tidak dobel notifikasi.

    Return [] kalau gagal / API key tidak valid / rate limit (jangan bikin
    bot crash - toh masih ada data dari BLS & FOMC manual).
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=lookahead_days)

    start_str = now.strftime("%Y-%m-%d")
    end_str = horizon.strftime("%Y-%m-%d")

    url = f"{TE_BASE_URL}/calendar/country/{CALENDAR_COUNTRY}/{start_str}/{end_str}"
    params = {"c": TRADING_ECONOMICS_API_KEY, "f": "json"}

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 401:
            print("[economic_calendar] Trading Economics API key tidak valid (401). "
                  "Cek TRADING_ECONOMICS_API_KEY di .env.")
            return []
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"[economic_calendar] Gagal ambil/parse data Trading Economics: {e}")
        return []

    if not isinstance(payload, list):
        print(f"[economic_calendar] Format response Trading Economics tidak dikenali: {type(payload)}")
        return []

    events = []
    for item in payload:
        try:
            country = str(item.get("Country", ""))
            if country.lower() != CALENDAR_COUNTRY.lower():
                continue

            name = str(item.get("Event", "")).strip()
            if not name:
                continue

            # Hindari duplikasi dengan BLS ICS (lebih presisi & resmi utk rilis BLS)
            # dan dengan daftar manual FOMC di events.py.
            if _is_bls_owned(name) or _is_fomc_owned(name):
                continue

            date_str = str(item.get("Date", "")).replace("Z", "")
            if not date_str:
                continue
            try:
                dt_utc = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if not (now <= dt_utc <= horizon):
                continue

            te_importance = item.get("Importance")
            try:
                te_importance = int(te_importance) if te_importance is not None else None
            except (TypeError, ValueError):
                te_importance = None

            impact, reason = classify_impact(name, te_importance=te_importance)

            forecast = str(item.get("Forecast") or item.get("TEForecast") or "").strip()
            previous = str(item.get("Previous") or "").strip()
            extra_bits = []
            if forecast:
                extra_bits.append(f"Forecast: {forecast}")
            if previous:
                extra_bits.append(f"Previous: {previous}")
            note = reason
            if extra_bits:
                note = f"{reason} ({' | '.join(extra_bits)})"

            calendar_id = str(item.get("CalendarId", "")) or name

            events.append({
                "id": _stable_id("te", calendar_id),
                "name": name,
                "type": "ECON",
                "datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
                "note": note,
                "impact": impact,
                "impact_reason": reason,
                "source": "Trading Economics",
                "country": country or "United States",
                "currency": str(item.get("Currency") or "USD"),
            })
        except Exception as e:
            print(f"[economic_calendar] Skip 1 event Trading Economics karena error parse: {e}")
            continue

    return events


# ---------------------------------------------------------------------------
# 3. Federal Reserve - via RSS resmi (reaktif, dipakai utk /fednews)
# ---------------------------------------------------------------------------

def fetch_fed_press_releases(limit: int = 5) -> list[dict]:
    """Ambil rilis press release terbaru dari Federal Reserve via RSS resmi.

    Sifatnya REAKTIF (baru muncul setelah rilis terjadi), jadi ini TIDAK
    dipakai untuk notifikasi H-24/H-15 (yang butuh data forward-looking),
    melainkan untuk command /fednews supaya user bisa lihat rilis/statement
    terbaru dari The Fed kapan saja.
    """
    try:
        import feedparser
    except ImportError:
        print("[economic_calendar] Package 'feedparser' belum terinstall, skip fetch Fed RSS. "
              "Jalankan: pip install feedparser")
        return []

    try:
        feed = feedparser.parse(FED_RSS_URL)
    except Exception as e:
        print(f"[economic_calendar] Gagal ambil Fed RSS: {e}")
        return []

    if getattr(feed, "bozo", False) and not feed.entries:
        print(f"[economic_calendar] Fed RSS gagal di-parse: {getattr(feed, 'bozo_exception', 'unknown error')}")
        return []

    releases = []
    for entry in feed.entries[:limit]:
        releases.append({
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "summary": entry.get("summary", "").strip(),
        })
    return releases


# ---------------------------------------------------------------------------
# Gabungkan semua sumber
# ---------------------------------------------------------------------------

def get_combined_calendar_events(lookahead_days: int = 14, min_impact: str = "Medium") -> list[dict]:
    """Gabungkan hasil BLS + Trading Economics, filter berdasarkan level
    dampak minimum (default Medium, supaya event dampak Low tidak membanjiri
    notifikasi), dan kembalikan list event yang siap disimpan ke cache/DB.

    Dipanggil secara periodik oleh scheduler di bot.py (bukan di setiap
    pengecekan notifikasi), supaya tidak membebani API pihak ketiga.
    """
    impact_rank = {"Low": 0, "Medium": 1, "High": 2}
    min_rank = impact_rank.get(min_impact, 1)

    bls_events = fetch_bls_calendar(lookahead_days=lookahead_days)
    te_events = fetch_trading_economics_calendar(lookahead_days=lookahead_days)

    combined = bls_events + te_events
    filtered = [e for e in combined if impact_rank.get(e.get("impact", "Low"), 0) >= min_rank]

    filtered.sort(key=lambda e: e["datetime_utc"])
    return filtered
