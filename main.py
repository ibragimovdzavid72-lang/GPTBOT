import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.enums.parse_mode import ParseMode

from settings import BOT_TOKEN
from handlers import router  # твои роутеры/хендлеры aiogram v3
from db import init_db       # инициализация БД (create_all)

# --- Конфиг ---
BOT_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123")  # задай в Railway Variables
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")                # https://<имя>.up.railway.app
WEBHOOK_PATH = f"/webhook/{BOT_WEBHOOK_SECRET}"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH}" if PUBLIC_URL else None

# --- FastAPI + aiogram ---
app = FastAPI()
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
dp.include_router(router)

@app.on_event("startup")
async def on_startup():
    # База
    await init_db()

    # Чистим возможный старый вебхук
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    # Ставим новый вебхук, если PUBLIC_URL задан
    if WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL, secret_token=BOT_WEBHOOK_SECRET)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

# Получение апдейтов от Telegram
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != BOT_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    data = await request.json()
    update = Update.model_validate(data)  # Pydantic v2 в aiogram3
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok", "webhook": WEBHOOK_URL or "not set"}
