# Changelog - BTC Insight Format Update

## Perubahan yang Dilakukan

### 1. **Format Output BTC Insight Berubah** (`ai_narrative.py`)

**Sebelumnya:**
- Narasi panjang dari AI (5-6 kalimat)
- Format naratif yang terasa kaku

**Sekarang:**
- Format **terstruktur dengan metric-metric jelas**
- Template:
  ```
  📊 Daily BTC Insight
  
  BTC: $xx,xxx
  24h: +x.xx% | 7D: +x.xx% | 30D: -x.xx%
  Volume 24h: $xxB
  Market Cap BTC: $x.xxT
  
  🌍 Market Crypto
  Total Market Cap: $x.xxT
  Total Volume 24h: $xxB
  BTC Dominance: xx.xx%
  ETH Dominance: xx.xx%
  Fear & Greed: xx / 100
  Altcoin Season Index: xx / 100
  
  🧠 Insight:
  [Insight teknis singkat dari AI - 3-4 kalimat]
  
  📌 Kesimpulan:
  Bias harian: Bullish / Netral / Bearish
  Area perhatian: $xx,xxx - $xx,xxx
  ```

**Keuntungan:**
- Lebih mudah dibaca dan dipahami
- Metric jelas terlihat dengan format ringkas (K, M, B, T)
- AI hanya generate insight teknis (momentum, volume, dominance) bukan narasi panjang
- Fallback insight juga terstruktur rapi jika API AI gagal

### 2. **Jadwal Insight BTC Berubah** (`bot.py`)

**Sebelumnya:**
- Jam 16:00 ET (penutupan market New York)
- Timezone: `America/New_York` (EDT/EST)

**Sekarang:**
- Jam **07:00 WIB** (pagi Indonesia)
- Timezone: `Asia/Jakarta`

**Perubahan kode:**
```python
# Sebelum
NY_CLOSE_HOUR = 16
NY_CLOSE_MINUTE = 0
NY_TZ = ZoneInfo("America/New_York")
scheduler.add_job(
    btc_daily_insight,
    CronTrigger(hour=NY_CLOSE_HOUR, minute=NY_CLOSE_MINUTE, timezone=NY_TZ),
    args=[app],
)

# Sesudah
BTC_INSIGHT_HOUR = 7
BTC_INSIGHT_MINUTE = 0
WIB_TZ = ZoneInfo("Asia/Jakarta")
scheduler.add_job(
    btc_daily_insight,
    CronTrigger(hour=BTC_INSIGHT_HOUR, minute=BTC_INSIGHT_MINUTE, timezone=WIB_TZ),
    args=[app],
)
```

### 3. **Dokumentasi Diperbarui** (`README.md`)

- Section 2 (Fitur Insight BTC Harian) diperbarui
- Mencakup informasi jadwal baru (07:00 WIB)
- Menjelaskan format output baru dan komponen-komponennya

## File yang Berubah

1. ✅ `ai_narrative.py` - Refactored BTC insight generation
2. ✅ `bot.py` - Updated scheduler timezone dan timing
3. ✅ `requirements.txt` - Added httpx pinning untuk fix compatibility issue
4. ✅ `README.md` - Updated dokumentasi

## File yang TIDAK Berubah

- `config.py` - Tetap sama
- `database.py` - Tetap sama
- `market_data.py` - Tetap sama (sudah support fetch_market_snapshot untuk semua data)
- `events.py` - Tetap sama

## Testing

Setelah update, pastikan:

1. ✅ Bot tidak crash saat startup
2. ✅ BTC insight dikirim tepat jam 07:00 WIB
3. ✅ Format output sesuai template baru
4. ✅ Command `/btc` (on-demand) juga menggunakan format baru
5. ✅ Fallback insight muncul jika API AI gagal (tetap terstruktur)

## Cara Deploy

1. Update file-file yang berubah ke server/environment kamu
2. Jangan lupa update `requirements.txt`:
   ```bash
   pip install -r requirements.txt --force-reinstall
   ```
3. Restart bot:
   ```bash
   python bot.py
   ```

Bot akan mulai mengirim BTC insight dengan format baru mulai besok jam 07:00 WIB.
