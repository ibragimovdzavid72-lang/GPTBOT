import os
import json
import asyncio
from typing import Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ---------- ENV ----------
BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
WEBHOOK_BASE    = os.getenv("WEBHOOK_BASE", "")       # https://gptbot-....up.railway.app
WEBHOOK_SECRET  = os.getenv("WEBHOOK_SECRET", "supersecret123456")
ADMIN_IDS       = [i.strip() for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
IMAGES_ENABLED  = os.getenv("IMAGES_ENABLED", "true").lower() == "true"
IMAGE_SIZE      = os.getenv("IMAGE_SIZE", "1024x1024")

if not (BOT_TOKEN and OPENAI_API_KEY and WEBHOOK_BASE and WEBHOOK_SECRET):
    raise RuntimeError("Some of TELEGRAM_BOT_TOKEN / OPENAI_API_KEY / WEBHOOK_BASE / WEBHOOK_SECRET are not set")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")  # совместимо с images.generate

# ---------- STATE (в памяти, без БД) ----------
# Глобальная пауза (вкл/выкл бот). Только админы могут менять.
STATE: Dict[str, Any] = {
    "paused": False,            # если True — бот молчит (кроме админов/команд)
    "images_enabled": IMAGES_ENABLED
}

# Память переписки по chat_id (храним последние N сообщений)
MEMORY: Dict[str, List[Dict[str, str]]] = {}
MAX_MEM = 20

# Персональные настройки по чату: память вкл/выкл, картинки вкл/выкл
CHAT_FLAGS: Dict[str, Dict[str, Any]] = {}  # {chat_id: {"memory":True, "images":True}}

# ---------- APP ----------
app = FastAPI(title="Telegram GPT Bot")

# ---------- UI / КНОПКИ ----------
def main_menu_kb(chat_id: str) -> Dict[str, Any]:
    flags = CHAT_FLAGS.setdefault(chat_id, {"memory": True, "images": STATE["images_enabled"]})
    memory_label = "🧠 Память: ВКЛ" if flags["memory"] else "🧠 Память: ВЫКЛ"
    images_label = "🖼 Картинки: ВКЛ" if flags["images"] else "🖼 Картинки: ВЫКЛ"

    rows = [
        [
            {"text": "🧠 Память", "callback_data": "toggle:memory"},
            {"text": "🖼 Картинки", "callback_data": "toggle:images"},
        ],
        [
            {"text": "📜 Помощь", "callback_data": "help"},
            {"text": "🧹 Очистить память", "callback_data": "clear_mem"},
        ],
    ]

    # Админ-кнопки
    if flags and "admin" in flags or False:  # флаг не используем; проверим по списку ADMIN_IDS ниже
        pass

    return {
        "inline_keyboard": rows
    }

ADMIN_KB = {
    "inline_keyboard": [
        [
            {"text": "⏸ Пауза", "callback_data": "admin:pause"},
            {"text": "▶️ Резюмe", "callback_data": "admin:resume"},
        ],
        [
            {"text": "⚙️ Статус", "callback_data": "admin:status"},
            {"text": "🚿 Сброс вебхука", "callback_data": "admin:reset_webhook"},
        ]
    ]
}

# ---------- OPENAI ----------
# используем официальный клиент new-style
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

async def ai_answer(chat_id: str, user_text: str) -> str:
    """Ответ через OpenAI с простой памятью (если включена)."""
    flags = CHAT_FLAGS.setdefault(chat_id, {"memory": True, "images": STATE["images_enabled"]})
    history = MEMORY.setdefault(chat_id, [])

    msgs = []
    if flags["memory"] and history:
        msgs.extend(history[-MAX_MEM:])

    msgs.append({"role": "user", "content": user_text})

    # запрос
    resp = await asyncio.to_thread(
        client.chat.completions.create,
        model=OPENAI_CHAT_MODEL,
        messages=msgs
    )
    text = resp.choices[0].message.content.strip()

    # обновляем память
    if flags["memory"]:
        history.extend([{"role": "user", "content": user_text},
                        {"role": "assistant", "content": text}])
        if len(history) > MAX_MEM:
            del history[:-MAX_MEM]

    return text

async def ai_image(prompt: str, size: str = IMAGE_SIZE) -> Optional[str]:
    """Генерация картинки (возвращает URL) — требует активного биллинга в OpenAI."""
    try:
        resp = await asyncio.to_thread(
            client.images.generate,
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=size
        )
        return resp.data[0].url
    except Exception as e:
        # Лог в консоль для Railway
        print("Image error:", repr(e))
        return None

# ---------- TELEGRAM API ----------
async def tg_send_text(chat_id: str, text: str, reply_markup: Optional[Dict]=None, parse_mode: Optional[str]="HTML"):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient(timeout=30) as cl:
        r = await cl.post(f"{TG_API}/sendMessage", data=payload)
        if r.status_code != 200:
            print("sendMessage error:", r.text)

async def tg_send_photo(chat_id: str, photo_url: str, caption: Optional[str]=None):
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    async with httpx.AsyncClient(timeout=60) as cl:
        r = await cl.post(f"{TG_API}/sendPhoto", data=payload)
        if r.status_code != 200:
            print("sendPhoto error:", r.text)

async def tg_answer_cb(cb_id: str, text: Optional[str] = None, show_alert: bool=False):
    payload = {"callback_query_id": cb_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    async with httpx.AsyncClient(timeout=15) as cl:
        await cl.post(f"{TG_API}/answerCallbackQuery", data=payload)

async def set_my_commands():
    cmds = [
        {"command": "start", "description": "Открыть меню"},
        {"command": "help",  "description": "Как пользоваться"},
        {"command": "image", "description": "Создать картинку по описанию"},
        {"command": "pause", "description": "Поставить бота на паузу (админ)"},
        {"command": "resume","description": "Снять паузу (админ)"},
    ]
    async with httpx.AsyncClient(timeout=15) as cl:
        await cl.post(f"{TG_API}/setMyCommands", json={"commands": cmds})

# ---------- WEBHOOK ----------
async def set_webhook():
    url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.post(f"{TG_API}/setWebhook", data={"url": url})
        print("setWebhook:", r.text)

async def delete_webhook():
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.post(f"{TG_API}/deleteWebhook")
        print("deleteWebhook:", r.text)

# ---------- FASTAPI ROUTES ----------
@app.get("/health")
async def health():
    return {"ok": True, "paused": STATE["paused"]}

@app.on_event("startup")
async def on_startup():
    print("Starting up...")
    await set_webhook()
    await set_my_commands()

@app.on_event("shutdown")
async def on_shutdown():
    print("Shutting down...")
    await delete_webhook()

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    update = await request.json()
    # Лог в Railway (видно в Deploy/HTTP logs)
    print("UPDATE:", json.dumps(update, ensure_ascii=False))

    # callback_buttons
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        from_id = str(cb["from"]["id"])
        chat_id = str(cb["message"]["chat"]["id"])
        data = cb.get("data", "")

        # админ?
        is_admin = from_id in ADMIN_IDS

        if data == "toggle:memory":
            flags = CHAT_FLAGS.setdefault(chat_id, {"memory": True, "images": STATE["images_enabled"]})
            flags["memory"] = not flags["memory"]
            await tg_answer_cb(cb_id, f"Память: {'ВКЛ' if flags['memory'] else 'ВЫКЛ'}")
        elif data == "toggle:images":
            flags = CHAT_FLAGS.setdefault(chat_id, {"memory": True, "images": STATE["images_enabled"]})
            flags["images"] = not flags["images"]
            await tg_answer_cb(cb_id, f"Картинки: {'ВКЛ' if flags['images'] else 'ВЫКЛ'}")
        elif data == "clear_mem":
            MEMORY[chat_id] = []
            await tg_answer_cb(cb_id, "Память чата очищена.")
        elif data == "help":
            await tg_answer_cb(cb_id, "Пиши текст — отвечу. Кнопка «Картинки» включает генерацию изображений по описанию или командой /image.")
        elif data == "admin:pause":
            if is_admin:
                STATE["paused"] = True
                await tg_answer_cb(cb_id, "Бот поставлен на паузу ✅", show_alert=True)
            else:
                await tg_answer_cb(cb_id, "Только для админа", show_alert=True)
        elif data == "admin:resume":
            if is_admin:
                STATE["paused"] = False
                await tg_answer_cb(cb_id, "Пауза снята ✅", show_alert=True)
            else:
                await tg_answer_cb(cb_id, "Только для админа", show_alert=True)
        elif data == "admin:status":
            if is_admin:
                chats = len(MEMORY)
                paused = STATE["paused"]
                await tg_answer_cb(cb_id, f"Статус: paused={paused}, памяти по чатам={chats}", show_alert=True)
            else:
                await tg_answer_cb(cb_id, "Только для админа", show_alert=True)
        elif data == "admin:reset_webhook":
            if is_admin:
                await delete_webhook()
                await set_webhook()
                await tg_answer_cb(cb_id, "Вебхук перезадан ✅", show_alert=True)
            else:
                await tg_answer_cb(cb_id, "Только для админа", show_alert=True)
        else:
            await tg_answer_cb(cb_id, "Ок")

        # Обновим меню (перерисовка)
        await tg_send_text(chat_id, "Меню обновлено. Выбирай:", reply_markup=main_menu_kb(chat_id))
        return JSONResponse({"ok": True})

    # обычное сообщение
    if "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        from_id = str(msg["from"]["id"])
        text = msg.get("text", "") or ""
        is_admin = from_id in ADMIN_IDS

        # /start
        if text.startswith("/start"):
            welcome = (
                "<b>Привет!</b> Я GPT-бот с памятью, картинками и админ-кнопками.\n\n"
                "Пиши сообщение — отвечу. Кнопки снизу помогут включить память, картинки и управление."
            )
            await tg_send_text(chat_id, welcome, reply_markup=main_menu_kb(chat_id))
            # если админ — показать панель
            if is_admin:
                await tg_send_text(chat_id, "<b>Админ-панель</b>", reply_markup=ADMIN_KB)
            return {"ok": True}

        # help
        if text.startswith("/help"):
            await tg_send_text(chat_id, "Команды: /start, /help, /image <описание>, /pause (админ), /resume (админ)")
            return {"ok": True}

        # admin pause/resume
        if text.startswith("/pause"):
            if is_admin:
                STATE["paused"] = True
                await tg_send_text(chat_id, "Пауза включена ✅")
            else:
                await tg_send_text(chat_id, "Команда только для админа.")
            return {"ok": True}

        if text.startswith("/resume"):
            if is_admin:
                STATE["paused"] = False
                await tg_send_text(chat_id, "Пауза снята ✅")
            else:
                await tg_send_text(chat_id, "Команда только для админа.")
            return {"ok": True}

        # если пауза — не отвечаем (кроме админов)
        if STATE["paused"] and not is_admin:
            return {"ok": True}

        # /image
        if text.startswith("/image"):
            prompt = text.replace("/image", "", 1).strip()
            if not prompt:
                await tg_send_text(chat_id, "Напиши после /image описание картинки.")
                return {"ok": True}

            flags = CHAT_FLAGS.setdefault(chat_id, {"memory": True, "images": STATE["images_enabled"]})
            if not flags["images"]:
                await tg_send_text(chat_id, "Генерация изображений выключена ☝️ Включи в меню «🖼 Картинки».")
                return {"ok": True}

            url = await ai_image(prompt, IMAGE_SIZE)
            if url:
                await tg_send_photo(chat_id, url, caption=f"<i>{prompt}</i>")
            else:
                await tg_send_text(chat_id, "❗️Ошибка генерации изображения. Попробуй позже.")
            return {"ok": True}

        # обычный текст → GPT
        reply = await ai_answer(chat_id, text)
        await tg_send_text(chat_id, reply)
        return {"ok": True}

    # что-то иное — просто ок
    return {"ok": True}
