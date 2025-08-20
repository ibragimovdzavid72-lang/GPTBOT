import os
import logging
import asyncio
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import httpx
from openai import AsyncOpenAI

# --------- Config ---------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# === Переменные окружения ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supers3cr3t123456")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")          # Chat
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")  # Images

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
http: Optional[httpx.AsyncClient] = None
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Админ и глобальное состояние
ADMIN_IDS = {1752390166}  # замените на свой Telegram ID
BOT_ENABLED = True
CHAT_MODES: Dict[int, str] = {}

# --------- Lifespan ---------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        await http.aclose()

app = FastAPI(lifespan=lifespan)

# --------- Helpers ---------
async def tg_send_message(chat_id: int, text: str, reply_markup: Dict[str, Any] | None = None):
    assert http is not None
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = await http.post(f"{TG_API}/sendMessage", json=payload)
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception as e:
        log.exception("sendMessage failed: %s", e)


def kb_main(is_admin: bool = False) -> Dict[str, Any]:
    kb = {
        "keyboard": [
            [{"text": "💬 Чат с GPT"}, {"text": "🎨 Создать изображение"}],
            [{"text": "ℹ️ Помощь"}],
        ],
        "resize_keyboard": True,
    }
    if is_admin:
        kb["keyboard"].append([{"text": "🛠 Админ-панель"}])
    return kb


def kb_admin() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "🟢 Включить бот"}, {"text": "🔴 Выключить бот"}],
            [{"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
    }

# --------- OpenAI ---------
async def do_chat(chat_id: int, text: str):
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": text}],
        )
        answer = response.choices[0].message.content
        await tg_send_message(chat_id, answer)
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
        image_url = resp.data[0].url
        await tg_send_message(chat_id, f"🖼 <b>Готово!</b>\n{image_url}")
    except Exception as e:
        log.exception("image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: {e}")

# --------- Routes ---------
@app.get("/health")
async def health():
    return {"ok": True}


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

# --------- Main Logic ---------
async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = text.casefold()
        is_admin = chat_id in ADMIN_IDS

        # Если бот выключен
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # --- Команды ---
        if low in ("/start", "start"):
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

        if low in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n\n"
                "• «💬 Чат с GPT» — текст пойдёт в ИИ\n"
                "• «🎨 Создать изображение» — текст = описание картинки\n"
                "• Команда: <code>/image ваш_текст</code>\n",
            )
            return

        # --- Админ-панель ---
        if low in ("/admin", "🛠 админ-панель"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только для администратора.")
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            await tg_send_message(
                chat_id,
                f"🛠 <b>Админ-панель</b>\nСтатус: {status}\nДоступные команды: /on /off",
                reply_markup=kb_admin(),
            )
            return

        if low in ("/on", "🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if low in ("/off", "🔴 выключить бот", "выключить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен.", reply_markup=kb_admin())
            return

        if low in ("⬅️ назад",):
            await tg_send_message(chat_id, "🔙 Возвращаемся в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        # --- Переключение режимов ---
        if low in ("💬 чат с gpt",):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат с GPT")
            return

        if low in ("🎨 создать изображение",):
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: Изображение. Напишите описание.")
            return

        if low.startswith("/image"):
            prompt = text[len("/image"):].strip()
            if not prompt:
                await tg_send_message(chat_id, "📸 Пример: /image закат над морем")
                return
            await do_image(chat_id, prompt)
            return

        # --- В зависимости от режима ---
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(chat_id, text)
        else:
            await do_chat(chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)
