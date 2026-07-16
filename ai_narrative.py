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
    "di channel Telegram tentang event ekonomi (Federal Reserve, rilis data "
    "ekonomi AS seperti CPI/NFP/PPI/GDP, dll) yang akan datang. Gaya bahasa: "
    "santai tapi profesional, singkat, jelas, pakai Bahasa Indonesia, terasa "
    "rapi & enak dibaca tapi TIDAK norak/berlebihan (hindari huruf kapital "
    "semua, tanda seru bertumpuk, atau emoji berlebihan). "
    "Fokus pada 3 hal secara ringkas: "
    "(1) apa event ini & apa yang diukur/diumumkan, "
    "(2) kenapa event ini bisa berdampak ke Dolar AS (USD) - jelaskan "
    "mekanismenya secara singkat berdasarkan konteks dampak yang diberikan "
    "(mis. kaitannya dengan ekspektasi kebijakan suku bunga The Fed), "
    "(3) reminder singkat untuk waspada terhadap potensi volatilitas & "
    "manajemen risiko. JANGAN memberi rekomendasi trading/investasi spesifik "
    "(jangan bilang 'beli' atau 'jual', jangan kasih target harga). Maksimal "
    "5-6 kalimat. PENTING: tulis dalam teks polos saja, JANGAN pakai simbol "
    "markdown seperti **, __, ##, atau format list bernomor/bullet."
)

IMPACT_BADGES = {
    "High": "🔴 Tinggi",
    "Medium": "🟡 Sedang",
    "Low": "🟢 Rendah",
}

IMPACT_LABELS_ID = {
    "High": "Tinggi",
    "Medium": "Sedang",
    "Low": "Rendah",
}


def _impact_line(impact: str | None) -> str:
    """Format baris badge dampak, contoh: '🔴 Dampak ke USD: Tinggi'."""
    if not impact:
        return ""
    emoji = IMPACT_BADGES.get(impact, "⚪️").split(" ")[0]
    label = IMPACT_LABELS_ID.get(impact, impact)
    return f"{emoji} Dampak ke USD: <b>{label}</b>"


def _fallback_text(event: dict, stage_label: str) -> str:
    event_name = event.get("name", "")
    note = event.get("note") or event.get("impact_reason", "")
    impact = event.get("impact")
    source = event.get("source", "")

    lines = [
        f"⚠️ <b>{_esc(event_name)}</b>",
        f"⏰ Akan berlangsung <b>{_esc(stage_label)}</b>",
    ]
    if impact:
        lines.append(_impact_line(impact))
    lines.append(DIVIDER)
    lines.append("")
    lines.append(_esc(note))
    lines.append("")
    lines.append(
        "📌 Volatilitas market berpotensi tinggi di sekitar waktu ini. "
        "Selalu gunakan manajemen risiko (stop loss, position sizing) dan "
        "hindari over-leverage menjelang &amp; saat pengumuman."
    )
    if source:
        lines.append("")
        lines.append(f"<i>Sumber: {_esc(source)}</i>")
    return "\n".join(lines)


