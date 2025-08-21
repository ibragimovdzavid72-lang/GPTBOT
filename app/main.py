import json, asyncio, logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager

from .settings import WEBHOOK_SECRET, TELEGRAM_WEBHOOK_TOKEN
from .tg import init_http, close_http
from .db import db_safe_connect, DB_ENABLED
from .handlers import handle_update

log=logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http()
    await db_safe_connect()
    yield
    await close_http()

app=FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok":True,"db":DB_ENABLED}

@app.post("/webhook/{secret}")
async def webhook(secret:str,request:Request):
    if secret!=WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    if TELEGRAM_WEBHOOK_TOKEN:
        if request.headers.get("x-telegram-bot-api-secret-token")!=TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)
    raw=await request.body()
    update=json.loads(raw.decode("utf-8")) if raw else {}
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok":True})
