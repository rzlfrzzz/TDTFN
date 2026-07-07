"""
Generate narasi peringatan pakai DeepSeek API (endpoint-nya compatible
dengan format OpenAI, jadi cukup pakai library `openai` tapi arahkan
base_url ke DeepSeek).

Kalau API gagal/timeout/limit, fallback ke template statis supaya bot
tetap kirim notifikasi (jangan sampai gagal total gara-gara AI down).

Semua output di sini dalam format HTML Telegram (bukan Markdown legacy),
karena:
1. Lebih stabil - Markdown legacy gampang error ("can't parse entities")
   kalau teks dari AI kebetulan mengandung karakter * atau _ yang tidak
   berpasangan.
2. Lebih gampang dibikin rapi (tabel angka rata kanan pakai <pre>, dsb).

Fungsi `_esc()` WAJIB dipakai untuk membungkus semua teks yang asalnya
dari luar (nama event, catatan event, output AI) sebelum disisipkan ke
template HTML, supaya karakter seperti < > & tidak merusak parsing.
"""

import html
from datetime import datetime, timezone

from openai import OpenAI, APIError, APITimeoutError

from config import DEEPSEEK_API_KEY

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")


def _esc(text) -> str:
    """Escape teks untuk aman disisipkan ke dalam parse_mode HTML Telegram."""
    return html.escape(str(text), quote=False)


DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

SYSTEM_PROMPT = (
    "Kamu adalah asisten yang menulis peringatan singkat untuk trader/investor "
    "di channel Telegram tentang event Federal Reserve (The Fed) yang akan "
    "datang. Gaya bahasa: santai tapi profesional, singkat, jelas, pakai "
    "Bahasa Indonesia. Fokus pada: apa eventnya, kenapa penting, dan "
    "reminder untuk hati-hati/manage risiko karena potensi volatilitas "
    "tinggi. JANGAN memberi rekomendasi trading/investasi spesifik "
    "(jangan bilang 'beli' atau 'jual'), cukup edukasi risiko. Maksimal "
    "5-6 kalimat. PENTING: tulis dalam teks polos saja, JANGAN pakai "
    "simbol markdown seperti **, __, ##, atau format list bernomor."
)


def _fallback_text(event_name: str, note: str, stage_label: str) -> str:
    return (
        f"⚠️ <b>Reminder: {_esc(event_name)}</b>\n"
        f"Akan berlangsung <b>{_esc(stage_label)}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_esc(note)}\n\n"
        "📌 Volatilitas market berpotensi tinggi di sekitar waktu ini. "
        "Selalu gunakan manajemen risiko (stop loss, position sizing) dan "
        "hindari over-leverage menjelang &amp; saat pengumuman."
    )


def generate_narrative(event_name: str, note: str, stage_label: str) -> str:
    """
    stage_label contoh: "24 jam lagi" atau "15 menit lagi"
    """
    user_prompt = (
        f"Buatkan pesan peringatan untuk channel Telegram tentang event berikut:\n"
        f"- Nama event: {event_name}\n"
        f"- Waktu tersisa: {stage_label}\n"
        f"- Keterangan tambahan: {note}\n"
    )
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.7,
            timeout=15,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            return _fallback_text(event_name, note, stage_label)
        return (
            f"⚠️ <b>Reminder: {_esc(event_name)}</b>\n"
            f"Akan berlangsung <b>{_esc(stage_label)}</b>\n"
            f"{DIVIDER}\n\n"
            f"{_esc(text)}"
        )
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal, pakai fallback. Error: {e}")
        return _fallback_text(event_name, note, stage_label)


# ---------------------------------------------------------------------------
# BTC daily insight (pagi WIB) - format terstruktur dengan AI insight
# ---------------------------------------------------------------------------

BTC_INSIGHT_PROMPT = (
    "Kamu adalah asisten trader berpengalaman. Buatkan analisis teknis singkat "
    "(3-4 kalimat) tentang kondisi BTC hari ini berdasarkan data yang diberikan. "
    "Gaya: santai tapi profesional, Bahasa Indonesia. Fokus: momentum (naik/turun/"
    "sideways), volume relatif terhadap market cap, dominance trend. "
    "JANGAN beri rekomendasi trading spesifik atau price target. "
    "Akhir dengan 1 kalimat bias harian (bullish/netral/bearish) + range harga "
    "perhatian (cukup range singkat, 2-3% dari harga saat ini). "
    "PENTING: tulis dalam teks polos saja, JANGAN pakai simbol markdown "
    "seperti **, __, ##, atau format list bernomor/bullet."
)


