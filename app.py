# app.py
import os
import sys
import json
import time
import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional, Deque, Set, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

# =========================
# Structured logging
# =========================
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": int(time.time() * 1000),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("gptbot")
log.setLevel(logging.INFO)
log.handlers[:] = [handler]

# =========================
# Env
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # обязателен
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN")  # для заголовка
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")  # https://xxx.up.railway.app
ADMIN_IDS = {
    int(x) for x in (os.getenv("ADMIN_IDS") or "").replace(",", " ").split() if x.isdigit()
}

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Параметры фоновых воркеров
WORKERS = int(os.getenv("WORKERS", "4"))         # кол-во фоновых задач
QUEUE_MAX = int(os.getenv("QUEUE_MAX", "2048"))  # длина очереди
HTTP_READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "8.0"))
HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "5.0"))

# =========================
# Globals
# =========================
http: Optional[httpx.AsyncClient] = None
queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=QUEUE_MAX)
workers: List[asyncio.Task] = []
app_started_at = time.time()

# Дедуп апдейтов
MAX_SEEN = 4096
_seen: Set[int] = set()
_order: Deque[int] = deque(maxlen=MAX_SEEN)

def seen_update(update_id: Optional[int]) -> bool:
    if update_id is None:
        return False
    if update_id in _seen:
        return True
    _seen.add(update_id)
    _order.append(update_id)
    if len(_seen) > MAX_SEEN:
        oldest = _order.popleft()
        _seen.discard(oldest)
    return False

# Простейшие метрики
metrics = {
    "updates_total": 0,
    "updates_deduped_total": 0,
    "updates_enqueued_total": 0,
    "updates_processed_total": 0,
    "tg_errors_total": 0,
}

