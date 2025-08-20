# app.py
import os
import json
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# ---------- Env ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN")  # опционально, если использовали secret_token в setWebhook

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_SECRET:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and WEBHOOK_SECRET must be set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Общий HTTP-клиент к Telegram
http: Optional[httpx.AsyncClient] = None

# ---------- FastAPI ----------
async def lifespan(app: FastAPI):
    """Создаём/закрываем httpx клиент на время жизни приложения."""
    global http
    http = httpx.AsyncClient(
        base_url=TG_API,
        timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0),
        headers={"Accept": "application/json"},
    )
    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# ---------- Helpers ----------
def escape_html(s: str) -> str:
    """Безопасное экранирование под parse_mode=HTML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def tg_send_message(chat_id: int, text: str):
    """Отправка сообщения в Telegram с HTML-разметкой."""
    assert http is not None
    try:
        r = await http.post(
            "/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendMessage failed")

# ---------- Routes ----------
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # 1) Секрет в пути
    if secret != WEBHOOK_SECRET:
        # 404, чтобы не палить эндпоинт
        raise HTTPException(status_code=404)

    # 2) Проверка секретного заголовка Telegram (если использовали при setWebhook)
    if TELEGRAM_WEBHOOK_TOKEN:
        header = request.headers.get("x-telegram-bot-api-secret-token")
        if header != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)

    # 3) Быстро читаем сырое тело и СРАЗУ отвечаем 200
    try:
        raw = await asyncio.wait_for(request.body(), timeout=1.5)
    except asyncio.TimeoutError:
        # никогда не держим соединение — Telegram сам ретрайнёт
        return JSONResponse({"ok": True})

    if not raw:
        return JSONResponse({"ok": True})

    # 4) В фоне разбираем и обрабатываем
    asyncio.create_task(process_raw_update(raw))
    return JSONResponse({"ok": True})

# ---------- Background processing ----------
async def process_raw_update(raw: bytes):
    """Парсим JSON и передаём на обработку. Ошибки не валят вебхук."""
    try:
        # orjson можно подключить, но стандартный json достаточно
        update = json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("invalid JSON payload")
        return

    await handle_update(update)

async def handle_update(update: Dict[str, Any]):
    """Простая логика бота."""
    try:
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = text.casefold()

        # Команды
        if low in ("/start", "start"):
            await tg_send_message(
                chat_id,
                "✅ Бот на Railway слушает вебхук. Напишите любой текст — я отвечу.",
            )
            return

        if low in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "Доступно:\n"
                "• /start — проверка\n"
                "• /pause — поставить бота на паузу (демо)\n"
                "• /image — заглушка генерации изображений\n"
                "• Напишите любой текст — эхо-ответ",
            )
            return

        if low in ("/pause", "pause", "🔴 выключить бота", "выключить бота"):
            await tg_send_message(chat_id, "🔴 Бот поставлен на паузу. (Логику on/off подключим позже.)")
            return

        if low in ("/image", "image", "🖼️ картинка", "картинка"):
            await tg_send_message(chat_id, "🖼️ Генерация изображений пока не подключена. Заглушка.")
            return

        # Эхо
        await tg_send_message(chat_id, f"Я получил: <b>{escape_html(text)}</b>")

    except Exception:
        # важное: строку закрываем корректно — без синтаксических ошибок :)
        log.exception("handle update error")