def format_number(num) -> str:
    """Format angka besar ke notasi singkat ($1.23T / $456.7M / dst)."""
    if num is None:
        return "N/A"
    if num >= 1e12:
        return f"${num / 1e12:.2f}T"
    elif num >= 1e9:
        return f"${num / 1e9:.2f}B"
    elif num >= 1e6:
        return f"${num / 1e6:.2f}M"
    elif num >= 1e3:
        return f"${num / 1e3:.2f}K"
    else:
        return f"${num:.2f}"


def _fg_label(value):
    """Label + emoji sentimen Fear & Greed Index berdasarkan nilai 0-100."""
    if value is None:
        return "N/A", "⚪️"
    if value <= 24:
        return "Extreme Fear", "🔴"
    if value <= 44:
        return "Fear", "🟠"
    if value <= 55:
        return "Neutral", "🟡"
    if value <= 75:
        return "Greed", "🟢"
    return "Extreme Greed", "🟢"


def _altcoin_label(value):
    """Label + emoji untuk Altcoin Season Index (0-100)."""
    if value is None:
        return "N/A", "⚪️"
    if value < 25:
        return "Bitcoin Season", "🟠"
    if value > 75:
        return "Altcoin Season", "🟢"
    return "Netral / Campuran", "🟡"


def _pct(value) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _num2(value) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _pad_row(label: str, value: str, label_width: int = 16) -> str:
    return f"{label.ljust(label_width)}{value}"


def _format_btc_metrics(snapshot: dict, timestamp_label: str = "") -> str:
    """Format metric BTC menjadi template HTML yang rapi & premium."""
    price = snapshot.get("price")
    change_24h = snapshot.get("change_24h")
    change_7d = snapshot.get("change_7d")
    change_30d = snapshot.get("change_30d")
    market_cap = snapshot.get("market_cap")
    volume_24h = snapshot.get("volume_24h")
    total_market_cap = snapshot.get("total_market_cap")
    total_volume_24h = snapshot.get("total_volume_24h")
    btc_dominance = snapshot.get("btc_dominance")
    eth_dominance = snapshot.get("eth_dominance")
    fear_greed = snapshot.get("fear_greed_value")
    altcoin_index = snapshot.get("altcoin_season_index")
    warnings = snapshot.get("data_warnings") or []

    price_str = f"${price:,.0f}" if price is not None else "N/A"

    btc_table = (
        "<pre>"
        + _pad_row("BTC", price_str) + "\n"
        + _pad_row("24H", _pct(change_24h)) + "\n"
        + _pad_row("7D", _pct(change_7d)) + "\n"
        + _pad_row("30D", _pct(change_30d)) + "\n"
        + _pad_row("Volume 24h", format_number(volume_24h)) + "\n"
        + _pad_row("Market Cap", format_number(market_cap))
        + "</pre>"
    )

    global_table = (
        "<pre>"
        + _pad_row("Total MCap", format_number(total_market_cap)) + "\n"
        + _pad_row("Total Vol 24h", format_number(total_volume_24h)) + "\n"
        + _pad_row("BTC Dominance", _num2(btc_dominance)) + "\n"
        + _pad_row("ETH Dominance", _num2(eth_dominance))
        + "</pre>"
    )

    fg_label, fg_emoji = _fg_label(fear_greed)
    fg_value_str = f"{fear_greed}/100" if fear_greed is not None else "N/A"

    alt_label, alt_emoji = _altcoin_label(altcoin_index)
    alt_value_str = f"{altcoin_index}/100" if altcoin_index is not None else "N/A"

    header = "📊 <b>DAILY BTC INSIGHT</b>"
    if timestamp_label:
        header += f"\n🕐 {_esc(timestamp_label)}"

    sections = [
        header,
        DIVIDER,
        "💰 <b>Bitcoin (BTC)</b>",
        btc_table,
        "",
        "🌍 <b>Kondisi Market Global</b>",
        global_table,
        "",
        "🧭 <b>Sentimen Market</b>",
        f"{fg_emoji} Fear &amp; Greed: <b>{fg_value_str}</b> ({_esc(fg_label)})",
        f"{alt_emoji} Altcoin Season: <b>{alt_value_str}</b> ({_esc(alt_label)})",
    ]

    if warnings:
        warn_list = ", ".join(_esc(w) for w in warnings)
        sections.append("")
        sections.append(f"⚠️ <i>Sebagian data tidak tersedia saat ini: {warn_list}.</i>")

    return "\n".join(sections)


