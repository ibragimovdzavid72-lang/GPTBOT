import os
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
from openai import OpenAI

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Не заданы TELEGRAM_TOKEN или OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = ReplyKeyboardMarkup([["💬 Чат", "🎨 Картинка"], ["✅ Задача"]], resize_keyboard=True)
    await update.message.reply_text("Привет! Я бот с GPT и генерацией картинок.", reply_markup=menu)

async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": user_text}],
            temperature=0.7,
            max_tokens=500
        )
        answer = resp.choices[0].message.content
    except Exception as e:
        answer = f"Ошибка OpenAI: {e}"
    await update.message.reply_text(answer)

async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /image <описание>")
        return
    prompt = " ".join(context.args)
    await update.message.reply_text("⏳ Генерирую изображение...")
    try:
        gen = client.images.generate(model="gpt-image-1", prompt=prompt, size="512x512", n=1)
        url = gen.data[0].url
        await update.message.reply_photo(url, caption=f"🎨 {prompt}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка генерации: {e}")

async def task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ Принять", callback_data="task_accept"),
                 InlineKeyboardButton("🏁 Готово", callback_data="task_done")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 Новая задача: проверить отчёт", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user.first_name
    if query.data == "task_accept":
        await query.edit_message_text(f"✅ {user} принял(а) задачу")
    elif query.data == "task_done":
        await query.edit_message_text(f"🏁 {user} выполнил(а) задачу")

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎨 Картинка":
        await update.message.reply_text("Напиши: /image <описание>")
    elif text == "✅ Задача":
        await task(update, context)
    else:
        await chatgpt(update, context)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(CommandHandler("task", task))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))
    app.run_polling()

if __name__ == "__main__":
    main()
