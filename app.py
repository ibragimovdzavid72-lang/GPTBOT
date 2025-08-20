import os
import logging
import asyncio
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager
import httpx
from openai import AsyncOpenAI

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# ---------- ENV ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Chat & Image models
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")          # чат
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")  # картинки

# Админы: можно задать ENV ADMIN_IDS="111,222", а также ниже задать дефолт (твои ID)
ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x) for x in ADMIN_IDS_ENV.replace(" ", "").split(",") if x.isdigit()]

# добавим твой ID как дефолт/резерв
DEFAULT_ADMIN_IDS = {1752390166}
ADMIN_IDS = list(set(ADMIN_IDS) | DEFAULT_ADMIN_IDS)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ---------- GLOBAL STATE ----------
http: Optional[httpx.AsyncClient] = None
BOT_ENABLED = True
CHAT_MODES: Dict[int, str] = {}  # chat_id -> "chat" | "image"

# ---------- LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(timeout=12.0)
    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# ---------- KEYBOARDS ----------
def kb_main(is_admin: bool = False) -> Dict[str, Any]:
    rows = [
        [{"text": "💬 Чат с GPT"}, {"text": "🎨 Создать изображение"}],
        [{"text": "ℹ️ Помощь"}],
    ]
    if is_admin:
        rows.append([{"text": "🛠 Админ-панель"}])
    return {"keyboard": rows, "resize_keyboard": True}

def kb_admin() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "🟢 Включить бот"}, {"text": "🔴 Выключить бот"}],
            [{"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
    }

# ---------- TG HELPERS ----------
async def tg_send_message(chat_id: int, text: str, reply_markup: Dict[str, Any] | None = None):
    assert http is not None
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = await http.post(f"{TG_API}/sendMessage", json=payload)
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception as e:
        log.exception("sendMessage failed: %s", e)

async def tg_send_photo(chat_id: int, photo_url: str, caption: str = ""):
    assert http is not None
    data: Dict[str, Any] = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    try:
        r = await http.post(f"{TG_API}/sendPhoto", data=data)
        if r.is_error:
            log.error("sendPhoto %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendPhoto failed")

# ---------- OPENAI ----------
async def do_chat(chat_id: int, text: str):
    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": text}],
        )
        out = (resp.choices[0].message.content or "").strip() or "⚠️ Пустой ответ."
        await tg_send_message(chat_id, out)
    except Exception as e:
        log.exception("chat failed")
        await tg_send_message(chat_id, f"❌ Ошибка ИИ: {e}")

async def do_image(chat_id: int, prompt: str):
    try:
        resp = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
        )
        url = resp.data[0].url
        await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
    except Exception as e:
        log.exception("image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: {e}")

# ---------- HANDLER ----------
async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        # В некоторых клиентах ключ может называться "from" (зарезервированное слово — но это dict-ключ, все ок)
        user_id = (msg.get("from") or {}).get("id")
        text = (msg.get("text") or "").strip()
        low = text.casefold()

        # Нормализация команды: "/admin@BotName arg" -> "/admin"
        cmd = ""
        if low.startswith("/"):
            first = low.split()[0]          # "/admin@BotName"
            cmd = first.split("@", 1)[0]    # "/admin"

        is_admin = bool(user_id and int(user_id) in ADMIN_IDS)

        # Диагностика
        if cmd == "/whoami":
            await tg_send_message(
                chat_id,
                "🔎 Диагностика\n"
                f"user_id: <code>{user_id}</code>\n"
                f"chat_id: <code>{chat_id}</code>\n"
                f"admins: <code>{ADMIN_IDS}</code>\n"
                f"cmd: <code>{cmd}</code>\n"
                f"text: <code>{text}</code>"
            )
            return

        # Если бот выключен и пишет не админ
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # ----- Команды -----
        if cmd in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "🟢 Доступные режимы:\n"
                "• <b>Чат с GPT</b> — отвечаю как ИИ\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Выберите режим кнопкой или просто напишите сообщение.",
                reply_markup=kb_main(is_admin=is_admin),
            )
            return

        if cmd in ("/help",) or low in ("ℹ️ помощь", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n\n"
                "• «💬 Чат с GPT» — текст пойдёт в ИИ\n"
                "• «🎨 Создать изображение» — текст = описание картинки\n",
            )
            return

        # ----- Админка -----
        if cmd == "/admin" or low == "🛠 админ-панель":
            if not is_admin:
                await tg_send_message(
                    chat_id,
                    "🚫 Только для администратора.\n"
                    f"(Я вижу user_id=<code>{user_id}</code>. Админы: <code>{ADMIN_IDS}</code>)"
                )
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            await tg_send_message(
                chat_id,
                f"🛠 <b>Админ-панель</b>\nСтатус: {status}\nДоступные команды: /on /off",
                reply_markup=kb_admin(),
            )
            return

        if cmd == "/on" or low in ("🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if cmd == "/off" or low in ("🔴 выключить бот", "выключить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен.", reply_markup=kb_admin())
            return

        if low == "⬅️ назад":
            await tg_send_message(chat_id, "🔙 Возвращаемся в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        # ----- Переключение режимов -----
        if low == "💬 чат с gpt":
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат с GPT")
            return

        if low == "🎨 создать изображение":
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: Изображение. Напишите описание.")
            return

        # ----- /image -----
        if cmd == "/image" or low.startswith("/image "):
            parts = text.split(maxsplit=1)
            prompt = parts[1] if len(parts) > 1 else ""
            if not prompt:
                await tg_send_message(chat_id, "📸 Пример: /image закат над морем")
                return
            await do_image(chat_id, prompt)
            return

        # ----- По режиму -----
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(chat_id, text)
        else:
            await do_chat(chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)

# ---------- ROUTES ----------
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True, "enabled": BOT_ENABLED, "admins": ADMIN_IDS}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    try:
        update = await request.json()
    except Exception:
        log.warning("Non-JSON update")
        return JSONResponse({"ok": True})

    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})
