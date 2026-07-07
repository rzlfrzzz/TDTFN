import html
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import database as db
import market_data
from ai_narrative import generate_narrative, generate_btc_insight, DIVIDER
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


# ---------- Helpers ----------

async def safe_reply(update: Update, text: str, parse_mode=ParseMode.HTML):
    """Reply dengan HTML, fallback ke plain text kalau parsing gagal
    (misalnya ada tag/simbol yang lolos escaping) supaya user tetap dapat
    pesannya walau formatting-nya rusak, bukan silent fail."""
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except BadRequest as e:
        logger.warning(f"Gagal kirim dengan parse_mode {parse_mode}, fallback plain text: {e}")
        plain = html.unescape(
            text.replace("<b>", "").replace("</b>", "")
            .replace("<i>", "").replace("</i>", "")
            .replace("<pre>", "").replace("</pre>", "")
        )
        await update.message.reply_text(plain)


# ---------- Command handlers ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Selamat datang!</b>\n"
        "Bot notifikasi jadwal pengumuman The Fed (FOMC &amp; event penting "
        "lainnya), plus insight harian BTC.\n"
        f"{DIVIDER}\n"
        "🔔 <b>Kamu akan dapat notifikasi otomatis:</b>\n"
        "• 24 jam sebelum pengumuman Fed\n"
        "• 15 menit sebelum pengumuman Fed\n"
        "• Insight BTC tiap pagi jam 07:00 WIB\n\n"
        "🛠 <b>Perintah tersedia:</b>\n"
        "/subscribe – aktifkan notifikasi\n"
        "/unsubscribe – matikan notifikasi\n"
        "/next – lihat event Fed terdekat\n"
        "/btc – lihat insight BTC saat ini\n"
        "/status – cek status subscribe kamu"
    )
    await safe_reply(update, text)


async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    db.add_subscriber(chat.id, chat.username)
    await safe_reply(
        update,
        "✅ <b>Berhasil subscribe!</b>\n"
        "Kamu akan dapat notifikasi H-24 jam dan H-15 menit sebelum event Fed.",
    )


async def unsubscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    db.remove_subscriber(chat.id)
    await safe_reply(update, "❌ Kamu sudah <b>unsubscribe</b> dari notifikasi.")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    subscribed = db.is_subscribed(chat.id)
    status_line = "✅ <b>Subscribed</b>" if subscribed else "❌ <b>Belum subscribe</b> (pakai /subscribe)"
    await safe_reply(update, f"Status kamu: {status_line}")


async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upcoming = get_upcoming_events()
    if not upcoming:
        await safe_reply(update, "Belum ada event terjadwal di data saat ini.")
        return
    event = upcoming[0]
    dt = get_event_dt(event)
    wib = dt.astimezone(timezone(timedelta(hours=7)))
    note = html.escape(event.get("note", ""), quote=False)
    name = html.escape(event["name"], quote=False)
    text = (
        "📅 <b>Event Fed Terdekat</b>\n"
        f"{DIVIDER}\n"
        f"<b>{name}</b>\n"
        f"🗓 {wib.strftime('%d %b %Y, %H:%M WIB')} ({dt.strftime('%H:%M UTC')})\n\n"
        f"{note}"
    )
    await safe_reply(update, text)


async def btc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "⏳ Mengambil data BTC terbaru...")
    snapshot = market_data.fetch_market_snapshot()
    if snapshot is None:
        await safe_reply(
            update,
            "⚠️ Gagal ambil data BTC dari CoinMarketCap saat ini. Coba lagi "
            "beberapa saat lagi.",
        )
        return
    now_wib = datetime.now(timezone.utc).astimezone(WIB_TZ)
    text = generate_btc_insight(snapshot, timestamp_label=now_wib.strftime("%d %b %Y • %H:%M WIB"))
    await safe_reply(update, text)


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
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            logger.warning(f"HTML gagal di-parse untuk {chat_id}, fallback plain text: {e}")
            plain = html.unescape(
                text.replace("<b>", "").replace("</b>", "")
                .replace("<i>", "").replace("</i>", "")
                .replace("<pre>", "").replace("</pre>", "")
            )
            try:
                await app.bot.send_message(chat_id=chat_id, text=plain)
            except Exception as e2:
                logger.warning(f"Gagal kirim (fallback) ke {chat_id}: {e2}")
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

    now_wib = datetime.now(timezone.utc).astimezone(WIB_TZ)
    text = generate_btc_insight(snapshot, timestamp_label=now_wib.strftime("%d %b %Y • %H:%M WIB"))
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
