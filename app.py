import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Глобальные переменные ---
IMAGES_ENABLED = os.getenv("IMAGES_ENABLED", "0") == "1"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is required!")

# --- FastAPI ---
app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()


# --- Хелперы ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я GPTBot 🤖\nИспользуй /help чтобы узнать команды.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - запуск\n"
        "/help - помощь\n"
        "/enable_images - включить картинки (только админ)\n"
        "/disable_images - выключить картинки (только админ)\n"
        "/images_status - статус картинок\n"
    )
    await update.message.reply_text(text)


async def enable_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IMAGES_ENABLED
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Только админ может это делать.")
    IMAGES_ENABLED = True
    await update.message.reply_text("🟢 Генерация картинок включена!")


async def disable_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IMAGES_ENABLED
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Только админ может это делать.")
    IMAGES_ENABLED = False
    await update.message.reply_text("🔴 Генерация картинок выключена!")


async def images_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "🟢 ВКЛ" if IMAGES_ENABLED else "🔴 ВЫКЛ"
    await update.message.reply_text(f"Статус картинок: {status}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "картинку" in text.lower():
        if not IMAGES_ENABLED:
            await update.message.reply_text("❌ Картинки сейчас выключены админом.")
            return
        await update.message.reply_text("📷 (Здесь будет генерация картинок через OpenAI API)")
    else:
        await update.message.reply_text(f"Ты написал: {text}")


# --- Регистрация команд ---
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_cmd))
telegram_app.add_handler(CommandHandler("enable_images", enable_images))
telegram_app.add_handler(CommandHandler("disable_images", disable_images))
telegram_app.add_handler(CommandHandler("images_status", images_status))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# --- Webhook FastAPI ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.initialize()
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})


@app.on_event("startup")
async def startup_event():
    if WEBHOOK_BASE:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        await telegram_app.bot.set_webhook(url=url)
        logger.info(f"Webhook set: {url}")


@app.on_event("shutdown")
async def shutdown_event():
    await telegram_app.bot.delete_webhook()
    logger.info("Webhook deleted")
