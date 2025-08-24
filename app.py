import os
import asyncio
from fastapi import FastAPI
from telegram_bot import setup_bot
import uvicorn
from database import init_db

app = FastAPI()

# Health check endpoint for Railway
@app.get("/")
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Global variable to store the bot application
bot_app = None

@app.on_event("startup")
async def startup_event():
    global bot_app
    # Initialize the database
    init_db()
    
    # Initialize the Telegram bot
    bot_app = await setup_bot()
    
    # Start the bot in a separate task
    asyncio.create_task(bot_app.run_polling())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)