# app.py
import os
import logging
import asyncio
from typing import Any, Dict, Optional, Deque, Set
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import httpx

# =========================
# Config & Logging
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")             # обязателен
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN")  # для X-Telegram-Bot-Api-Secret-Token
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")                 # например: https://gptbot-production-xxxx.up.railway.app
ADMIN_IDS = {
    int(x.strip()) for x in (os.getenv("ADMIN_IDS") or "").replace(",", " ").split() if x.strip().isdigit()
}

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set (use a strong random value)")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# =========================
# HTTP client (shared)
# =========================
http: Optional[httpx.AsyncClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(
        base_url=TG_API,
        timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0),  # быстрее 10с лимита Telegram
        headers={"Accept": "application/json"},
    )
    # Авто-регистрация вебхука (опционально)
    if WEBHOOK_BASE:
        try:
            url = f"{WEBHOOK_BASE.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
            payload = {
                "url": url,
                # Telegram проверит этот заголовок на входе
                "secret_token": TELEGRAM_WEBHOOK_TOKEN or "",
                # рекомендуемый максимум — меньше 10 МБ для фото/доков
                "max_connections": 40,
                "allowed_updates": ["message", "edited_message", "callback_query", "channel_post"],
                "drop_pending_updates": False,
            }
            r = await http.post("/setWebhook", json=payload)
            if r.is_error or not r.json().get("ok"):
                log.warning("setWebhook failed: %s %s", r.status_code, r.text)
            else:
                log.info("Webhook set to %s", url)
        except Exception as e:
            log.warning("setWebhook exception: %s", e)

    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# =========================
# Dedup updates (in-memory LRU)
# =========================
MAX_SEEN = 4096
_seen: Set[int] = set()
_queue: Deque[int] = deque(maxlen=MAX_SEEN)

def seen_update(update_id: Optional[int]) -> bool:
    if update_id is None:
        return False
    if update_id in _seen:
        return True
    _seen.add(update_id)
    _queue.append(update_id)
    if len(_seen) > MAX_SEEN:
        oldest = _queue.popleft()
        _seen.discard(oldest)
    return False

# =========================
# Telegram helpers
# =========================
async def tg_request(method: str, payload: Dict[str, Any], *, retries: int = 2) -> Optional[Dict[str, Any]]:
    """
    Универсальный вызов методов Telegram с мягкими ретраями на сетевые ошибки/5xx.
    """
    assert http is not None
    delay = 0.5
    for attempt in range(retries + 1):
        try:
            r = await http.post(f"/{method}", json=payload)
            if r.is_error:
                # 4xx — без ретраев, 5xx — с ретраями
                if 500 <= r.status_code < 600 and attempt < retries:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                log.error("%s %s: %s", method, r.status_code, r.text)
                return None
            data = r.json()
            if not data.get("ok", False):
                log.error("%s not ok: %s", method, data)
                return None
            return data.get("result")
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            log.exception("%s timeout after retries", method)
            return None
        except Exception:
            log.exception("%s failed", method)
            return None

async def tg_send_message(
    chat_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
):
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await tg_request("sendMessage", payload)

def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def default_keyboard() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "ℹ️ Помощь"}, {"text": "🖼️ Картинка"}],
            [{"text": "🟢 Включить бота"}, {"text": "🔴 Выключить бота"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True,
    }

# =========================
# Routes
# =========================
@app.get("/health")
async def health():
    return {"ok": True, "service": "gptbot", "version": "1.2.0"}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # 1) Путь с секретом — 404, чтобы не раскрывать эндпоинт
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    # 2) Проверка Telegram secret header (если настроен при setWebhook)
    if TELEGRAM_WEBHOOK_TOKEN:
        header = request.headers.get("x-telegram-bot-api-secret-token")
        if header != TELEGRAM_WEBHOOK_TOKEN:
            # намеренно без подробностей
            raise HTTPException(status_code=403, detail="Forbidden")

    # 3) Тип контента
    if "application/json" not in (request.headers.get("content-type") or ""):
        return JSONResponse({"ok": True})

    # 4) Читаем тело быстро, со страховкой по таймауту — чтобы избежать 15s/502 на Railway
    try:
        raw = await asyncio.wait_for(request.body(), timeout=2.0)
    except asyncio.TimeoutError:
        # не держим коннект — возвращаем 200, Telegram ретрайнёт с тем же update_id
        log.warning("Webhook body read timeout")
        return PlainTextResponse("OK", status_code=200)

    if not raw:
        return JSONResponse({"ok": True})

    # 5) Парсим JSON (без лишней возни)
    try:
        # orjson быстрее, но опционально
        try:
            import orjson  # type: ignore
            update = orjson.loads(raw)
        except Exception:
            import json
            update = json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("Webhook got non-JSON payload")
        return JSONResponse({"ok": True})

    # 6) Дедуп по update_id — если повтор, сразу 200
    if seen_update(update.get("update_id")):
        return JSONResponse({"ok": True})

    # 7) Уходим в фон и мгновенно отвечаем 200
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})

# =========================
# Core logic
# =========================
async def handle_update(update: Dict[str, Any]):
    try:
        callback = update.get("callback_query")
        msg = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
        )

        if callback:
            chat_id = callback["message"]["chat"]["id"]
            data = (callback.get("data") or "").strip()
            await tg_send_message(chat_id, f"Callback: <code>{escape_html(data)}</code>")
            return

        if not msg:
            return

        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            return

        text = (msg.get("text") or "").strip()
        normalized = text.casefold()

        # Команды
        if normalized in ("/start", "start"):
            await tg_send_message(
                chat_id,
                "✅ Бот на Railway слушает вебхук.\nНапишите любой текст — я отвечу.",
                reply_markup=default_keyboard(),
            )
            return

        if normalized in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "Доступно:\n• /start — проверить работу\n• Напишите текст — эхо-ответ\n• «🖼️ Картинка» — заглушка",
                reply_markup=default_keyboard(),
            )
            return

        if normalized in ("🖼️ картинка", "картинка"):
            await tg_send_message(chat_id, "Заглушка генерации изображений (подключим позже).")
            return

        if normalized in ("🟢 включить бота", "включить бота"):
            # TODO: сохранить флаг on (Redis/БД)
            await tg_send_message(chat_id, "🟢 Бот включён.")
            return

        if normalized in ("🔴 выключить бота", "выключить бота"):
            # TODO: сохранить флаг off (Redis/БД)
            await tg_send_message(chat_id, "🔴 Бот выключён.")
            return

        # Приватные команды для админов (пример)
        if normalized.startswith("/broadcast ") and chat_id in ADMIN_IDS:
            # TODO: разослать по списку chat_id из БД
            await tg_send_message(chat_id, "🛰️ Рассылка запланирована.")
            return

        # Fallback: эхо
        await tg_send_message(chat_id, f"Я получил: <b>{escape_html(text)}</b>", reply_markup=default_keyboard())

    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("handle_update failed")

# =========================
# Optional root (для быстрого пинга)
# =========================
@app.get("/")
async def root():
    return PlainTextResponse("OK")
