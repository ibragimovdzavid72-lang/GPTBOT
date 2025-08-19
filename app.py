import os
import sys
import logging
from fastapi import FastAPI, Request, Header, HTTPException
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WEBHOOK_BASE = (os.environ.get("WEBHOOK_BASE") or "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_BASE:
    raise RuntimeError("WEBHOOK_BASE is not set (your public Railway URL)")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set")

# ---------- OpenAI (optional) ----------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    log.warning("OpenAI client not available: %s", e)
    openai_client = None

# ---------- Handlers ----------
HELP_TEXT = (
    "Я онлайн 🤖\n"
    "/start — проверить бота\n"
    "/help — помощь\n\n"
    "Просто напиши сообщение — отвечу через GPT."
)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на webhook. Пиши — отвечу с GPT!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    if not openai_client:
        await update.message.reply_text("Нет ключа OpenAI — отвечаю без ИИ 🙂")
        return
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и краткий Telegram-бот."},
                {"role": "user", "content": text},
            ],
        )
        await update.message.reply_text(resp.choices[0].message.content.strip())
    except Exception as e:
        log.exception("OpenAI error: %s", e)
        await update.message.reply_text("⚠️ Ошибка GPT. Попробуй позже.")

# ---------- Telegram Application (no polling) ----------
tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("help", help_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

# ---------- FastAPI ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

@api.on_event("startup")
async def on_startup():
    # Инициализация PTB и установка вебхука
    await tg_app.initialize()
    await tg_app.start()
    webhook_url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    await tg_app.bot.set_webhook(url=webhook_url, secret_token=WEBHOOK_SECRET)
    log.info("Webhook set: %s", webhook_url)

@api.on_event("shutdown")
async def on_shutdown():
    # Снятие вебхука и останов PTB
    try:
        await tg_app.bot.delete_webhook()
    except Exception:
        pass
    await tg_app.stop()
    await tg_app.shutdown()
    log.info("Telegram application stopped")

@api.post("/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    # Проверяем секрет в пути и заголовке
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad path secret")
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad header secret")

    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    log.info("Starting Uvicorn on 0.0.0.0:%s (webhook mode)", port)
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
