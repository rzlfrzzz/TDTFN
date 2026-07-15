"""
Config diambil dari environment variables supaya API key/token TIDAK
ditulis langsung di kode (aman kalau mau push ke GitHub misalnya).

Cara set (Linux/Mac):
    export TELEGRAM_BOT_TOKEN="123456:ABC-your-token"
    export DEEPSEEK_API_KEY="sk-xxxxxxxx"
    export COINMARKETCAP_API_KEY="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

Cara set (Windows PowerShell):
    $env:TELEGRAM_BOT_TOKEN="123456:ABC-your-token"
    $env:DEEPSEEK_API_KEY="sk-xxxxxxxx"
    $env:COINMARKETCAP_API_KEY="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

Atau paling gampang: pakai file .env (lihat README untuk instruksi).
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv opsional, kalau tidak ada ya pakai env var biasa

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY", "")

# Channel/group id tempat notifikasi broadcast dikirim (opsional).
# Kalau diisi, bot akan kirim ke channel ini SELAIN ke semua subscriber personal.
# Contoh: "-1001234567890" (id channel/group, harus bot jadi admin di sana)
BROADCAST_CHAT_ID = os.getenv("BROADCAST_CHAT_ID", "")

# --- Economic Calendar (Trading Economics + BLS + Fed RSS) ---
#
# Trading Economics API key. Kalau kosong, pakai key demo publik
# "guest:guest" yang HANYA mengembalikan data sample/terbatas (bukan
# kalender penuh & bukan real-time). Untuk pemakaian serius, daftar API key
# sendiri di https://developer.tradingeconomics.com/ lalu isi di .env.
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "guest:guest")

# Negara yang dipantau untuk economic calendar (dampak ke USD -> "united states").
CALENDAR_COUNTRY = os.getenv("CALENDAR_COUNTRY", "united states")

# Berapa hari ke depan yang di-fetch tiap kali refresh calendar.
CALENDAR_LOOKAHEAD_DAYS = int(os.getenv("CALENDAR_LOOKAHEAD_DAYS", "14"))

# Seberapa sering scheduler refresh ulang calendar dari API (jam).
CALENDAR_REFRESH_HOURS = int(os.getenv("CALENDAR_REFRESH_HOURS", "6"))

# Level dampak minimum yang disimpan & dinotifikasi: "Low" / "Medium" / "High".
# Default "Medium" supaya event dampak kecil tidak membanjiri notifikasi.
CALENDAR_MIN_IMPACT = os.getenv("CALENDAR_MIN_IMPACT", "Medium")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN belum di-set. Lihat README.md untuk cara setting."
    )
if not DEEPSEEK_API_KEY:
    print("[config] WARNING: DEEPSEEK_API_KEY kosong, bot akan pakai narasi fallback saja.")
if not COINMARKETCAP_API_KEY:
    print("[config] WARNING: COINMARKETCAP_API_KEY kosong, insight BTC tidak akan berjalan.")
if TRADING_ECONOMICS_API_KEY == "guest:guest":
    print(
        "[config] WARNING: TRADING_ECONOMICS_API_KEY belum di-set, pakai demo key "
        "'guest:guest' (data sample/terbatas). Daftar API key sendiri di "
        "https://developer.tradingeconomics.com/ untuk data calendar penuh."
    )