def generate_narrative(event: dict, stage_label: str) -> str:
    """
    Generate pesan notifikasi H-24 jam / H-15 menit untuk sebuah event.

    event: dict dengan minimal key "name". Key opsional yang dimanfaatkan
        kalau ada: "note", "impact" ("High"/"Medium"/"Low"), "impact_reason",
        "source".
    stage_label contoh: "24 jam lagi" atau "15 menit lagi"
    """
    event_name = event.get("name", "")
    note = event.get("note") or event.get("impact_reason", "")
    impact = event.get("impact")
    impact_reason = event.get("impact_reason", "")
    source = event.get("source", "")

    prompt_lines = [
        "Buatkan pesan peringatan untuk channel Telegram tentang event berikut:",
        f"- Nama event: {event_name}",
        f"- Waktu tersisa: {stage_label}",
    ]
    if impact:
        prompt_lines.append(f"- Level dampak ke USD: {impact}")
    if impact_reason:
        prompt_lines.append(f"- Konteks/alasan dampak ke USD: {impact_reason}")
    if note and note != impact_reason:
        prompt_lines.append(f"- Keterangan tambahan: {note}")
    user_prompt = "\n".join(prompt_lines)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=350,
            temperature=0.7,
            timeout=15,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            return _fallback_text(event, stage_label)

        header_lines = [
            f"⚠️ <b>{_esc(event_name)}</b>",
            f"⏰ Akan berlangsung <b>{_esc(stage_label)}</b>",
        ]
        if impact:
            header_lines.append(_impact_line(impact))

        footer = f"\n\n<i>Sumber: {_esc(source)}</i>" if source else ""

        return (
            f"{chr(10).join(header_lines)}\n"
            f"{DIVIDER}\n\n"
            f"{_esc(text)}"
            f"{footer}"
        )
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal, pakai fallback. Error: {e}")
        return _fallback_text(event, stage_label)


# ---------------------------------------------------------------------------
# BTC daily insight (pagi WIB) - format terstruktur dengan AI insight
# ---------------------------------------------------------------------------

