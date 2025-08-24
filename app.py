import os
import logging
import asyncio
from fastapi import FastAPI
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gptbot")

# Telegram token
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# FastAPI app for health check
api = FastAPI()

@api.get("/health")
async def health():
    return {"status": "ok"}

# Telegram bot handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает на Railway!")

def run_bot():
    log.info("Telegram: building application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    log.info("Telegram: starting polling...")
    application.run_polling()

async def main():
    # Запускаем Telegram бота в отдельном asyncio таске
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.to_thread(run_bot))

    # Запускаем Uvicorn сервер (FastAPI)
    config = uvicorn.Config(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    log.info("Process start: python app.py (v3)")
    asyncio.run(main())
