import json
import asyncio
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from .settings import WEBHOOK_SECRET, TELEGRAM_WEBHOOK_TOKEN, DATABASE_URL
from .db import db_safe_connect, DB_ENABLED, pg_pool
from .handlers import handle_update

http: httpx.AsyncClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # общий HTTP-клиент (по желанию, если понадобится)
    global http
    http = httpx.AsyncClient(timeout=12.0)
    # попытка подключения к БД (если DATABASE_URL задан)
    await db_safe_connect(DATABASE_URL)
    try:
        yield
    finally:
        await http.aclose()
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
    # проверка секрета из URL
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    # дополнительная проверка заголовка Telegram (если включили TELEGRAM_WEBHOOK_TOKEN)
    if TELEGRAM_WEBHOOK_TOKEN:
        if request.headers.get("x-telegram-bot-api-secret-token") != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)

    # читаем апдейт
    try:
        raw = await request.body()
        update = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return JSONResponse({"ok": True})

    # обрабатываем асинхронно, чтобы webhook отвечал быстро
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})
