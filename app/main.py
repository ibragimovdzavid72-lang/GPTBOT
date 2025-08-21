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
    await init_http()
    await db_safe_connect(DATABASE_URL)
    try:
        yield
    finally:
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
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    if TELEGRAM_WEBHOOK_TOKEN:
        if request.headers.get("x-telegram-bot-api-secret-token") != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)

    try:
        raw = await request.body()
        update = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return JSONResponse({"ok": True})

    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})
