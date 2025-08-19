from telegram.ext import Application, CommandHandler, MessageHandler, filters

application = Application.builder().token("
8450495463:AAHgqcdBVJdgT0vfw6vbXTSu5flmYYiqpz8").build()

async def start(update, context):
    await update.message.reply_text("Привет, бот работает!")

application.add_handler(CommandHandler("start", start))

