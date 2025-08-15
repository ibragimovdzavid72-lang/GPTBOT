import os
import logging
import threading
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gptbot")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
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
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Блокирующий long polling — запускаем в отдельном потоке
    log.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ---------- FastAPI for health ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

def main():
    # Запустить бота в фоне
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()

    # HTTP-сервер (чтобы Railway видел живой сервис)
    port = int(os.environ.get("PORT", 8000))
    log.info(f"Starting HTTP server on port {port} ...")
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    main()
