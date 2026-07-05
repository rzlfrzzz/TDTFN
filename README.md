# Fed Announcement Notifier Bot

Bot Telegram untuk kirim notifikasi otomatis **H-24 jam** dan **H-15 menit**
sebelum pengumuman The Fed (FOMC, dll), lengkap dengan narasi AI dari
DeepSeek (opsional, ada fallback kalau API-nya down). Sekarang juga ada
**insight harian BTC** tiap penutupan NY market.

## 1. Sumber Data Jadwal

- **FOMC**: jadwal resmi dari `federalreserve.gov/monetarypolicy/fomccalendars.htm`.
  Fed mengumumkan 8 jadwal meeting untuk setahun penuh di awal tahun, jadi
  cukup diperbarui manual 1x/tahun di file `events.py`. Ini lebih stabil
  daripada scraping otomatis (gak akan tiba-tiba rusak kalau layout web Fed
  berubah).
- **Event lain** (CPI, NFP, pidato Powell, dll): tambahkan manual ke list
  `FED_EVENTS` di `events.py` dengan format yang sudah dicontohkan. Kalau
  nanti mau full-otomatis, bisa integrasikan API economic calendar seperti
  Finnhub (`/calendar/economic`) atau Trading Economics.
- ⚠️ **PENTING**: selalu double-check tanggal & jam terbaru langsung di
  federalreserve.gov sebelum event, karena jadwal kadang bisa berubah
  (meeting emergency, dll).

## 2. Fitur Insight BTC Harian

Setiap hari jam **07:00 WIB** (pagi Indonesia), bot akan:

1. Ambil data BTC lengkap dari CoinMarketCap (harga, changes, volume, market cap, dominance, Fear & Greed Index, Altcoin Season Index).
2. Format ke template terstruktur dengan semua metric utama.
3. Minta DeepSeek bikin insight teknis singkat (analisis momentum, volume, dominance trend) dalam Bahasa Indonesia.
4. Broadcast ke subscriber yang sama dengan notifikasi Fed (jadi kalau `/subscribe`, otomatis dapat notif Fed **dan** BTC).

Format output mencakup:
- 📊 Harga BTC & perubahan (24h, 7D, 30D)
- Volume & Market Cap
- 🌍 Data global crypto (total market cap, dominance BTC/ETH, Fear & Greed Index)
- 🧠 Insight teknis dari AI
- 📌 Kesimpulan (bias harian + area perhatian harga)

Bisa juga dicek kapan saja lewat command `/btc` (on-demand, tidak perlu subscribe).

Sumber data: **CMC Pro API resmi** (`pro-api.coinmarketcap.com`), butuh API
key gratis dari [coinmarketcap.com/api](https://coinmarketcap.com/api/)
(tier Basic gratis, cukup untuk basic usage seperti ini — sekali fetch per
hari + on-demand lewat `/btc`). Isi ke `COINMARKETCAP_API_KEY` di `.env`.

Kalau `COINMARKETCAP_API_KEY` kosong / key-nya invalid / kena rate limit,
bot **skip** notifikasi BTC hari itu saja (log warning muncul di console,
tidak crash, tidak kirim data kosong/salah).

## 3. Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Buat file .env di folder yang sama (atau set environment variable manual)
```

Isi file `.env`:
```
TELEGRAM_BOT_TOKEN=123456:ABC-token-dari-BotFather
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx
COINMARKETCAP_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
BROADCAST_CHAT_ID=
```

- `TELEGRAM_BOT_TOKEN`: dapatkan dari **@BotFather** di Telegram (`/newbot`).
- `DEEPSEEK_API_KEY`: API key DeepSeek yang sudah kamu punya.
- `COINMARKETCAP_API_KEY`: API key dari [coinmarketcap.com/api](https://coinmarketcap.com/api/)
  (daftar akun → dashboard → copy API key, tier Basic gratis sudah cukup).
- `BROADCAST_CHAT_ID` (opsional): kalau mau notifikasi otomatis dibroadcast
  ke channel/group tertentu (bukan cuma yang /subscribe personal), isi
  dengan chat ID channel-nya (bot harus jadi admin di channel itu). Kosongkan
  kalau tidak perlu.

## 4. Menjalankan

```bash
python bot.py
```

Bot akan langsung polling & scheduler jalan di background (cek tiap 60 detik
apakah ada event yang jatuh tempo H-24 jam / H-15 menit).

## 5. Command yang tersedia di Telegram

- `/start` – info bot
- `/subscribe` – aktifkan notifikasi ke chat pribadi (Fed + BTC harian)
- `/unsubscribe` – matikan notifikasi
- `/status` – cek status subscribe
- `/next` – lihat event Fed terdekat
- `/btc` – lihat insight BTC saat ini (on-demand, tidak perlu subscribe)

## 6. Deploy 24/7

Supaya notifikasi jalan terus-menerus, bot ini perlu jalan 24/7 di server,
bukan cuma di laptop kamu. Opsi murah/gampang:
- VPS kecil (misal Contabo, Vultr, DigitalOcean) + `screen`/`tmux` atau
  `systemd` service
- Railway.app / Render.com (ada free tier, tinggal push repo)
- Docker + VPS mana saja

Kalau proses mati (restart server dll), tinggal `python bot.py` lagi —
data subscriber & histori notifikasi aman tersimpan di `fedbot.db`
(SQLite), jadi tidak akan kirim notifikasi dobel untuk event yang sama.

## 7. Menambah event baru

Edit `events.py`, tambahkan dict baru ke list `FED_EVENTS`. Pastikan `id`
unik dan `datetime_utc` dalam format ISO UTC (`YYYY-MM-DDTHH:MM:SS`).

## Catatan Keamanan

- Jangan commit file `.env` ke git (masukkan ke `.gitignore`).
- Jangan share `TELEGRAM_BOT_TOKEN` / `DEEPSEEK_API_KEY` / `COINMARKETCAP_API_KEY` ke siapa pun.
