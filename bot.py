import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import database as db
import market_data
from ai_narrative import generate_narrative, generate_btc_insight
from config import TELEGRAM_BOT_TOKEN, BROADCAST_CHAT_ID
from events import get_upcoming_events, get_event_dt

# Jam insight BTC = 07:00 WIB (pagi Indonesia). Pakai ZoneInfo supaya
# otomatis handle timezone dengan tepat.
BTC_INSIGHT_HOUR = 7
BTC_INSIGHT_MINUTE = 0
WIB_TZ = ZoneInfo("Asia/Jakarta")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Toleransi jendela cek (scheduler jalan tiap 1 menit, jadi kasih toleransi
# +-90 detik supaya tidak ke-skip meskipun ada sedikit delay eksekusi)
CHECK_INTERVAL_SECONDS = 60
WINDOW_SECONDS = 90


# ---------- Command handlers ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Halo! Ini bot notifikasi jadwal pengumuman The Fed (FOMC & event "
        "penting lainnya), plus insight harian BTC.\n\n"
        "Kamu akan dapat notifikasi otomatis:\n"
        "• 24 jam sebelum pengumuman Fed\n"
        "• 15 menit sebelum pengumuman Fed\n"
        "• Insight BTC tiap pagi jam 07:00 WIB\n\n"
        "Perintah yang tersedia:\n"
        "/subscribe – aktifkan notifikasi\n"
        "/unsubscribe – matikan notifikasi\n"
        "/next – lihat event Fed terdekat\n"
        "/btc – lihat insight BTC saat ini\n"
        "/status – cek status subscribe kamu"
    )
    await update.message.reply_text(text)


async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    db.add_subscriber(chat.id, chat.username)
    await update.message.reply_text(
        "✅ Kamu berhasil subscribe! Kamu akan dapat notifikasi H-24 jam dan "
        "H-15 menit sebelum event Fed."
    )


async def unsubscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    db.remove_subscriber(chat.id)
    await update.message.reply_text("❌ Kamu sudah unsubscribe dari notifikasi.")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    subscribed = db.is_subscribed(chat.id)
    await update.message.reply_text(
        "Status kamu: " + ("✅ Subscribed" if subscribed else "❌ Belum subscribe (pakai /subscribe)")
    )


async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upcoming = get_upcoming_events()
    if not upcoming:
        await update.message.reply_text("Belum ada event terjadwal di data saat ini.")
        return
    event = upcoming[0]
    dt = get_event_dt(event)
    wib = dt.astimezone(timezone(timedelta(hours=7)))
    await update.message.reply_text(
        f"📅 Event terdekat: *{event['name']}*\n"
        f"Waktu: {wib.strftime('%d %b %Y, %H:%M WIB')} ({dt.strftime('%H:%M UTC')})\n"
        f"{event.get('note', '')}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def btc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mengambil data BTC terbaru...")
    snapshot = market_data.fetch_market_snapshot()
    if snapshot is None:
        await update.message.reply_text(
            "⚠️ Gagal ambil data BTC dari CoinMarketCap saat ini. Coba lagi "
            "beberapa saat lagi."
        )
        return
    text = generate_btc_insight(snapshot)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ---------- Scheduler job ----------

async def check_and_notify(app: Application):
    now = datetime.now(timezone.utc)
    for event in get_upcoming_events(now=now - timedelta(days=2)):  # ambil termasuk yang barusan lewat dikit
        event_dt = get_event_dt(event)
        delta = (event_dt - now).total_seconds()

        # H-24 jam
        if abs(delta - 24 * 3600) <= WINDOW_SECONDS and not db.already_sent(event["id"], "24h"):
            await broadcast_notification(app, event, stage="24h", stage_label="24 jam lagi")
            db.mark_sent(event["id"], "24h")

        # H-15 menit
        if abs(delta - 15 * 60) <= WINDOW_SECONDS and not db.already_sent(event["id"], "15m"):
            await broadcast_notification(app, event, stage="15m", stage_label="15 menit lagi")
            db.mark_sent(event["id"], "15m")


async def broadcast_message(app: Application, text: str) -> int:
    """Kirim `text` ke semua subscriber + BROADCAST_CHAT_ID (kalau diset).
    Dipakai bareng oleh notifikasi Fed dan insight BTC (subscriber sama).
    Return jumlah chat yang jadi target (bukan jumlah yang sukses)."""
    recipients = db.get_all_subscribers()
    if BROADCAST_CHAT_ID:
        recipients = recipients + [BROADCAST_CHAT_ID]

    for chat_id in recipients:
        try:
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Gagal kirim ke {chat_id}: {e}")

    return len(recipients)


async def broadcast_notification(app: Application, event: dict, stage: str, stage_label: str):
    text = generate_narrative(event["name"], event.get("note", ""), stage_label)
    count = await broadcast_message(app, text)
    logger.info(f"Notifikasi '{stage}' untuk event '{event['id']}' terkirim ke {count} chat.")


async def btc_daily_insight(app: Application):
    """Job harian: insight BTC jam 07:00 WIB. Kalau fetch data
    gagal, skip aja hari itu (jangan crash, jangan kirim data kosong)."""
    snapshot = market_data.fetch_market_snapshot()
    if snapshot is None:
        logger.warning("[btc_daily_insight] Gagal ambil data BTC, skip notifikasi hari ini.")
        return

    text = generate_btc_insight(snapshot)
    count = await broadcast_message(app, text)
    logger.info(f"Insight BTC harian terkirim ke {count} chat.")


# ---------- Main ----------

def main():
    db.init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe_cmd))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("btc", btc_cmd))

    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        check_and_notify,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        args=[app],
    )
    # Insight BTC tiap hari jam 07:00 WIB (pagi Indonesia).
    scheduler.add_job(
        btc_daily_insight,
        CronTrigger(hour=BTC_INSIGHT_HOUR, minute=BTC_INSIGHT_MINUTE, timezone=WIB_TZ),
        args=[app],
    )
    scheduler.start()

    logger.info("Bot mulai jalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
