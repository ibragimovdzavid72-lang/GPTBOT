# app.py
import os
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException
import httpx

# --------- Config ---------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")  # на случай, если не задано

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# HTTP клиент (переиспользуем соединения)
http = httpx.AsyncClient(timeout=15)

# --------- App ---------
app = FastAPI()


@app.get("/health")
async def health():
    return {"ok": True}


async def tg_send_message(chat_id: int, text: str, reply_markup: Dict[str, Any] | None = None):
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = await http.post(f"{TG_API}/sendMessage", json=payload)
    if r.is_error:
        log.error("sendMessage error %s: %s", r.status_code, r.text)


def default_keyboard() -> Dict[str, Any]:
    # Простые “готовые” кнопки (Reply Keyboard)
    return {
        "keyboard": [
            [{"text": "ℹ️ Помощь"}, {"text": "🖼️ Картинка"}],
            [{"text": "🟢 Включить бота"}, {"text": "🔴 Выключить бота"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    # Проверяем секрет пути, чтобы посторонние не дергали наш эндпоинт
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)

    update = await request.json()
    log.debug("update: %s", update)

    # Обработка обычных сообщений
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "") or ""

        # Команды/кнопки
        normalized = text.strip().lower()
        if normalized in ("/start", "start"):
            await tg_send_message(
                chat_id,
                "✅ Бот на Railway подключен и слушает вебхук!\nНапиши любой текст — я отвечу.",
                reply_markup=default_keyboard(),
            )
        elif normalized in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "Доступно:\n• /start — проверить работу\n• Напиши текст — я его повторю\n• “🖼️ Картинка” — заготовка под генерацию",
                reply_markup=default_keyboard(),
            )
        elif normalized in ("🖼️ картинка", "картинка"):
            await tg_send_message(chat_id, "Заготовка для генерации изображений. (Сейчас просто ответ.)")
        elif normalized in ("🟢 включить бота", "включить бота", "🔴 выключить бота", "выключить бота"):
            await tg_send_message(chat_id, "Ок, принял. (Здесь можно привязать реальный on/off флаг.)")
        else:
            # эхо-ответ
            await tg_send_message(chat_id, f"Я получил: {text}", reply_markup=default_keyboard())

    # Можно расширить: callback_query, edited_message и т.д.
    return {"ok": True}
