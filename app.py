# app.py
import os
import json
import base64
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

# ==================  CONFIG  ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN")  # опционально

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # добавь в Railway, чтобы включить ИИ
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")       # можешь поменять
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1024")             # 256x256, 512x512, 1024x1024

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_SECRET:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and WEBHOOK_SECRET must be set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# HTTP-клиент к Telegram
http: Optional[httpx.AsyncClient] = None

# Память режимов на чат (простая, в ОЗУ, переживает только текущий запуск)
CHAT_MODES: Dict[int, str] = {}  # chat_id -> "chat" | "image"

# ------------------ OpenAI Async client ------------------
try:
    # Новый SDK (openai>=1.0): AsyncOpenAI
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    openai_client = None

# ==================  FASTAPI  ==================
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(
        base_url=TG_API,
        timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        headers={"Accept": "application/json"},
    )
    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# ==================  TG HELPERS  ==================
def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def default_keyboard() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "💬 Чат с GPT"}, {"text": "🎨 Создать изображение"}],
            [{"text": "ℹ️ Помощь"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
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

async def tg_send_photo(chat_id: int, image_bytes: bytes, caption: str | None = None):
    assert http is not None
    try:
        files = {"photo": ("image.png", image_bytes, "image/png")}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        r = await http.post("/sendPhoto", data=data, files=files)
        if r.is_error:
            log.error("sendPhoto %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendPhoto failed")

# ==================  ROUTES  ==================
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # 1) Секрет пути
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    # 2) Проверка заголовка Telegram (если указан при setWebhook)
    if TELEGRAM_WEBHOOK_TOKEN:
        header = request.headers.get("x-telegram-bot-api-secret-token")
        if header != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)
    # 3) Быстро читаем тело и сразу 200
    try:
        raw = await asyncio.wait_for(request.body(), timeout=1.5)
    except asyncio.TimeoutError:
        return JSONResponse({"ok": True})
    if not raw:
        return JSONResponse({"ok": True})
    asyncio.create_task(process_raw_update(raw))
    return JSONResponse({"ok": True})

# ==================  BACKGROUND LOGIC  ==================
async def process_raw_update(raw: bytes):
    try:
        update = json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("invalid JSON payload")
        return
    await handle_update(update)

async def handle_update(update: Dict[str, Any]):
    try:
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = text.casefold()

        # --- Команды/кнопки ---
        if low in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "Я готов работать в двух режимах:\n"
                "• <b>Чат с GPT</b> — отвечаю как ИИ\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Нажмите кнопку ниже или просто напишите сообщение.",
                reply_markup=default_keyboard(),
            )
            await tg_send_message(chat_id, "Выберите действие:", reply_markup=default_keyboard())
            return

        if low in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n\n"
                "• Нажмите «💬 Чат с GPT» — и любой текст пойдёт в ИИ.\n"
                "• Нажмите «🎨 Создать изображение» — и любое сообщение станет описанием для картинки.\n"
                "• Или используйте: <code>/image ваш_описание</code>",
            )
            return

        if low in ("💬 чат с gpt",):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: <b>Чат с GPT</b>. Пишите вопрос — отвечу как ИИ.")
            return

        if low in ("🎨 создать изображение",):
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(
                chat_id,
                "🖼 Режим: <b>Изображение</b>.\n"
                "Опишите, что нарисовать. Пример: <i>кот на скейте в городе</i>.",
            )
            return

        # /image c аргументом — одноразовая генерация
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

        # --- Режимы: chat / image ---
        mode = CHAT_MODES.get(chat_id, "chat")

        if mode == "image":
            # Любой текст — это prompt для картинки
            await do_image(chat_id, text)
            return

        # Иначе — режим chat
        await do_chat(chat_id, text)

    except Exception:
        log.exception("handle update error")

# ==================  CHAT & IMAGE IMPLEMENTATION  ==================
async def do_chat(chat_id: int, user_text: str):
    # Если нет ключа OpenAI — предупреждаем и не падаем
    if not openai_client:
        await tg_send_message(
            chat_id,
            "⚠️ ИИ пока не настроен. Добавьте переменную <b>OPENAI_API_KEY</b> в Railway — и я стану умным 🤖",
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
        if not answer:
            answer = "Извините, не смог сформулировать ответ."
        await tg_send_message(chat_id, escape_html(answer))
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
    # Сообщим пользователю, что работаем
    await tg_send_message(chat_id, f"🎨 Рисую по описанию: <i>{escape_html(prompt)}</i> …")
    try:
        img = await openai_client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=IMAGE_SIZE,
            response_format="b64_json",
        )
        b64 = img.data[0].b64_json
        image_bytes = base64.b64decode(b64)
        await tg_send_photo(chat_id, image_bytes, caption=f"Готово: <i>{escape_html(prompt)}</i>")
    except Exception as e:
        log.exception("openai image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: <code>{escape_html(str(e))}</code>")
