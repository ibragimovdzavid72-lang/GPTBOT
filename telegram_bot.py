import os
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from database import SessionLocal, ChatMessage, User
import uuid

# Initialize OpenAI client
openai.api_key = os.environ.get("OPENAI_API_KEY")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    # Save user to database
    db = SessionLocal()
    try:
        # Check if user already exists
        user = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).first()
        if not user:
            # Create new user
            user = User(
                telegram_id=str(update.effective_user.id),
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name
            )
            db.add(user)
            db.commit()
    finally:
        db.close()
    
    await update.message.reply_text("Привет! Я бот на базе ChatGPT. Задай мне любой вопрос!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    await update.message.reply_text("Отправь мне любой текст, и я постараюсь на него ответить!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for incoming messages"""
    try:
        # Get the user's message
        user_message = update.message.text
        
        # Call OpenAI API
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        # Extract the response
        bot_response = response.choices[0].message.content
        
        # Save conversation to database
        db = SessionLocal()
        try:
            chat_message = ChatMessage(
                user_id=str(update.effective_user.id),
                message=user_message,
                response=bot_response
            )
            db.add(chat_message)
            db.commit()
        finally:
            db.close()
        
        # Reply to the user
        await update.message.reply_text(bot_response)
    except Exception as e:
        await update.message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

async def setup_bot():
    """Initialize and return the bot application"""
    # Get the bot token from environment variables
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application