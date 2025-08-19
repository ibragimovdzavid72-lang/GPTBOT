# app.py
import os
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import httpx

# -------- Config --------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_SECRET:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and WEBHOOK_SECRET must be set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

http: Optional[httpx.AsyncClient] = None

# -------- FastAPI --------
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(base_url=TG_API, timeout=8.0)
    yield
    await http.aclose()

app = FastAPI(lifespan=lifespan)

# -------- Helpers --------
async def tg_send_message(chat_id: int, text: str):
    try:
        r = await http.post("/sendMessage", json={"chat_id": chat_id, "text": text})
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception as e:
        log.error("sendMessage failed: %s", e)

# -------- Routes --------
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    # читаем тело, но не обрабатываем здесь
    try:
        update = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    # мгновенный ответ Telegram (чтобы не словить 502)
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})

# -------- Logic --------
async def handle_update(update: Dict[str, Any]):
    try:
        msg = update.get("message")
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()

        if text.lower() in ("/start", "start"):
            await tg_send_message(chat_id, "✅ Бот на Railway слушает вебхук.")
        else:
            await tg_send_message(chat_id, f"Эхо: {text}")
    except Exception as e:
        log.error("handle_update error: %s", e)
