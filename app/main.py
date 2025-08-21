import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from .settings import WEBHOOK_SECRET, TELEGRAM_WEBHOOK_TOKEN, DATABASE_URL
from .db import db_safe_connect, DB_ENABLED, pg_pool
from .tg import init_http, close_http
from .handlers import handle_update

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Инициализируем HTTP-клиент для Telegram (tg.py)
    await init_http()
    # 2) Подключаемся к БД (если задан DATABASE_URL)
    await db_safe_connect(DATABASE_URL)
    try:
        yield
    finally:
        # 3) Корректно закрываем HTTP-клиент и пул БД
        await close_http()
        if DB_ENABLED and pg_pool:
            await pg_pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True, "db": DB_ENABLED}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # Проверяем секрет в URL
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    # Доп. защита: проверяем секретный заголовок Telegram (если задан)
    if TELEGRAM_WEBHOOK_TOKEN:
        if request.headers.get("x-telegram-bot-api-secret-token") != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)

    # Читаем апдейт
    try:
        raw = await request.body()
        update = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        # На странный JSON просто отвечаем ok, не падаем
        return JSONResponse({"ok": True})

    # Обрабатываем асинхронно, чтобы webhook отвечал мгновенно
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})
