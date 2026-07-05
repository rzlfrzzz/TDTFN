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
# BTC daily insight (pagi WIB) - format terstruktur dengan AI insight
# ---------------------------------------------------------------------------

BTC_INSIGHT_PROMPT = (
    "Kamu adalah asisten trader berpengalaman. Buatkan analisis teknis singkat "
    "(3-4 kalimat) tentang kondisi BTC hari ini berdasarkan data yang diberikan. "
    "Gaya: santai tapi profesional, Bahasa Indonesia. Fokus: momentum (naik/turun/"
    "sideways), volume relatif terhadap market cap, dominance trend. "
    "JANGAN beri rekomendasi trading spesifik atau price target. "
    "Akhir dengan 1 kalimat bias harian (bullish/netral/bearish) + range harga "
    "perhatian (cukup range singkat, 2-3% dari harga saat ini)."
)


def _format_btc_metrics(snapshot: dict) -> str:
    """Format metric BTC menjadi template yang rapi."""
    price = snapshot.get("price", 0)
    change_24h = snapshot.get("change_24h", 0)
    change_7d = snapshot.get("change_7d", 0)
    change_30d = snapshot.get("change_30d", 0)
    market_cap = snapshot.get("market_cap", 0)
    volume_24h = snapshot.get("volume_24h", 0)
    total_market_cap = snapshot.get("total_market_cap", 0)
    total_volume_24h = snapshot.get("total_volume_24h", 0)
    btc_dominance = snapshot.get("btc_dominance", 0)
    eth_dominance = snapshot.get("eth_dominance", 0)
    fear_greed = snapshot.get("fear_greed_value", 0)
    altcoin_index = snapshot.get("altcoin_season_index", 0)

    # Format harga & market cap ke angka singkat (K, M, B, T)
    def format_number(num):
        if num >= 1e12:
            return f"${num/1e12:.2f}T"
        elif num >= 1e9:
            return f"${num/1e9:.2f}B"
        elif num >= 1e6:
            return f"${num/1e6:.2f}M"
        elif num >= 1e3:
            return f"${num/1e3:.2f}K"
        else:
            return f"${num:.2f}"

    metrics = (
        "📊 *Daily BTC Insight*\n\n"
        f"*BTC:* ${price:,.0f}\n"
        f"24h: {change_24h:+.2f}% | 7D: {change_7d:+.2f}% | 30D: {change_30d:+.2f}%\n"
        f"Volume 24h: {format_number(volume_24h)}\n"
        f"Market Cap BTC: {format_number(market_cap)}\n\n"
        f"🌍 *Market Crypto*\n"
        f"Total Market Cap: {format_number(total_market_cap)}\n"
        f"Total Volume 24h: {format_number(total_volume_24h)}\n"
        f"BTC Dominance: {btc_dominance:.2f}%\n"
        f"ETH Dominance: {eth_dominance:.2f}%\n"
        f"Fear & Greed: {fear_greed} / 100\n"
        f"Altcoin Season Index: {altcoin_index} / 100\n"
    )
    return metrics


def _btc_fallback_insight(snapshot: dict) -> str:
    """Fallback insight kalau AI gagal."""
    price = snapshot.get("price", 0)
    change_24h = snapshot.get("change_24h", 0)
    bias = "Bullish" if change_24h > 0 else "Bearish" if change_24h < -1 else "Netral"
    
    upper = price * 1.02
    lower = price * 0.98
    
    return (
        f"Volume dan momentum menunjukkan kondisi pasar saat ini. Dominance BTC "
        f"tetap kuat menandakan kepercayaan investor pada aset utama. Monitor "
        f"pergerakan volume untuk konfirmasi arah selanjutnya.\n\n"
        f"📌 *Kesimpulan:*\n"
        f"Bias harian: {bias}\n"
        f"Area perhatian: ${lower:,.0f} - ${upper:,.0f}"
    )


def generate_btc_insight(snapshot: dict) -> str:
    """
    Format BTC insight dengan struktur:
    1. Metrics (harga, changes, volume, dominance, fear & greed)
    2. AI-generated insight teknis
    3. Kesimpulan (bias + support/resistance range)
    
    snapshot: dict hasil dari market_data.fetch_market_snapshot()
    """
    metrics_text = _format_btc_metrics(snapshot)
    
    # Prepare data untuk AI
    price = snapshot.get("price", 0)
    change_24h = snapshot.get("change_24h", 0)
    volume_24h = snapshot.get("volume_24h", 0)
    market_cap = snapshot.get("market_cap", 0)
    volume_to_mcap = snapshot.get("volume_to_market_cap", 0)
    btc_dominance = snapshot.get("btc_dominance", 0)
    fear_greed = snapshot.get("fear_greed_value", 0)
    
    user_prompt = (
        "Data BTC hari ini:\n"
        f"- Harga: ${price:,.0f}\n"
        f"- Change 24h: {change_24h:+.2f}%\n"
        f"- Volume 24h: ${volume_24h:,.0f}\n"
        f"- Market Cap: ${market_cap:,.0f}\n"
        f"- Volume/Market Cap: {volume_to_mcap:.2f}%\n"
        f"- BTC Dominance: {btc_dominance:.2f}%\n"
        f"- Fear & Greed Index: {fear_greed} / 100\n\n"
        "Berdasarkan data ini, buatkan insight singkat tentang kondisi teknis BTC. "
        "Kesimpulan dengan bias harian + range support/resistance."
    )
    
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
    except (APIError, APITimeoutError, Exception) as e:
        print(f"[ai_narrative] DeepSeek API gagal (BTC insight), pakai fallback. Error: {e}")
        insight_text = _btc_fallback_insight(snapshot)
    
    # Combine metrics + insight
    final_text = f"{metrics_text}\n🧠 *Insight:*\n{insight_text}"
    return final_text
