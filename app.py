
import os
import sys
import logging
from collections import deque, defaultdict
from typing import Deque, Dict, List, Optional
from datetime import datetime
import base64, io

from fastapi import FastAPI, Request, Header, HTTPException
import uvicorn

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
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
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY")
WEBHOOK_BASE       = (os.environ.get("WEBHOOK_BASE") or "").rstrip("/")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET")
DATABASE_URL       = os.environ.get("DATABASE_URL")   # optional
IMAGE_SIZE         = os.environ.get("IMAGE_SIZE", "1024x1024")
ADMIN_IDS_ENV      = os.environ.get("ADMIN_IDS", "")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_BASE:
    raise RuntimeError("WEBHOOK_BASE is not set (public Railway URL)")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set")

ADMIN_IDS = set()
for part in ADMIN_IDS_ENV.replace(";", ",").split(","):
    part = part.strip()
    if part.isdigit():
        ADMIN_IDS.add(int(part))

# ---------- OpenAI ----------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    log.warning("OpenAI client not available: %s", e)
    openai_client = None

# ---------- Memory ----------
MEM_LIMIT = 8
chat_memory: Dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=MEM_LIMIT))

def memory_add(chat_id: int, role: str, content: str):
    chat_memory[chat_id].append({"role": role, "content": content})

def memory_messages(chat_id: int) -> List[dict]:
    sys_msg = [{"role": "system", "content": "Ты дружелюбный и лаконичный Telegram-бот. Отвечай по делу."}]
    return sys_msg + list(chat_memory[chat_id])

# ---------- Postgres ----------
def have_pg() -> bool:
    return bool(DATABASE_URL)

def pg_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)

def pg_exec(sql: str, params: tuple = ()):
    if not have_pg(): return
    conn = pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    finally:
        conn.close()

def pg_query_one(sql: str, params: tuple = ()) -> Optional[tuple]:
    if not have_pg(): return None
    conn = pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()
    finally:
        conn.close()