BTC_INSIGHT_PROMPT = (
    "Kamu adalah asisten trader berpengalaman yang menulis insight pagi harian "
    "untuk channel Telegram. Gaya: santai tapi profesional, Bahasa Indonesia, "
    "TIDAK norak/berlebihan (hindari huruf kapital semua, tanda seru bertumpuk, "
    "emoji berlebihan). Tulis 4-6 kalimat.\n\n"
    "Data yang diberikan bisa berisi beberapa bagian (tidak semua selalu ada, "
    "sesuaikan narasi dengan apa yang tersedia hari itu):\n"
    "1. Data BTC hari ini (harga, change, volume, dominance, fear&greed) - WAJIB dibahas.\n"
    "2. Perbandingan dengan kemarin (kalau ada) - sebutkan TRENnya (menguat/melemah/"
    "stabil dibanding kemarin), jangan cuma ulang angka mentah.\n"
    "3. Top gainers/losers 24h dari coin-coin besar (kalau ada) - singgung singkat "
    "kalau ada yang menonjol, ini indikasi rotasi minat pasar.\n"
    "4. Event ekonomi AS yang akan rilis dalam waktu dekat (kalau ada) - kaitkan "
    "sepintas kalau relevan (mis. pasar cenderung wait-and-see menjelang rilis besar).\n\n"
    "PENTING supaya insight tidak monoton dari hari ke hari: JANGAN selalu pakai "
    "struktur kalimat & urutan pembahasan yang sama persis setiap hari - variasikan "
    "sudut pandang tergantung data mana yang paling menonjol/relevan hari itu. "
    "JANGAN beri rekomendasi trading spesifik (jangan bilang 'beli'/'jual') atau "
    "price target pasti. Akhir dengan 1 kalimat bias harian (bullish/netral/bearish) "
    "+ range harga perhatian (2-3% dari harga saat ini). "
    "PENTING: tulis dalam teks polos saja, JANGAN pakai simbol markdown seperti "
    "**, __, ##, atau format list bernomor/bullet."
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


def _delta_arrow(current, previous, higher_is_up: bool = True) -> str:
    """Panah tren dibanding kemarin. Return string kosong kalau salah satu
    data tidak tersedia (bukan dipaksa tampil 'N/A' biar tidak berisik)."""
    if current is None or previous is None:
        return ""
    diff = current - previous
    if abs(diff) < 1e-9:
        return " →"
    arrow = "▲" if diff > 0 else "▼"
    if not higher_is_up:
        arrow = "▼" if diff > 0 else "▲"
    return f" {arrow}"


def _format_top_movers(snapshot: dict) -> str:
    """Format tabel top gainers & losers 24h, atau string kosong kalau
    datanya tidak ada/gagal fetch (biar section-nya tidak muncul kosong)."""
    gainers = snapshot.get("top_gainers") or []
    losers = snapshot.get("top_losers") or []
    if not gainers and not losers:
        return ""

    lines = ["", "🔥 <b>Top Movers 24h</b> <i>(top 200 by mcap)</i>"]
    if gainers:
        g_str = "  ".join(f"{c['symbol']} {_pct(c['change_24h'])}" for c in gainers[:5])
        lines.append(f"📈 {_esc(g_str)}")
    if losers:
        l_str = "  ".join(f"{c['symbol']} {_pct(c['change_24h'])}" for c in losers[:5])
        lines.append(f"📉 {_esc(l_str)}")
    return "\n".join(lines)


def _format_upcoming_events(upcoming_events: list[dict] | None) -> str:
    """Format ringkasan event ekonomi yang akan rilis dalam waktu dekat,
    atau string kosong kalau tidak ada event relevan."""
    if not upcoming_events:
        return ""

    from events import get_event_dt  # local import biar tidak circular di module load

    lines = ["", "📅 <b>Event Ekonomi Mendatang</b>"]
    for event in upcoming_events[:3]:
        dt = get_event_dt(event)
        impact = event.get("impact")
        badge = IMPACT_BADGES.get(impact, "⚪️").split(" ")[0] if impact else "⚪️"
        name = _esc(event.get("name", ""))
        lines.append(f"{badge} {name} — {dt.strftime('%d %b, %H:%M UTC')}")
    return "\n".join(lines)


def _format_btc_metrics(
    snapshot: dict,
    timestamp_label: str = "",
    previous_snapshot: dict | None = None,
    upcoming_events: list[dict] | None = None,
) -> str:
    """Format metric BTC menjadi template HTML yang rapi & premium.

    previous_snapshot (opsional): snapshot kemarin, dipakai untuk kasih
    panah tren (▲/▼) di sebelah fear&greed dan dominance supaya kelihatan
    arah perubahannya, bukan cuma angka absolut.
    """
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

    prev = previous_snapshot or {}
    price_arrow = _delta_arrow(price, prev.get("price"))
    fg_arrow = _delta_arrow(fear_greed, prev.get("fear_greed_value"))
    dom_arrow = _delta_arrow(btc_dominance, prev.get("btc_dominance"))

    price_str = f"${price:,.0f}" if price is not None else "N/A"

    btc_table = (
        "<pre>"
        + _pad_row("BTC", price_str + price_arrow) + "\n"
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
        + _pad_row("BTC Dominance", _num2(btc_dominance) + dom_arrow) + "\n"
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
        f"{fg_emoji} Fear &amp; Greed: <b>{fg_value_str}{fg_arrow}</b> ({_esc(fg_label)})",
        f"{alt_emoji} Altcoin Season: <b>{alt_value_str}</b> ({_esc(alt_label)})",
    ]

    movers_block = _format_top_movers(snapshot)
    if movers_block:
        sections.append(movers_block)

    events_block = _format_upcoming_events(upcoming_events)
    if events_block:
        sections.append(events_block)

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


def generate_btc_insight(
    snapshot: dict,
    timestamp_label: str = "",
    previous_snapshot: dict | None = None,
    upcoming_events: list[dict] | None = None,
) -> str:
    """
    Format BTC insight dengan struktur:
    1. Metrics (harga, changes, volume, dominance, fear & greed) - tabel rapi,
       lengkap dengan panah tren vs kemarin kalau ada histori
    2. Top gainers/losers 24h (kalau datanya ada)
    3. Event ekonomi AS yang akan datang (kalau ada dalam waktu dekat)
    4. AI-generated insight yang meracik semua konteks di atas jadi narasi
    5. Kesimpulan (bias + support/resistance range)

    snapshot: dict hasil dari market_data.fetch_market_snapshot()
    timestamp_label: string waktu (WIB) untuk ditampilkan di header, opsional.
    previous_snapshot: dict hasil database.get_btc_snapshot_before(), opsional -
        kalau ada, dipakai untuk narasi "vs kemarin" (bukan cuma tampilan panah).
    upcoming_events: list event dari events.get_upcoming_events(), sudah
        difilter ke rentang waktu dekat (mis. 36 jam) oleh caller, opsional.
    """
    metrics_text = _format_btc_metrics(
        snapshot,
        timestamp_label=timestamp_label,
        previous_snapshot=previous_snapshot,
        upcoming_events=upcoming_events,
    )

    price = snapshot.get("price") or 0
    change_24h = snapshot.get("change_24h") or 0
    volume_24h = snapshot.get("volume_24h") or 0
    market_cap = snapshot.get("market_cap") or 0
    volume_to_mcap = snapshot.get("volume_to_market_cap") or 0
    btc_dominance = snapshot.get("btc_dominance")
    fear_greed = snapshot.get("fear_greed_value")

    fg_text = f"{fear_greed} / 100" if fear_greed is not None else "tidak tersedia saat ini"
    dominance_text = f"{btc_dominance:.2f}%" if btc_dominance is not None else "tidak tersedia saat ini"

    prompt_parts = [
        "Data BTC hari ini:",
        f"- Harga: ${price:,.0f}",
        f"- Change 24h: {change_24h:+.2f}%",
        f"- Volume 24h: ${volume_24h:,.0f}",
        f"- Market Cap: ${market_cap:,.0f}",
        f"- Volume/Market Cap: {volume_to_mcap:.2f}%",
        f"- BTC Dominance: {dominance_text}",
        f"- Fear & Greed Index: {fg_text}",
    ]

    if previous_snapshot:
        prev_price = previous_snapshot.get("price")
        prev_fg = previous_snapshot.get("fear_greed_value")
        prev_dom = previous_snapshot.get("btc_dominance")
        comp_lines = ["", "Perbandingan dengan kemarin:"]
        if prev_price is not None:
            price_change_pct = ((price - prev_price) / prev_price * 100) if prev_price else 0
            comp_lines.append(f"- Harga kemarin: ${prev_price:,.0f} (selisih {price_change_pct:+.2f}%)")
        if prev_fg is not None and fear_greed is not None:
            comp_lines.append(f"- Fear & Greed kemarin: {prev_fg}/100 (sekarang {fear_greed}/100)")
        if prev_dom is not None and btc_dominance is not None:
            comp_lines.append(f"- BTC Dominance kemarin: {prev_dom:.2f}% (sekarang {btc_dominance:.2f}%)")
        if len(comp_lines) > 2:
            prompt_parts.extend(comp_lines)

    gainers = snapshot.get("top_gainers") or []
    losers = snapshot.get("top_losers") or []
    if gainers or losers:
        prompt_parts.append("")
        prompt_parts.append("Top movers 24h (dari top 200 coin by market cap):")
        if gainers:
            g_str = ", ".join(f"{c['symbol']} {c['change_24h']:+.1f}%" for c in gainers[:5])
            prompt_parts.append(f"- Top gainers: {g_str}")
        if losers:
            l_str = ", ".join(f"{c['symbol']} {c['change_24h']:+.1f}%" for c in losers[:5])
            prompt_parts.append(f"- Top losers: {l_str}")

    if upcoming_events:
        prompt_parts.append("")
        prompt_parts.append("Event ekonomi AS yang akan rilis dalam waktu dekat:")
        for event in upcoming_events[:3]:
            name = event.get("name", "")
            impact = event.get("impact", "")
            prompt_parts.append(f"- {name} (dampak ke USD: {impact})")

    prompt_parts.append("")
    prompt_parts.append(
        "Berdasarkan semua data di atas, buatkan insight singkat tentang kondisi "
        "BTC hari ini. Kesimpulan dengan bias harian + range support/resistance."
    )
    user_prompt = "\n".join(prompt_parts)

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
