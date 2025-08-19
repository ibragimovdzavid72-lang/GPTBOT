# app.py
import os
import sys
import json
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()  # если пусто — без секрета

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# ---------- Telegram App ----------
tg_app: Application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен и работает!")

# эхо
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text:
        await update.message.reply_text(f"Ты написал: {text}")

tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ---------- FastAPI ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

def webhook_path() -> str:
    # /webhook или /webhook/<секрет>
    return "/webhook" if not WEBHOOK_SECRET else f"/webhook/{WEBHOOK_SECRET}"

@api.on_event("startup")
async def on_startup():
    # Инициализация и установка вебхука
    await tg_app.initialize()
    await tg_app.start()

    if not WEBHOOK_BASE:
        log.warning("WEBHOOK_BASE не задан, вебхук не будет установлен.")
        return

    url = f"{WEBHOOK_BASE}{webhook_path()}"
    await tg_app.bot.set_webhook(url)
    log.info("Webhook установлен: %s", url)

@api.on_event("shutdown")
async def on_shutdown():
    try:
        await tg_app.bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook удалён")
    except Exception as e:
        log.warning("Не удалось удалить вебхук: %s", e)
    await tg_app.stop()
    await tg_app.shutdown()

# ---------- Webhook endpoints ----------
@api.post("/webhook")
async def webhook_plain(request: Request):
    if WEBHOOK_SECRET:
        # Если секрет включён, этот путь не должен использоваться
        raise HTTPException(status_code=404, detail="Not Found")
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)  # PTB 21.6
    await tg_app.process_update(update)
    return {"ok": True}

@api.post("/webhook/{secret}")
async def webhook_secret(request: Request, secret: Optional[str] = None):
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404, detail="Not Found")
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

# ---------- Local run (Railway запускает через python app.py) ----------
def main():
    port = int(os.environ.get("PORT", "8000"))
    log.info("HTTP: starting Uvicorn on 0.0.0.0:%d", port)
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    main()
