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
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # может быть пустым — тогда бот будет просто отвечать-эхо

# ---------- FastAPI (health) ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

def run_api():
    port = int(os.environ.get("PORT", 8000))
    log.info(f"HTTP: starting Uvicorn on 0.0.0.0:{port}")
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")

# ---------- OpenAI ----------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    log.warning("OpenAI client not available: %s", e)
    openai_client = None

# ---------- Handlers ----------
HELP_TEXT = (
    "Я онлайн 🤖\n"
    "/start — проверить, что бот жив\n"
    "/help — справка\n\n"
    "Просто напиши сообщение — отвечу с помощью GPT. "
    "Если ключа нет, вернусь к простому ответу."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает на Railway! Напиши что-нибудь, отвечу с помощью GPT.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def reply_with_gpt(text: str) -> str:
    """Отправка запроса в OpenAI (gpt-4o-mini). Возвращает текст ответа."""
    if not openai_client:
        return "У меня пока нет ключа OpenAI, поэтому просто отвечаю без ИИ 🙂"

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и краткий Telegram-бот. Отвечай по делу и понятно."},
                {"role": "user", "content": text},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.exception("OpenAI error: %s", e)
        return "⚠️ Ошибка при обращении к GPT. Попробуй ещё раз чуть позже."

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = (update.message.text or "").strip()
    if not user_text:
        return
    # Защита от слишком длинных сообщений
    if len(user_text) > 4000:
        await update.message.reply_text("Сообщение слишком длинное. Сократи, пожалуйста.")
        return

    reply = await reply_with_gpt(user_text)
    await update.message.reply_text(reply)

def main():
    # 1) HTTP-сервер в отдельном потоке
    threading.Thread(target=run_api, daemon=True, name="uvicorn-thread").start()

    # 2) Telegram-поллинг — в главном потоке (без asyncio-ошибок)
    log.info("Telegram: building application...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Telegram: starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    log.info("Process start: python app.py (gpt-enabled)")
    main()