# =========================
# Lifespan
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http, workers
    http = httpx.AsyncClient(
        base_url=TG_API,
        http2=True,
        timeout=httpx.Timeout(connect=HTTP_CONNECT_TIMEOUT, read=HTTP_READ_TIMEOUT, write=5.0, pool=5.0),
        headers={"Accept": "application/json"},
    )

    # Автосет вебхука (опционально)
    if WEBHOOK_BASE:
        try:
            url = f"{WEBHOOK_BASE.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
            payload = {
                "url": url,
                "secret_token": TELEGRAM_WEBHOOK_TOKEN or "",
                "max_connections": 40,
                "allowed_updates": ["message", "edited_message", "callback_query", "channel_post"],
            }
            r = await http.post("/setWebhook", json=payload)
            ok = not r.is_error and r.json().get("ok")
            log.info(f"setWebhook ok={ok}, url={url}")
        except Exception:
            log.exception("setWebhook failed")

    # Запуск фоновых воркеров
    workers = [asyncio.create_task(worker_loop(i)) for i in range(WORKERS)]
    try:
        yield
    finally:
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# =========================
# Helpers
# =========================
def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def default_keyboard() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "ℹ️ Помощь"}, {"text": "🖼️ Картинка"}],
            [{"text": "🟢 Включить бота"}, {"text": "🔴 Выключить бота"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
    }

async def tg_request(method: str, payload: Dict[str, Any], *, retries: int = 2) -> Optional[Dict[str, Any]]:
    """Вызов Telegram API с мягкими ретраями."""
    assert http is not None
    delay = 0.5
    for attempt in range(retries + 1):
        try:
            r = await http.post(f"/{method}", json=payload)
            if r.is_error:
                if 500 <= r.status_code < 600 and attempt < retries:
                    await asyncio.sleep(delay); delay *= 2; continue
                metrics["tg_errors_total"] += 1
                log.error(f"{method} {r.status_code}: {r.text}")
                return None
            data = r.json()
            if not data.get("ok", False):
                metrics["tg_errors_total"] += 1
                log.error(f"{method} not ok: {data}")
                return None
            return data.get("result")
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt < retries:
                await asyncio.sleep(delay); delay *= 2; continue
            metrics["tg_errors_total"] += 1
            log.exception(f"{method} timeout/network after retries")
            return None
        except Exception:
            metrics["tg_errors_total"] += 1
            log.exception(f"{method} failed")
            return None

async def tg_send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await tg_request("sendMessage", payload)

# =========================
# Web routes
# =========================
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    uptime = int(time.time() - app_started_at)
    return {
        "ok": True,
        "service": "gptbot",
        "version": "2.0.0",
        "uptime_s": uptime,
        "queue_size": queue.qsize(),
        "workers": WORKERS,
    }

@app.get("/ready")
async def ready():
    # простая проверка готовности HTTP-клиента
    return {"ready": http is not None}

@app.get("/metrics")
async def prometheus_metrics():
    # минимальный Prometheus exposition
    lines = [
        "# HELP gptbot_updates_total Total updates received",
        "# TYPE gptbot_updates_total counter",
        f"gptbot_updates_total {metrics['updates_total']}",
        "# HELP gptbot_updates_deduped_total Updates dropped as duplicates",
        "# TYPE gptbot_updates_deduped_total counter",
        f"gptbot_updates_deduped_total {metrics['updates_deduped_total']}",
        "# HELP gptbot_updates_enqueued_total Updates enqueued to workers",
        "# TYPE gptbot_updates_enqueued_total counter",
        f"gptbot_updates_enqueued_total {metrics['updates_enqueued_total']}",
        "# HELP gptbot_updates_processed_total Updates processed by workers",
        "# TYPE gptbot_updates_processed_total counter",
        f"gptbot_updates_processed_total {metrics['updates_processed_total']}",
        "# HELP gptbot_tg_errors_total Telegram API errors",
        "# TYPE gptbot_tg_errors_total counter",
        f"gptbot_tg_errors_total {metrics['tg_errors_total']}",
        "# HELP gptbot_queue_current Current queue size",
        "# TYPE gptbot_queue_current gauge",
        f"gptbot_queue_current {queue.qsize()}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # 1) Путь с секретом — 404 (не палим эндпоинт)
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    # 2) Проверка Telegram secret header
    if TELEGRAM_WEBHOOK_TOKEN:
        header = request.headers.get("x-telegram-bot-api-secret-token")
        if header != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)

    # 3) Тип контента
    if "application/json" not in (request.headers.get("content-type") or ""):
        return JSONResponse({"ok": True})

    # 4) Читаем тело очень быстро, чтобы не словить 15s 502
    try:
        raw = await asyncio.wait_for(request.body(), timeout=2.0)
    except asyncio.TimeoutError:
        log.warning("webhook body read timeout -> immediate 200")
        return JSONResponse({"ok": True})

    if not raw:
        return JSONResponse({"ok": True})

    # 5) Парсим JSON (orjson если доступен)
    try:
        try:
            import orjson  # type: ignore
            update = orjson.loads(raw)
        except Exception:
            update = json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("invalid JSON payload")
        return JSONResponse({"ok": True})

    # 6) Метрики и дедуп
    metrics["updates_total"] += 1
    if seen_update(update.get("update_id")):
        metrics["updates_deduped_total"] += 1
        return JSONResponse({"ok": True})

    # 7) Быстрый ответ и постановка в очередь
    try:
        queue.put_nowait(update)
        metrics["updates_enqueued_total"] += 1
    except asyncio.QueueFull:
        # В крайнем случае — не блокируем вебхук
        log.error("queue full, dropping update")
    return JSONResponse({"ok": True})

# =========================
# Worker logic
# =========================
async def worker_loop(i: int):
    """Постоянный воркер обработки апдейтов."""
    log.info(json.dumps({"msg": "worker start", "id": i}))
    try:
        while True:
            update = await queue.get()
            try:
                await handle_update(update)
            except Exception:
                log.exception("handle_update failed")
            finally:
                metrics["updates_processed_total"] += 1
                queue.task_done()
    except asyncio.CancelledError:
        log.info(json.dumps({"msg": "worker stop", "id": i}))
        raise

async def handle_update(update: Dict[str, Any]):
    """Ядро логики бота."""
    callback = update.get("callback_query")
    msg = update.get("message") or update.get("edited_message") or update.get("channel_post")

    if callback:
        chat_id = callback["message"]["chat"]["id"]
        data = (callback.get("data") or "").strip()
        await tg_send_message(chat_id, f"Callback: <code>{escape_html(data)}</code>")
        return

    if not msg:
        return

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    normalized = text.casefold()

    if normalized in ("/start", "start"):
        await tg_send_message(
            chat_id,
            "✅ Бот на Railway слушает вебхук.\nНапишите любой текст — я отвечу.",
        )
        await tg_send_message(chat_id, "Доступные кнопки на клавиатуре ↓", reply_markup=default_keyboard())
        return

    if normalized in ("ℹ️ помощь", "/help", "help"):
        await tg_send_message(
            chat_id,
            "Доступно:\n• /start — проверить работу\n• Напишите текст — эхо-ответ\n• «🖼️ Картинка» — заглушка\n"
            "• «🟢 Включить бота» / «🔴 Выключить бота»",
            reply_markup=default_keyboard(),
        )
        return

    if normalized in ("🖼️ картинка", "картинка"):
        await tg_send_message(chat_id, "Заглушка генерации изображений (подключим позже).")
        return

    if normalized in ("🟢 включить бота", "включить бота"):
        # TODO: сохранить флаг on в БД/Redis
        await tg_send_message(chat_id, "🟢 Бот включён.")
        return

    if normalized in ("🔴 выключить бота", "выключить бота"):
        # TODO: сохранить флаг off в БД/Redis
        await tg_send_message(chat_id, "🔴 Бот выключён.")
        return

    # Пример административной команды
    if normalized.startswith("/broadcast ") and chat_id in ADMIN_IDS:
        # TODO: рассылка по chat_id из БД
        await tg_send_message(chat_id, "🛰️ Рассылка принята в работу.")
        return

    # Fallback: эхо
    await tg_send_message(chat_id, f"Я получил: <b>{escape_html(text)}</b>")
