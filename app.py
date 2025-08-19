import os
import sys
import logging
from collections import deque, defaultdict
from typing import Deque, Dict, List
from datetime import datetime
import base64, io

from fastapi import FastAPI, Request, Header, HTTPException
import uvicorn

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------ Logging ------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("gptbot")

# ------------ ENV ------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY")
WEBHOOK_BASE       = (os.environ.get("WEBHOOK_BASE") or "").rstrip("/")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET")
DATABASE_URL       = os.environ.get("DATABASE_URL")      # optional
IMAGE_SIZE         = os.environ.get("IMAGE_SIZE", "1024x1024")  # 512x512 или 1024x1024

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_BASE:
    raise RuntimeError("WEBHOOK_BASE is not set (public Railway URL)")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set")

# ------------ OpenAI ------------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    log.warning("OpenAI client init failed: %s", e)
    openai_client = None

# ------------ Memory (per chat) ------------
MEM_LIMIT = 8  # сколько последних сообщений держать в памяти
chat_memory: Dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=MEM_LIMIT))

def memory_add(chat_id: int, role: str, content: str):
    chat_memory[chat_id].append({"role": role, "content": content})

def memory_messages(chat_id: int) -> List[dict]:
    system = [{"role": "system", "content": "Ты дружелюбный и краткий Telegram-бот. Отвечай по делу."}]
    return system + list(chat_memory[chat_id])

# ------------ Postgres logging (optional) ------------
def _pg_enabled() -> bool:
    return bool(DATABASE_URL)

def _pg_exec(sql: str, params: tuple = ()):
    if not _pg_enabled():
        return
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    finally:
        conn.close()

def pg_init():
    if not _pg_enabled():
        return
    _pg_exec("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMP NOT NULL,
            chat_id BIGINT,
            username TEXT,
            msg_type TEXT,
            user_text TEXT,
            bot_reply TEXT
        )
    """)
    log.info("Postgres: chat_logs table ready")

def pg_log(ts: datetime, chat_id: int, username: str, msg_type: str, user_text: str, bot_reply: str):
    if not _pg_enabled(): return
    _pg_exec(
        "INSERT INTO chat_logs (ts, chat_id, username, msg_type, user_text, bot_reply) VALUES (%s,%s,%s,%s,%s,%s)",
        (ts, chat_id, username, msg_type, user_text, bot_reply)
    )

# ------------ UI helpers ------------
HELP_TEXT = (
    "Я онлайн 🤖 (webhook)\n"
    "/help — помощь\n"
    "/image <описание> — сгенерировать картинку\n"
    "/reset — очистить контекст\n"
    "/diag — диагностика\n\n"
    "Просто напиши сообщение — отвечу с GPT и учту контекст."
)

def reply_kb():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("/help"), KeyboardButton("/image")],
         [KeyboardButton("/reset"), KeyboardButton("/diag")]],
        resize_keyboard=True, one_time_keyboard=False
    )

# ------------ Handlers ------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на webhook. Кнопки снизу помогут быстро вызывать команды.", reply_markup=reply_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, reply_markup=reply_kb())

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_memory[update.effective_chat.id].clear()
    await update.message.reply_text("🧠 Контекст диалога очищен.", reply_markup=reply_kb())

async def image_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args).strip()
    if not prompt:
        context.user_data["awaiting_image"] = True
        await update.message.reply_text("✍️ Напиши описание для картинки одним сообщением.", reply_markup=reply_kb())
        return
    await generate_and_send_image(update, prompt)

async def generate_and_send_image(update: Update, prompt: str):
    """Устойчивая генерация: поддерживает и URL, и base64 (b64_json)."""
    if not openai_client:
        await update.message.reply_text("Нет ключа OpenAI — генерация изображений недоступна.")
        return
    try:
        resp = openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=IMAGE_SIZE,
            n=1,
        )
        data = resp.data[0]
        if getattr(data, "b64_json", None):
            raw = base64.b64decode(data.b64_json)
            bio = io.BytesIO(raw); bio.name = "image.png"
            await update.message.reply_photo(photo=bio, caption=f"🎨 {prompt}")
            pg_log(datetime.utcnow(), update.effective_chat.id, update.effective_user.username or "", "image", prompt, "sent-bytes")
        elif getattr(data, "url", None):
            await update.message.reply_photo(photo=data.url, caption=f"🎨 {prompt}")
            pg_log(datetime.utcnow(), update.effective_chat.id, update.effective_user.username or "", "image", prompt, data.url)
        else:
            await update.message.reply_text("⚠️ Не удалось получить данные изображения от API.")
    except Exception as e:
        log.exception("Image gen error: %s", e)
        await update.message.reply_text("⚠️ Ошибка генерации изображения. Попробуй другой запрос или позже.")

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text: return

    # ждали описание для картинки?
    if context.user_data.pop("awaiting_image", False):
        await generate_and_send_image(update, text)
        return

    chat_id   = update.effective_chat.id
    username  = update.effective_user.username or ""
    memory_add(chat_id, "user", text)

    if not openai_client:
        reply = "У меня пока нет ключа OpenAI, поэтому отвечаю без ИИ 🙂"
        await update.message.reply_text(reply, reply_markup=reply_kb())
        pg_log(datetime.utcnow(), chat_id, username, "text", text, reply)
        return

    try:
        messages = memory_messages(chat_id) + [{"role": "user", "content": text}]
        resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        reply = resp.choices[0].message.content.strip()
        memory_add(chat_id, "assistant", reply)
        await update.message.reply_text(reply, reply_markup=reply_kb())
        pg_log(datetime.utcnow(), chat_id, username, "text", text, reply)
    except Exception as e:
        log.exception("OpenAI error: %s", e)
        await update.message.reply_text("⚠️ Ошибка GPT. Попробуй позже.")

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Тест: чат…")
    try:
        if openai_client:
            r = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Скажи OK одним словом."}],
            )
            await update.message.reply_text("Chat OK: " + r.choices[0].message.content.strip())
        else:
            await update.message.reply_text("Chat: нет OPENAI_API_KEY")
    except Exception as e:
        log.exception("Diag chat error: %s", e)
        await update.message.reply_text("Chat: ошибка (см. логи Railway).")

    await update.message.reply_text("🔎 Тест: изображение…")
    await generate_and_send_image(update, "минималистичная пиктограмма солнца")

# ------------ Telegram app (webhook) ------------
tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("help",  help_cmd))
tg_app.add_handler(CommandHandler("reset", reset_cmd))
tg_app.add_handler(CommandHandler("image", image_cmd))
tg_app.add_handler(CommandHandler("diag",  diag_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

# ------------ FastAPI ------------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

@api.on_event("startup")
async def on_startup():
    pg_init()
    await tg_app.initialize()
    await tg_app.start()

    # меню команд
    await tg_app.bot.set_my_commands([
        BotCommand("start", "Проверить бота"),
        BotCommand("help",  "Помощь"),
        BotCommand("image", "Сгенерировать картинку"),
        BotCommand("reset", "Очистить контекст"),
        BotCommand("diag",  "Диагностика"),
    ])

    webhook_url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    await tg_app.bot.set_webhook(url=webhook_url, secret_token=WEBHOOK_SECRET)
    log.info("Webhook set: %s", webhook_url)

@api.on_event("shutdown")
async def on_shutdown():
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
    log.info("Starting Uvicorn on 0.0.0.0:%s (webhook+buttons+memory+images+logs)", port)
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
