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

# ---- значения задавай в Railway → Variables (или оставь тут дефолты для локалки) ----
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "PASTE_TELEGRAM_BOT_TOKEN_HERE")
WEBHOOK_SECRET           = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN   = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")  # можно пусто

OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL       = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")  # или "dall-e-3"
IMAGE_SIZE               = os.getenv("IMAGE_SIZE", "1024x1024")

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
    return {
        "keyboard": [
            [{"text": "🟢 Включить бот"}, {"text": "🔴 Выключить бот"}],
            [{"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }

async def tg_send_message(chat_id: int, text: str, reply_markup: Dict[str, Any] | None = None):
    assert http is not None
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = await http.post("/sendMessage", json=payload)
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendMessage failed")

async def tg_send_photo_bytes(chat_id: int, image_bytes: bytes, caption: str | None = None):
    assert http is not None
    try:
        files = {"photo": ("image.png", image_bytes, "image/png")}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        r = await http.post("/sendPhoto", data=data, files=files)
        if r.is_error:
            log.error("sendPhoto(bytes) %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendPhoto(bytes) failed")

async def tg_send_photo_url(chat_id: int, url: str, caption: str | None = None):
    assert http is not None
    try:
        data = {"chat_id": str(chat_id), "photo": url}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        r = await http.post("/sendPhoto", data=data)
        if r.is_error:
            log.error("sendPhoto(url) %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendPhoto(url) failed")

# ============== ROUTES ==============
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True, "enabled": BOT_ENABLED}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    if TELEGRAM_WEBHOOK_TOKEN:
        header = request.headers.get("x-telegram-bot-api-secret-token")
        if header != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)
    try:
        raw = await asyncio.wait_for(request.body(), timeout=1.5)
    except asyncio.TimeoutError:
        return JSONResponse({"ok": True})
    if not raw:
        return JSONResponse({"ok": True})
    asyncio.create_task(process_raw_update(raw))
    return JSONResponse({"ok": True})

# ============== BACKGROUND ==============
async def process_raw_update(raw: bytes):
    try:
        update = json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("invalid JSON payload")
        return
    await handle_update(update)

async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED  # объявляем сразу в начале функции
    try:
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = text.casefold()
        is_admin = chat_id in ADMIN_IDS

        # --- Глобальный тумблер ---
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # --- Команды/кнопки ---
        if low in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "Режимы:\n"
                "• <b>Чат с GPT</b> — отвечаю как ИИ\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Выберите кнопкой ниже или просто напишите сообщение.",
                reply_markup=kb_main(is_admin=is_admin),
            )
            await tg_send_message(chat_id, "Выберите действие:", reply_markup=kb_main(is_admin=is_admin))
            return

        if low in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n\n"
                "• «💬 Чат с GPT» — текст пойдёт в ИИ\n"
                "• «🎨 Создать изображение» — текст = описание картинки\n"
                "• Команда: <code>/image ваш_описание</code>\n"
                "• Админ: /on /off /admin",
            )
            return

        # ----- Админ-панель -----
        if low in ("/admin", "🛠 админ-панель"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Доступ только для администратора.")
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            await tg_send_message(
                chat_id,
                f"🛠 <b>Админ-панель</b>\nСтатус бота: {status}\nКоманды: /on, /off",
                reply_markup=kb_admin(),
            )
            return

        if low in ("/on", "🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только админ может включать бота.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if low in ("/off", "🔴 выключить бот", "выключить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только админ может выключать бота.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен для пользователей.", reply_markup=kb_admin())
            return

        if low in ("⬅️ назад",):
            await tg_send_message(chat_id, "Возвращаемся в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        # ----- Переключатели режимов -----
        if low in ("💬 чат с gpt",):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: <b>Чат с GPT</b>. Пишите вопрос — отвечу как ИИ.")
            return

        if low in ("🎨 создать изображение",):
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: <b>Изображение</b>. Опишите, что нарисовать.")
            return

        # ----- /image одноразовая -----
        if low.startswith("/image"):
            prompt = text[len("/image"):].strip()
            if not prompt:
                await tg_send_message(
                    chat_id,
                    "📸 Формат: <code>/image красивый закат над морем</code>\n"
                    "Или включите режим «🎨 Создать изображение» и просто напишите описание.",
                )
                return
            await do_image(chat_id, prompt)
            return

        # ----- Режимы -----
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(chat_id, text)
            return

        await do_chat(chat_id, text)

    except Exception:
        log.exception("handle update error")

# ============== CHAT & IMAGE ==============
async def do_chat(chat_id: int, user_text: str):
    if not openai_client:
        await tg_send_message(
            chat_id,
            "⚠️ ИИ не настроен. Добавьте переменную <b>OPENAI_API_KEY</b> в Railway.",
        )
        return
    try:
        resp = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Вы полезный ассистент. Отвечайте кратко и по делу."},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
            max_tokens=700,
        )
        answer = (resp.choices[0].message.content or "").strip()
        await tg_send_message(chat_id, escape_html(answer) or "Извините, не смог сформулировать ответ.")
    except Exception as e:
        log.exception("openai chat failed")
        await tg_send_message(chat_id, f"❌ Ошибка ИИ: <code>{escape_html(str(e))}</code>")

async def do_image(chat_id: int, prompt: str):
    if not openai_client:
        await tg_send_message(
            chat_id,
            "⚠️ Генерация изображений не настроена. Добавьте <b>OPENAI_API_KEY</b> в Railway.",
        )
        return
    await tg_send_message(chat_id, f"🎨 Рисую по описанию: <i>{escape_html(prompt)}</i> …")
    try:
        # Без response_format — совместимо с текущими API.
        img = await openai_client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=IMAGE_SIZE,
        )
        # Универсально: пробуем b64 или url
        data0 = img.data[0]
        b64 = getattr(data0, "b64_json", None) or (data0.get("b64_json") if isinstance(data0, dict) else None)
        url = getattr(data0, "url", None) or (data0.get("url") if isinstance(data0, dict) else None)

        if b64:
            image_bytes = base64.b64decode(b64)
            await tg_send_photo_bytes(chat_id, image_bytes, caption=f"Готово: <i>{escape_html(prompt)}</i>")
        elif url:
            await tg_send_photo_url(chat_id, url, caption=f"Готово: <i>{escape_html(prompt)}</i>")
        else:
            await tg_send_message(chat_id, "❌ Не получил картинку от модели.")
    except Exception as e:
        log.exception("openai image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: <code>{escape_html(str(e))}</code>")
