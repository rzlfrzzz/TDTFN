"""
Generate narasi peringatan pakai DeepSeek API (endpoint-nya compatible
dengan format OpenAI, jadi cukup pakai library `openai` tapi arahkan
base_url ke DeepSeek).

Kalau API gagal/timeout/limit, fallback ke template statis supaya bot
tetap kirim notifikasi (jangan sampai gagal total gara-gara AI down).
"""

from openai import OpenAI, APIError, APITimeoutError

from config import DEEPSEEK_API_KEY

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

SYSTEM_PROMPT = (
    "Kamu adalah asisten yang menulis peringatan singkat untuk trader/investor "
    "di channel Telegram tentang event Federal Reserve (The Fed) yang akan "
    "datang. Gaya bahasa: santai tapi profesional, singkat, jelas, pakai "
    "Bahasa Indonesia. Fokus pada: apa eventnya, kenapa penting, dan "
    "reminder untuk hati-hati/manage risiko karena potensi volatilitas "
    "tinggi. JANGAN memberi rekomendasi trading/investasi spesifik "
    "(jangan bilang 'beli' atau 'jual'), cukup edukasi risiko. Maksimal "
    "5-6 kalimat."
)


def _fallback_text(event_name: str, note: str, stage_label: str) -> str:
    return (
        f"⚠️ *Reminder: {event_name}* akan berlangsung {stage_label}.\n\n"
        f"{note}\n\n"
        "Volatilitas market berpotensi tinggi di sekitar waktu ini. "
        "Selalu gunakan manajemen risiko (stop loss, position sizing) dan "
        "hindari over-leverage menjelang & saat pengumuman."
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
        return text if text else _fallback_text(event_name, note, stage_label)
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal, pakai fallback. Error: {e}")
        return _fallback_text(event_name, note, stage_label)


# ---------------------------------------------------------------------------
# BTC daily insight (penutupan NY market)
# ---------------------------------------------------------------------------

BTC_SYSTEM_PROMPT = (
    "Kamu adalah asisten yang menulis insight harian singkat tentang harga "
    "Bitcoin (BTC) untuk channel Telegram trader/investor, dikirim setiap "
    "penutupan market NY. Gaya bahasa: santai tapi profesional, singkat, "
    "jelas, pakai Bahasa Indonesia. Fokus pada: pergerakan harga hari ini, "
    "konteks singkat (naik/turun/sideways, momentum, likuiditas), dan "
    "reminder umum soal manajemen risiko. JANGAN memberi rekomendasi "
    "trading/investasi spesifik (jangan bilang 'beli' atau 'jual', jangan "
    "kasih target harga/price target), cukup edukasi & insight. Maksimal "
    "5-6 kalimat."
)


def _btc_fallback_text(snapshot: dict) -> str:
    arrow = "📈" if snapshot["change_24h"] >= 0 else "📉"
    return (
        f"{arrow} *BTC Update - Penutupan NY Market*\n\n"
        f"Harga: ${snapshot['price']:,.2f}\n"
        f"Perubahan 24 jam: {snapshot['change_24h']:+.2f}%\n"
        f"Perubahan 7 hari: {snapshot['change_7d']:+.2f}%\n\n"
        "Selalu gunakan manajemen risiko dan hindari FOMO mengikuti "
        "pergerakan harga jangka pendek."
    )


def generate_btc_insight(snapshot: dict) -> str:
    """
    snapshot: dict hasil dari market_data.fetch_btc_snapshot()
    """
    user_prompt = (
        "Buatkan insight harian BTC untuk channel Telegram berdasarkan data "
        "berikut (waktu: penutupan NY market):\n"
        f"- Harga saat ini: ${snapshot['price']:,.2f}\n"
        f"- Perubahan 1 jam: {snapshot['change_1h']:+.2f}%\n"
        f"- Perubahan 24 jam: {snapshot['change_24h']:+.2f}%\n"
        f"- Perubahan 7 hari: {snapshot['change_7d']:+.2f}%\n"
        f"- Market cap: ${snapshot['market_cap']:,.0f}\n"
        f"- Volume 24 jam: ${snapshot['volume_24h']:,.0f}\n"
    )
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BTC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.7,
            timeout=15,
        )
        text = response.choices[0].message.content.strip()
        return text if text else _btc_fallback_text(snapshot)
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal (BTC insight), pakai fallback. Error: {e}")
        return _btc_fallback_text(snapshot)