def _btc_fallback_insight(snapshot: dict) -> str:
    """Fallback insight kalau AI gagal."""
    price = snapshot.get("price") or 0
    change_24h = snapshot.get("change_24h") or 0
    bias = "Bullish" if change_24h > 0 else "Bearish" if change_24h < -1 else "Netral"

    upper = price * 1.02
    lower = price * 0.98

    return (
        "Volume dan momentum menunjukkan kondisi pasar saat ini. Dominance BTC "
        "tetap kuat menandakan kepercayaan investor pada aset utama. Monitor "
        "pergerakan volume untuk konfirmasi arah selanjutnya.\n\n"
        f"📌 <b>Kesimpulan</b>\n"
        f"Bias harian: <b>{bias}</b>\n"
        f"Area perhatian: ${lower:,.0f} - ${upper:,.0f}"
    )


def generate_btc_insight(snapshot: dict, timestamp_label: str = "") -> str:
    """
    Format BTC insight dengan struktur:
    1. Metrics (harga, changes, volume, dominance, fear & greed) - tabel rapi
    2. AI-generated insight teknis
    3. Kesimpulan (bias + support/resistance range)

    snapshot: dict hasil dari market_data.fetch_market_snapshot()
    timestamp_label: string waktu (WIB) untuk ditampilkan di header, opsional.
    """
    metrics_text = _format_btc_metrics(snapshot, timestamp_label=timestamp_label)

    price = snapshot.get("price") or 0
    change_24h = snapshot.get("change_24h") or 0
    volume_24h = snapshot.get("volume_24h") or 0
    market_cap = snapshot.get("market_cap") or 0
    volume_to_mcap = snapshot.get("volume_to_market_cap") or 0
    btc_dominance = snapshot.get("btc_dominance")
    fear_greed = snapshot.get("fear_greed_value")

    fg_text = f"{fear_greed} / 100" if fear_greed is not None else "tidak tersedia saat ini"
    dominance_text = f"{btc_dominance:.2f}%" if btc_dominance is not None else "tidak tersedia saat ini"

    user_prompt = (
        "Data BTC hari ini:\n"
        f"- Harga: ${price:,.0f}\n"
        f"- Change 24h: {change_24h:+.2f}%\n"
        f"- Volume 24h: ${volume_24h:,.0f}\n"
        f"- Market Cap: ${market_cap:,.0f}\n"
        f"- Volume/Market Cap: {volume_to_mcap:.2f}%\n"
        f"- BTC Dominance: {dominance_text}\n"
        f"- Fear & Greed Index: {fg_text}\n\n"
        "Berdasarkan data ini, buatkan insight singkat tentang kondisi teknis BTC. "
        "Kesimpulan dengan bias harian + range support/resistance."
    )

    used_fallback = False
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BTC_INSIGHT_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.7,
            timeout=15,
        )
        insight_text = response.choices[0].message.content.strip()
        if not insight_text:
            insight_text = _btc_fallback_insight(snapshot)
            used_fallback = True
        else:
            insight_text = _esc(insight_text)
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal (BTC insight), pakai fallback. Error: {e}")
        insight_text = _btc_fallback_insight(snapshot)
        used_fallback = True

    footer = "<i>Sumber data: CoinMarketCap"
    footer += " • Analisis: template</i>" if used_fallback else " • Analisis: DeepSeek AI</i>"

    final_text = (
        f"{metrics_text}\n"
        f"{DIVIDER}\n"
        f"🧠 <b>AI Insight</b>\n"
        f"{insight_text}\n\n"
        f"{footer}"
    )
    return final_text
