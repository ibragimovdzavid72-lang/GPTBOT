import os
import sys
import logging
import threading
import time
from fastapi import FastAPI
import uvicorn

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("gptbot")

# ---------- ENV ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    log.error("ENV ERROR: TELEGRAM_BOT_TOKEN is not set")
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# ---------- Telegram Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот запущен ✅")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    await update.message.reply_text(f"Ты написал: {text}")

def run_bot():
    try:
        log.info("Telegram: building application...")
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

        log.info("Telegram: starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        log.exception("Telegram bot crashed: %s", e)
        time.sleep(2)
        raise

# ---------- FastAPI for health ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

def main():
    log.info("Boot: starting bot thread...")
    t = threading.Thread(target=run_bot, daemon=True, name="tg-bot-thread")
    t.start()

    port = int(os.environ.get("PORT", 8000))
    log.info(f"Boot: starting HTTP server on 0.0.0.0:{port}")
    try:
        uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        log.exception("Uvicorn crashed: %s", e)
        raise

if __name__ == "__main__":
    log.info("Process start: python app.py")
    main()
