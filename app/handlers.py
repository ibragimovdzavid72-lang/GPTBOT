import logging
from typing import Any, Dict
from .settings import ADMIN_IDS, BOT_USERNAME, FREE_MSGS_PER_DAY, FREE_IMAGES_PER_DAY
from .tg import tg_send_message
from .openai_api import do_chat, do_image, do_image_edit
from .db import DB_ENABLED, usage_get_today

log = logging.getLogger("gptbot")

CHAT_MODES: Dict[int, str] = {}   # chat_id -> "chat"|"image"
BOT_ENABLED = True                # админ может выключать бота

# ---------- клавиатуры ----------
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

def remove_keyboard() -> Dict[str, Any]:
    return {"remove_keyboard": True}

# ---------- утилиты ----------
def _is(text: str, *variants: str) -> bool:
    """Гибкое совпадение: без регистра и эмодзи можно писать или без эмодзи."""
    low = (text or "").casefold().strip()
    for v in variants:
        vv = v.casefold().strip()
        if low == vv or low.replace("ℹ️", "").strip() == vv.replace("ℹ️", "").strip():
            return True
    return False

# ---------- обработчик ----------
async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED

    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat = msg["chat"]
        chat_id = chat["id"]
        chat_type = chat.get("type")  # private | group | supergroup
        user_id = (msg.get("from") or {}).get("id")
        if not user_id:
            return

        text = (msg.get("text") or "").strip()
        low = text.casefold()
        is_admin = user_id in ADMIN_IDS

        # В группах реагируем только на упоминание @username или слэш-команды
        if chat_type in ("group", "supergroup"):
            if not low.startswith("/") and (BOT_USERNAME and BOT_USERNAME not in low):
                return

        # /whoami — диагностика
        if low.startswith("/whoami"):
            txt, img = await usage_get_today(user_id)
            await tg_send_message(
                chat_id,
                "user_id: <code>{}</code>\nchat_id: <code>{}</code>\nDB_ENABLED: <code>{}</code>\n"
                "Сегодня: текст {} / {}, картинки {} / {}".format(
                    user_id, chat_id, DB_ENABLED, txt, FREE_MSGS_PER_DAY, img, FREE_IMAGES_PER_DAY
                )
            )
            return

        # если бот выключен админом — игнорим всех, кроме админа
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # ---------- команды ----------
        if _is(text, "/start", "start", "меню", "открыть меню"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "🟢 Режимы:\n• <b>Чат</b> — диалог с памятью (если БД включена)\n"
                "• <b>Изображение</b> — генерация по описанию или редактирование по фото/подписи",
                reply_markup=kb_main(is_admin)
            )
            return

        if _is(text, "/help", "help", "ℹ️ помощь", "помощь", "как пользоваться"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n"
                "• Напишите текст — отвечу как ChatGPT\n"
                "• <code>/image текст</code> — нарисую картинку\n"
                "• Отправьте фото + подпись — сделаю <i>редактирование</i>/вариацию\n"
                "• <code>/whoami</code> — диагностика\n"
                "• Админ: <code>/admin</code>, <code>/on</code>, <code>/off</code>, <code>/stats</code>",
                reply_markup=kb_main(is_admin)
            )
            return

        if _is(text, "/admin", "🛠 админ-панель"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только для администратора.")
                return
            status = "🟢 ВКЛ" if BOT_ENABLED else "🔴 ВЫКЛ"
            dbs = "🟢" if DB_ENABLED else "🔴"
            await tg_send_message(
                chat_id, f"🛠 <b>Админ-панель</b>\nСтатус бота: {status}\nБаза данных: {dbs}\n",
                reply_markup=kb_admin()
            )
            return

        if _is(text, "/on", "🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if _is(text, "/off", "🔴 выключить бот", "выключить бота", "/pause"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен.", reply_markup=kb_admin())
            return

        if _is(text, "/stats", "📊 статистика"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            txt, img = await usage_get_today(user_id)
            await tg_send_message(chat_id, f"📊 Сегодня: текст {txt}/{FREE_MSGS_PER_DAY}, картинки {img}/{FREE_IMAGES_PER_DAY}\nБД: {'✅' if DB_ENABLED else '❌'}")
            return

        if _is(text, "⬅️ назад", "назад"):
            await tg_send_message(chat_id, "🔙 Назад в меню.", reply_markup=kb_main(is_admin))
            return

        # переключение режимов кнопками
        if _is(text, "💬 чат с gpt", "чат", "режим чат"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат", reply_markup=kb_main(is_admin))
            return

        if _is(text, "🎨 создать изображение", "изображение", "режим изображение"):
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: Изображение. Опишите, что нарисовать.", reply_markup=kb_main(is_admin))
            return

        # ---------- /image команда ----------
        if low.startswith("/image"):
            parts = text.split(maxsplit=1)
            prompt = parts[1] if len(parts) > 1 else ""
            if not prompt:
                await tg_send_message(chat_id, "📸 Пример: <code>/image кот на скейте</code>")
            else:
                await do_image(user_id, chat_id, prompt)
            return

        # ---------- обработка фото (image-to-image) ----------
        if msg.get("photo"):
            # подпись к фото — промпт
            caption = (msg.get("caption") or "").strip() or "Сделай вариации"
            await do_image_edit(user_id, chat_id, msg["photo"], caption)
            return

        # ---------- обычный текст по текущему режиму ----------
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(user_id, chat_id, text)
        else:
            await do_chat(user_id, chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)
