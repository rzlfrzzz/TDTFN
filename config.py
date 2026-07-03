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

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN belum di-set. Lihat README.md untuk cara setting."
    )
if not DEEPSEEK_API_KEY:
    print("[config] WARNING: DEEPSEEK_API_KEY kosong, bot akan pakai narasi fallback saja.")
if not COINMARKETCAP_API_KEY:
    print("[config] WARNING: COINMARKETCAP_API_KEY kosong, insight BTC tidak akan berjalan.")
