# Economic Calendar & Fed Announcement Notifier Bot

Bot Telegram untuk kirim notifikasi otomatis **H-24 jam** dan **H-15 menit**
sebelum event ekonomi penting AS - FOMC/keputusan suku bunga The Fed, CPI,
Non-Farm Payrolls (Employment Situation), PPI, GDP, ISM PMI, Retail Sales,
dan lain-lain - lengkap dengan:

- **Analisa dampak ke USD** (🔴 Tinggi / 🟡 Sedang / 🟢 Rendah), dengan alasan
  singkat kenapa event itu berdampak besar/kecil ke Dolar AS.
- **Narasi AI dari DeepSeek** (opsional, ada fallback template kalau API-nya
  down) dengan format yang rapi & enak dibaca, tanpa markdown/emoji berlebihan.

Sekarang juga ada **insight harian BTC** tiap pagi jam 07:00 WIB.

## 1. Sumber Data Economic Calendar

Data diambil otomatis & digabung dari 3 sumber (lihat `economic_calendar.py`):

| Sumber | Dipakai untuk | Cara ambil |
|---|---|---|
| **BLS** (Bureau of Labor Statistics) | CPI, Employment Situation (NFP + unemployment rate), PPI, JOLTS, Employment Cost Index, Real Earnings, Import/Export Price Index, Productivity & Costs | ICS calendar resmi (`bls.gov/schedule/news_release/bls.ics`) - feed publik yang sama dipakai orang subscribe ke Outlook/Google Calendar, jadi presisi & resmi (bukan scraping HTML yang gampang rusak kalau layout berubah). |
| **Trading Economics** | Event ekonomi AS lainnya: GDP, Retail Sales, ISM Manufacturing/Services PMI, Consumer Confidence, Housing Starts, Durable Goods, PCE, Trade Balance, dll. | REST API (`api.tradingeconomics.com/calendar/...`). Field `Importance` (0/1/2) dipakai sebagai salah satu sinyal dampak. |
| **Federal Reserve** | Rilis press release/statement terbaru (dipakai di command `/fednews`) | RSS resmi (`federalreserve.gov/feeds/press_all.xml`). **Catatan**: RSS ini sifatnya reaktif (baru muncul setelah rilis terjadi), jadi TIDAK dipakai untuk notifikasi H-24/H-15 - untuk itu jadwal FOMC tetap manual (lihat di bawah). |

Event dari BLS & Trading Economics otomatis di-refresh tiap **6 jam sekali**
(bisa diatur lewat `CALENDAR_REFRESH_HOURS` di `.env`) dan disimpan ke cache
SQLite (`fedbot.db`), supaya tidak bolak-balik hit API pihak ketiga tiap kali
scheduler cek notifikasi.