def pg_init():
    if not have_pg():
        return
    pg_exec("""
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
    pg_exec("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # default: bot_enabled=true
    if not get_setting("bot_enabled"):
        set_setting("bot_enabled", "true")
    log.info("Postgres tables ready")

def set_setting(key: str, value: str):
    if not have_pg(): return
    pg_exec("""
        INSERT INTO settings(key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value=excluded.value
    """, (key, value))

def get_setting(key: str) -> Optional[str]:
    if not have_pg(): return None
    row = pg_query_one("SELECT value FROM settings WHERE key=%s", (key,))
    return row[0] if row else None

def pg_log(ts: datetime, chat_id: int, username: str, msg_type: str, user_text: str, bot_reply: str):
    if not have_pg(): return
    pg_exec(
        "INSERT INTO chat_logs (ts, chat_id, username, msg_type, user_text, bot_reply) VALUES (%s,%s,%s,%s,%s,%s)",
        (ts, chat_id, username, msg_type, user_text, bot_reply)
    )

# ---------- Global state (fallback, if no Postgres) ----------
BOT_ENABLED = True  # будет перезаписано из PG на старте, если есть

def bot_enabled() -> bool:
    if have_pg():
        val = get_setting("bot_enabled")
        if val is not None:
            return val.lower() == "true"
    return BOT_ENABLED

def set_bot_enabled(flag: bool):
    global BOT_ENABLED
    BOT_ENABLED = flag
    if have_pg():
        set_setting("bot_enabled", "true" if flag else "false")

# ---------- UI ----------
HELP_TEXT = (
    "Привет! Я онлайн 🤖\n"
    "• Отвечаю с учетом контекста\n"
    "• Генерирую изображения через /image <описание>\n"
    "• /reset — очистить контекст\n"
    "• /diag — самопроверка\n\n"
    "Админ: /admin для панели управления."
)

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("/help"), KeyboardButton("/image")],
         [KeyboardButton("/reset"), KeyboardButton("/diag")]],
        resize_keyboard=True
    )

def admin_markup():
    status = "🟢 ВКЛ" if bot_enabled() else "🔴 ВЫКЛ"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Статус: " + status, callback_data="noop")],
        [InlineKeyboardButton("🟢 Включить", callback_data="on"),
         InlineKeyboardButton("🔴 Выключить", callback_data="off")],
        [InlineKeyboardButton("🧹 Reset контекста", callback_data="reset")],
    ])

def is_admin(update: Update) -> bool:
    uid = update.effective_user.id
    return uid in ADMIN_IDS

# ---------- Handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на webhook. Кнопки снизу помогут быстро вызывать команды.", reply_markup=main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, reply_markup=main_keyboard())

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_memory[update.effective_chat.id].clear()
    await update.message.reply_text("🧠 Контекст очищен.", reply_markup=main_keyboard())

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Только для админов.", reply_markup=main_keyboard())
        return
    await update.message.reply_text("⚙️ Админ-панель", reply_markup=main_keyboard())
    await update.message.reply_text("Выберите действие:", reply_markup=admin_markup())

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.callback_query.answer("Только для админов", show_alert=True)
        return
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "on":
        set_bot_enabled(True)
        await q.edit_message_text("🟢 Бот включен.", reply_markup=admin_markup())
    elif data == "off":
        set_bot_enabled(False)
        await q.edit_message_text("🔴 Бот выключен.", reply_markup=admin_markup())
    elif data == "reset":
        chat_memory.clear()
        await q.edit_message_text("🧹 Контекст всех чатов очищен.", reply_markup=admin_markup())
    else:
        await q.edit_message_reply_markup(reply_markup=admin_markup())

async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Только для админов.")
        return
    set_bot_enabled(True)
    await update.message.reply_text("🟢 Бот включен.")

async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Только для админов.")
        return
    set_bot_enabled(False)
    await update.message.reply_text("🔴 Бот выключен.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Статус: " + ("🟢 ВКЛ" if bot_enabled() else "🔴 ВЫКЛ"))

async def image_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args).strip()
    if not prompt:
        context.user_data["awaiting_image"] = True
        await update.message.reply_text("✍️ Напиши описание для картинки одним сообщением.", reply_markup=main_keyboard())
        return
    await generate_and_send_image(update, prompt)

async def generate_and_send_image(update: Update, prompt: str):
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

    if (not bot_enabled()) and (not is_admin(update)):
        await update.message.reply_text("⏸ Бот временно выключен админом.")
        return

    if context.user_data.pop("awaiting_image", False):
        await generate_and_send_image(update, text)
        return

    chat_id = update.effective_chat.id
    username = update.effective_user.username or ""
    memory_add(chat_id, "user", text)

    if not openai_client:
        reply = "У меня пока нет ключа OpenAI, поэтому отвечаю без ИИ 🙂"
        await update.message.reply_text(reply, reply_markup=main_keyboard())
        pg_log(datetime.utcnow(), chat_id, username, "text", text, reply)
        return

    try:
        messages = memory_messages(chat_id) + [{"role": "user", "content": text}]
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        reply = resp.choices[0].message.content.strip()
        memory_add(chat_id, "assistant", reply)
        await update.message.reply_text(reply, reply_markup=main_keyboard())
        pg_log(datetime.utcnow(), chat_id, username, "text", text, reply)
    except Exception as e:
        log.exception("OpenAI error: %s", e)
        await update.message.reply_text("⚠️ Ошибка GPT. Попробуй позже.")

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Диагностика: чат…")
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
    await update.message.reply_text("🔎 Диагностика: изображение…")
    await generate_and_send_image(update, "минималистичная пиктограмма солнца")

# ---------- Telegram app (webhook) ----------
tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("help", help_cmd))
tg_app.add_handler(CommandHandler("reset", reset_cmd))
tg_app.add_handler(CommandHandler("image", image_cmd))
tg_app.add_handler(CommandHandler("diag", diag_cmd))
tg_app.add_handler(CommandHandler("admin", admin_cmd))
tg_app.add_handler(CommandHandler("on", on_cmd))
tg_app.add_handler(CommandHandler("off", off_cmd))
tg_app.add_handler(CommandHandler("status", status_cmd))
tg_app.add_handler(CallbackQueryHandler(admin_cb))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

# ---------- FastAPI ----------
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}

@api.on_event("startup")
async def on_startup():
    pg_init()
    try:
        # Синхронизация состояния в памяти с БД
        _ = bot_enabled()
    except Exception:
        pass

    await tg_app.initialize()
    await tg_app.start()

    await tg_app.bot.set_my_commands([
        BotCommand("start", "Начать"),
        BotCommand("help", "Помощь"),
        BotCommand("image", "Сгенерировать картинку"),
        BotCommand("reset", "Очистить контекст"),
        BotCommand("diag", "Диагностика"),
        BotCommand("admin", "Админ-панель"),
        BotCommand("status", "Статус бота"),
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
    log.info("Starting Uvicorn on 0.0.0.0:%s (modern+admin+images+memory+webhook)", port)
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
