import os
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from .handlers import handle_update
from .settings import WEBHOOK_SECRET, TELEGRAM_WEBHOOK_TOKEN, DATABASE_URL
from .db import db_safe_connect, DB_ENABLED, pg_pool

http: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(timeout=12.0)
    # Подключение к БД
    await db_safe_connect(DATABASE_URL)
    try:
        yield
    finally:
        await http.aclose()
        if DB_ENABLED and pg_pool:
            await pg_pool.close()

app = FastAPI(lifespan=lifespan)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    data = await request.json()
    await handle_update(data, http)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok", "webhook": f"/webhook/{WEBHOOK_SECRET}"}