⚠️ **Trading Economics API key**: kalau `TRADING_ECONOMICS_API_KEY` di `.env`
dikosongkan, bot pakai demo key publik `guest:guest` yang **hanya
mengembalikan data sample/terbatas**, bukan kalender penuh & real-time. Untuk
pemakaian serius, daftar API key sendiri gratis/berbayar di
[developer.tradingeconomics.com](https://developer.tradingeconomics.com/) lalu
isi ke `.env`.

### FOMC (tetap manual)

- **FOMC**: jadwal resmi dari `federalreserve.gov/monetarypolicy/fomccalendars.htm`.
  Fed mengumumkan 8 jadwal meeting untuk setahun penuh di awal tahun, jadi
  cukup diperbarui manual 1x/tahun di file `events.py`. Ini lebih stabil
  daripada mengandalkan API/scraping otomatis untuk event sepenting ini (gak
  akan tiba-tiba rusak kalau layout web Fed atau data pihak ketiga berubah).
  Data dari Trading Economics yang match dengan FOMC/keputusan suku bunga
  otomatis di-skip supaya tidak dobel notifikasi dengan daftar manual ini.
- **Event lain** (CPI, NFP, PPI, dll): otomatis dari BLS & Trading Economics
  seperti dijelaskan di atas. Kalau mau tambah event manual tambahan (mis.
  jadwal pidato Powell spesifik), tetap bisa ditambahkan ke `FED_EVENTS` di
  `events.py` dengan format yang sudah dicontohkan.
- ⚠️ **PENTING**: selalu double-check tanggal & jam terbaru langsung di
  federalreserve.gov sebelum event, karena jadwal kadang bisa berubah
  (meeting emergency, dll). Sama halnya, data forecast/actual dari Trading
  Economics guest key bisa terbatas/delayed - jangan jadikan satu-satunya
  acuan untuk keputusan trading.

### Level dampak ke USD

Tiap event diklasifikasikan **High / Medium / Low** berdasarkan kombinasi:
1. Daftar kurasi manual (`HIGH_IMPACT_INFO` / `MEDIUM_IMPACT_INFO` di
   `economic_calendar.py`) untuk indikator-indikator utama seperti CPI, NFP,
   FOMC, GDP, PPI, ISM PMI, dll - lengkap dengan penjelasan Bahasa Indonesia
   kenapa event itu berdampak ke USD.
2. Fallback ke field `Importance` dari Trading Economics kalau event-nya
   tidak ada di daftar kurasi manual.

Secara default hanya event dengan dampak **Medium ke atas** yang disimpan &
dinotifikasi (diatur lewat `CALENDAR_MIN_IMPACT` di `.env`), supaya
notifikasi tidak kebanjiran event-event kecil.

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

# Economic Calendar (opsional, ada default kalau dikosongkan)
TRADING_ECONOMICS_API_KEY=guest:guest
CALENDAR_COUNTRY=united states
CALENDAR_LOOKAHEAD_DAYS=14
CALENDAR_REFRESH_HOURS=6
CALENDAR_MIN_IMPACT=Medium
```

- `TELEGRAM_BOT_TOKEN`: dapatkan dari **@BotFather** di Telegram (`/newbot`).
- `DEEPSEEK_API_KEY`: API key DeepSeek yang sudah kamu punya.
- `COINMARKETCAP_API_KEY`: API key dari [coinmarketcap.com/api](https://coinmarketcap.com/api/)
  (daftar akun → dashboard → copy API key, tier Basic gratis sudah cukup).
- `BROADCAST_CHAT_ID` (opsional): kalau mau notifikasi otomatis dibroadcast
  ke channel/group tertentu (bukan cuma yang /subscribe personal), isi
  dengan chat ID channel-nya (bot harus jadi admin di channel itu). Kosongkan
  kalau tidak perlu.
- `TRADING_ECONOMICS_API_KEY` (opsional): API key dari
  [developer.tradingeconomics.com](https://developer.tradingeconomics.com/).
  Kalau dikosongkan, pakai demo key `guest:guest` (data sample/terbatas saja).
- `CALENDAR_COUNTRY` (opsional): negara yang dipantau untuk economic calendar,
  default `united states` (paling relevan untuk dampak ke USD).
- `CALENDAR_LOOKAHEAD_DAYS` (opsional): berapa hari ke depan yang di-fetch
  tiap refresh, default `14`.
- `CALENDAR_REFRESH_HOURS` (opsional): seberapa sering calendar di-refresh
  ulang dari API, default `6` jam.
- `CALENDAR_MIN_IMPACT` (opsional): level dampak minimum yang disimpan &
  dinotifikasi - `Low` / `Medium` / `High`, default `Medium`.

## 4. Menjalankan

```bash
python bot.py
```

Bot akan langsung polling & scheduler jalan di background (cek tiap 60 detik
apakah ada event yang jatuh tempo H-24 jam / H-15 menit).

## 5. Command yang tersedia di Telegram

- `/start` – info bot
- `/subscribe` – aktifkan notifikasi ke chat pribadi (economic calendar + BTC harian)
- `/unsubscribe` – matikan notifikasi
- `/status` – cek status subscribe
- `/next` – lihat event terdekat (FOMC / CPI / NFP / dll), lengkap dengan badge dampak ke USD
- `/calendar` – lihat semua event ekonomi mendatang (sampai ~12 event ke depan)
- `/fednews` – lihat rilis press release terbaru dari Federal Reserve (via RSS resmi)
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

## 7. Menambah event manual (FOMC/lainnya)

Event CPI, NFP, PPI, GDP, dll sudah otomatis dari BLS & Trading Economics -
tidak perlu ditambah manual. Kalau mau tambah event manual tambahan (mis.
jadwal FOMC tahun berikutnya, atau pidato Powell spesifik), edit `events.py`,
tambahkan dict baru ke list `FED_EVENTS`. Pastikan `id` unik dan
`datetime_utc` dalam format ISO UTC (`YYYY-MM-DDTHH:MM:SS`). Field `impact`,
`impact_reason`, dan `source` opsional tapi disarankan diisi supaya notifikasi
ikut menampilkan badge dampak ke USD.

## 8. Keterbatasan yang Perlu Diketahui

- **Trading Economics guest key**: kalau tidak diisi API key sendiri, data
  yang didapat dari Trading Economics sangat terbatas (sample data). Untuk
  cakupan calendar yang lebih lengkap & real-time, disarankan daftar API key
  sendiri.
- **Asumsi timezone Trading Economics**: field `Date` dari API TE diasumsikan
  UTC (umum di layanan calendar semacam ini). Kalau ternyata API key kamu
  mengembalikan waktu dalam timezone lain, sesuaikan parsing di
  `economic_calendar.py` fungsi `fetch_trading_economics_calendar`.
- **BLS ICS**: cukup andal karena ini feed resmi BLS untuk subscription
  calendar publik, tapi tetap ada kemungkinan (jarang) jadwal berubah
  mendadak - selalu ada baiknya cross-check ke bls.gov kalau ragu.
- **Fed RSS** (`/fednews`) sifatnya reaktif (baru muncul setelah rilis
  terjadi), jadi tidak dipakai untuk notifikasi H-24/H-15.
- Bot ini murni alat bantu informasi & bukan nasihat finansial. Selalu
  cross-check data penting ke sumber resmi sebelum mengambil keputusan
  trading.

## Catatan Keamanan

- Jangan commit file `.env` ke git (masukkan ke `.gitignore`).
- Jangan share `TELEGRAM_BOT_TOKEN` / `DEEPSEEK_API_KEY` / `COINMARKETCAP_API_KEY` /
  `TRADING_ECONOMICS_API_KEY` ke siapa pun.
