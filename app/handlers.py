import logging
from typing import Any, Dict

from .settings import ADMIN_IDS
from .tg import tg_send_message
from .openai_api import do_chat, do_image

log = logging.getLogger("gptbot")
CHAT_MODES: Dict[int, str] = {}

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
            [{"text": "📊 Статистика"}, {"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
    }

async def handle_update(update: Dict[str, Any]):
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        user_id = (msg.get("from") or {}).get("id")
        if not user_id:
            return

        text = (msg.get("text") or "").strip()
        low = text.casefold()

        cmd = ""
        if low.startswith("/"):
            first = low.split()[0]
            cmd = first.split("@", 1)[0]

        is_admin = user_id in ADMIN_IDS

        if cmd in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 Добро пожаловать! Выберите режим:",
                reply_markup=kb_main(is_admin=is_admin),
            )
            return

        if low == "💬 чат с gpt":
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат")
            return

        if low == "🎨 создать изображение":
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: Изображение. Опишите, что нарисовать.")
            return

        if cmd == "/image" or low.startswith("/image "):
            parts = text.split(maxsplit=1)
            prompt = parts[1] if len(parts) > 1 else ""
            if not prompt:
                await tg_send_message(chat_id, "📸 Пример: /image кот на скейте")
                return
            await do_image(user_id, chat_id, prompt)
            return

        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(user_id, chat_id, text)
        else:
            await do_chat(user_id, chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)
