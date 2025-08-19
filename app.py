# app.py
import os
import sys
import json
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
import uvicorn

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
)

# --------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("gptbot")

# --------- ENV --------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
ADMIN_IDS_RAW = os.environ.get("ADMIN_IDS", "")
IMAGES_ENABLED = os.environ.get("IMAGES_ENABLED", "false").lower() in ("1", "true", "yes")
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "1024x1024")
SAFE_MODE = os.environ.get("SAFE_MODE", "true").lower() in ("1", "true", "yes")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# --------- OpenAI client (optional) -----------
# Работает даже если ключа нет: функции сами проверят наличие
try:
    from openai import OpenAI
    _openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    log.warning("OpenAI SDK not available or failed to init: %s", e)
    _openai_client = None

# --------- Bot state (in-memory, no DB) ------
BOT_ENABLED: bool = True  # можно выключать/включать из Telegram
DIALOG_MEMORY: Dict[int, List[Dict[str, str]]] = {}  # user_id -> messages (role/content)
MAX_MEMORY = 12  # последних сообщений

def is_admin(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    if not ADMIN_IDS_RAW:
        return False
    try:
        admin_ids = {int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()}
    except ValueError:
        admin_ids = set()
    return user_id in admin_ids

# --------- UI helpers -------------------------
def main_menu(admin: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("💬 Чат", callback_data="mode_chat"),
         InlineKeyboardButton("🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton("🧹 Очистить память", callback_data="clear_memory")],
    ]
    if admin:
        buttons.append([
            InlineKeyboardButton("⚙️ Admin: ON/OFF", callback_data="admin_toggle"),
        ])
    return InlineKeyboardMarkup(buttons)

# --------- OpenAI helpers ---------------------
async def ask_openai(messages: List[Dict[str, str]]) -> str:
    """
    messages: [{"role":"system/user/assistant","content":"..."}]
    """
    if not _openai_client or not OPENAI_API_KEY:
        raise RuntimeError("openai_unavailable")

    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # Частые коды: billing_hard_limit_reached / rate_limit_exceeded и т.д.
        log.warning("OpenAI chat error: %s", e)
        raise

async def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Возвращает URL изображения. Требует IMAGES_ENABLED=true.
    """
    if not IMAGES_ENABLED:
        raise RuntimeError("images_disabled")
    if not _openai_client or not OPENAI_API_KEY:
        raise RuntimeError("openai_unavailable")

    try:
        img = _openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
        # SDK возвращает data[0].url (временная ссылка)
        return img.data[0].url
    except Exception as e:
        log.warning("OpenAI image error: %s", e)
        raise

# --------- Handlers ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    DIALOG_MEMORY.pop(uid, None)
    text = (
        "Привет! Я GPTBOT 🤖\n\n"
        "• Пиши текст — отвечу с памятью диалога\n"
        "• Нажми «🖼️ Картинка» — сгенерирую изображение\n"
        "• «🧹 Очистить память» — забыть контекст\n"
        "• Админ может /on и /off или кнопкой в админ-меню\n"
    )
    await update.effective_chat.send_message(
        text, reply_markup=main_menu(is_admin(uid))
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    await update.message.reply_text("Меню:", reply_markup=main_menu(is_admin(uid)))

async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not is_admin(uid):
        return await update.message.reply_text("Недостаточно прав.")
    global BOT_ENABLED
    BOT_ENABLED = True
    await update.message.reply_text("Бот: ✅ включён")

async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not is_admin(uid):
        return await update.message.reply_text("Недостаточно прав.")
    global BOT_ENABLED
    BOT_ENABLED = False
    await update.message.reply_text("Бот: ⛔️ выключен")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id if update.effective_user else None

    if query.data == "mode_chat":
        await query.edit_message_text(
            "Режим: 💬 Чат. Напиши сообщение.", reply_markup=main_menu(is_admin(uid))
        )
    elif query.data == "mode_image":
        if not IMAGES_ENABLED:
            return await query.edit_message_text(
                "Генерация изображений отключена.", reply_markup=main_menu(is_admin(uid))
            )
        await query.edit_message_text(
            "Опиши картинку одним сообщением — я сгенерирую 🖼️", reply_markup=main_menu(is_admin(uid))
        )
        context.user_data["await_image_prompt"] = True
    elif query.data == "clear_memory":
        DIALOG_MEMORY.pop(uid, None)
        await query.edit_message_text(
            "Память диалога очищена 🧹", reply_markup=main_menu(is_admin(uid))
        )
    elif query.data == "admin_toggle":
        if not is_admin(uid):
            return await query.edit_message_text("Недостаточно прав.")
        global BOT_ENABLED
        BOT_ENABLED = not BOT_ENABLED
        state = "✅ включён" if BOT_ENABLED else "⛔️ выключен"
        await query.edit_message_text(
            f"Бот сейчас: {state}", reply_markup=main_menu(is_admin(uid))
        )

def _push_memory(uid: int, role: str, content: str):
    msgs = DIALOG_MEMORY.setdefault(uid, [])
    msgs.append({"role": role, "content": content})
    if len(msgs) > MAX_MEMORY:
        DIALOG_MEMORY[uid] = msgs[-MAX_MEMORY:]

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    text = (update.message.text or "").strip()

    # Если ждём промпт для картинки
    if context.user_data.get("await_image_prompt"):
        context.user_data["await_image_prompt"] = False
        try:
            url = await generate_image(text, IMAGE_SIZE)
            return await update.message.reply_photo(
                photo=url,
                caption="Готово! Если нужна новая картинка — нажми «🖼️ Картинка».",
                reply_markup=main_menu(is_admin(uid)),
            )
        except Exception as e:
            log.warning("Image gen failed: %s", e)
            hint = (
                "Не удалось сгенерировать изображение.\n"
                "Возможные причины: лимит биллинга, ключ не задан, IMAGES_ENABLED=false."
            )
            return await update.message.reply_text(
                f"⚠️ {hint}", reply_markup=main_menu(is_admin(uid))
            )

    if not BOT_ENABLED and not is_admin(uid):
        return await update.message.reply_text(
            "⛔️ Бот временно выключен. Обратитесь к администратору."
        )

    # Память + запрос к OpenAI (если есть ключ)
    system_prompt = (
        "Ты полезный ассистент. Отвечай кратко и по делу на русском. "
        "Если тебя просят сгенерировать картинку — предложи нажать кнопку 🖼️."
    )
    _push_memory(uid, "system", system_prompt)
    _push_memory(uid, "user", text)

    try:
        reply = await ask_openai(DIALOG_MEMORY[uid])
        _push_memory(uid, "assistant", reply)
        await update.message.reply_text(reply, reply_markup=main_menu(is_admin(uid)))
    except Exception as e:
        # fallback: эхо + подсказка
        log.warning("Chat failed, fallback echo: %s", e)
        fallback = (
            "Сейчас не могу обратиться к модели (возможно, закончился баланс / нет ключа). "
            "Вернусь к работе, как только будет доступ. А пока эхо: "
        )
        await update.message.reply_text(fallback + text, reply_markup=main_menu(is_admin(uid)))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Update error: %s", context.error, exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await update.effective_chat.send_message("⚠️ Произошла ошибка. Попробуйте позже.")
    except Exception:
        pass

# --------- Telegram Application ---------------
application: Application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("menu", menu_cmd))
application.add_handler(CommandHandler("on", on_cmd))
application.add_handler(CommandHandler("off", off_cmd))
application.add_handler(CallbackQueryHandler(button_click))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
application.add_error_handler(error_handler)

# --------- FastAPI ----------------------------
api = FastAPI()

@api.get("/health")
async def health():
    return {"ok": True}

# Универсальный обработчик вебхука
async def _handle_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    update = Update.de_json(data=data, bot=application.bot)
    await application.process_update(update)
    return {"ok": True}

# Роут без секрета
@api.post("/webhook")
async def webhook_plain(request: Request):
    # Если у нас задан секрет — запретим доступ к plain-пути,
    # чтобы не было дублей (502 у Telegram при таймаутах).
    if WEBHOOK_SECRET:
        raise HTTPException(status_code=404, detail="not found")
    return await _handle_webhook(request)

# Роут с секретом (если задан)
if WEBHOOK_SECRET:
    @api.post(f"/webhook/{WEBHOOK_SECRET}")
    async def webhook_secret(request: Request):
        return await _handle_webhook(request)

# Автосетап вебхука при старте
@api.on_event("startup")
async def on_startup():
    log.info("Starting up...")
    await application.initialize()
    await application.start()

    if WEBHOOK_BASE:
        url = f"{WEBHOOK_BASE}/webhook"
        if WEBHOOK_SECRET:
            url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        try:
            resp = await application.bot.set_webhook(url)
            log.info("setWebhook: %s", resp)
        except Exception as e:
            log.error("Failed to set webhook: %s", e)
    else:
        log.info("WEBHOOK_BASE not set — webhook will not be updated automatically.")

    log.info("Application startup complete.")

@api.on_event("shutdown")
async def on_shutdown():
    log.info("Shutting down...")
    try:
        await application.stop()
        await application.shutdown()
    finally:
        log.info("Application shutdown complete.")

# --------- Local run (Railway uses start command) ---------
def run():
    port = int(os.environ.get("PORT", "8080"))
    log.info("HTTP: starting Uvicorn on 0.0.0.0:%s", port)
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    run()
