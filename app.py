import os
import sys
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

# ----- Logging -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("gptbot")

# ----- ENV -----
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# ----- FastAPI (health) -----
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

def run_api():
    port = int(os.environ.get("PORT", 8000))
    log.info(f"HTTP: starting Uvicorn on 0.0.0.0:{port}")
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")

# ----- Telegram Handlers -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает на Railway!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text:
        await update.message.reply_text(f"Ты написал: {text}")

def main():
    # 1) Запускаем FastAPI в отдельном системном потоке
    threading.Thread(target=run_api, daemon=True, name="uvicorn-thread").start()

    # 2) В ГЛАВНОМ потоке запускаем Telegram-поллинг
    log.info("Telegram: building application...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    log.info("Telegram: starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    log.info("Process start: python app.py (fixed)")
    main()
