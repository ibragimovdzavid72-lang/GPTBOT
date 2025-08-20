# app.py
import os
import json
import base64
import asyncio
import logging
from typing import Any, Dict, Optional, List

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

# ============== LOGGING & CONFIG ==============
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# ---- Задай в Railway Variables либо здесь в дефолтах ----
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "PASTE_TELEGRAM_BOT_TOKEN_HERE")
WEBHOOK_SECRET           = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN   = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")  # можно оставить пустым

OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "")  # добавь ключ, чтобы включить GPT и картинки
OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL       = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")  # или 'dall-e-3'
IMAGE_SIZE               = os.getenv("IMAGE_SIZE", "1024x1024")            # 256x256/512x512/1024x1024

# Админы: список ID через запятую, напр. "123456,987654"
ADMIN_IDS_RAW            = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int]     = [int(x) for x in ADMIN_IDS_RAW.replace(" ", "").split(",") if x.strip().isdigit()]

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_SECRET:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and WEBHOOK_SECRET must be set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# HTTP клиент к Telegram
http: Optional[httpx.AsyncClient] = None

# Состояния
CHAT_MODES: Dict[int, str] = {}        # chat_id -> "chat" | "image"
BOT_ENABLED: bool = True               # глобальный тумблер; админ переключает /on /off

# OpenAI client (async)
try:
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    openai_client = None

# ============== FASTAPI LIFESPAN ==============
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(
        base_url=TG_API,
        timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
        headers={"Accept": "application/json"},
    )
    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# ============== HELPERS (TG) ==============
def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def kb_main(is_admin: bool = False) -> Dict[str, Any]:
    rows = [
        [{"text": "💬 Чат с GPT"}, {"text": "🎨 Создать изображение"}],
        [{"text": "ℹ️ Помощь"}],
    ]
    if is_admin:
        rows.append([{"text": "🛠 Админ-панель"}])
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}

def kb_admin() -> Dict[str, Any]:
    status = "🟢 ВКЛ" if BOT_ENABLED else "🔴 ВЫКЛ"
    return {
        "keyboard": [
            [{"text": "🟢 Включить бот"}, {"text": "🔴 Выключить бот"}],
            [{"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
