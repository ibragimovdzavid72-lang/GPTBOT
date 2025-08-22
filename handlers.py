import logging
from typing import Any, Dict, Optional
import httpx

from db import (
    upsert_user, set_mode, get_mode, append_msg, history, inc_limits
)
from openai_api import (
    moderate, respond_text, respond_vision, generate_image, stt_transcribe, tts_speak
)
from telegram_api import (
    tg_send_message, tg_send_photo, tg_send_document, tg_send_voice, tg_get_file
)
from settings import HISTORY_LIMIT, FREE_MSGS_PER_DAY, FREE_IMAGES_PER_DAY

log = logging.getLogger("handlers")

def kb_main() -> Dict[str, Any]:
    rows = [
        [{"text": "💬 Чат"}, {"text": "🛠 Инструменты"}],
        [{"text": "🎨 Картинка"}, {"text": "🔊 Голос"}],
        [{"text": "ℹ️ Помощь"}, {"text": "🧹 Сбросить память"}],
    ]
    return {"keyboard": rows, "resize_keyboard": True}

def _msg(update: Dict[str, Any]) -> Dict[str, Any]:
    return update.get("message") or {}

def _text(update: Dict[str, Any]) -> Optional[str]:
    return _msg(update).get("text")

def _ids(update: Dict[str, Any]) -> tuple[int, int, Optional[str]]:
    m = _msg(update); c = m.get("chat", {}); f = m.get("from", {})
    return int(f.get("id", 0)), int(c.get("id", 0)), f.get("username")

def _photos(update: Dict[str, Any]) -> list[Dict[str, Any]]:
    return _msg(update).get("photo") or []

def _voice(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _msg(update).get("voice")

async def handle_update(update: Dict[str, Any], *, pool):
    text = _text(update)
    user_id, chat_id, username = _ids(update)
    await upsert_user(pool, user_id, username)

    # команды
    if text:
        low = text.strip().lower()
        if low in ("/start", "start"):
            await tg_send_message(chat_id,
                "👋 Привет! Я ассистент на GPT‑4o: чат, инструменты, картинки, голос.
"
                "Выбери режим на клавиатуре ниже и напиши/скажи мне.",
            )
            await tg_send_message(chat_id, "Готово.", reply_markup=kb_main())
            return
        if low in ("/help", "ℹ️ помощь", "help"):
            await tg_send_message(chat_id,
                "Режимы:
"
                "• 💬 Чат — обычные ответы.
"
                "• 🛠 Инструменты — web-поиск (вики), погода, калькулятор, напоминания.
"
                "• 🎨 Картинка — генерирую изображение по описанию.
"
                "• 🔊 Голос — присылай voice; отвечу голосом и текстом.
"
                "Сброс памяти: «🧹 Сбросить память».",
            )
            return
        if low in ("💬 чат", "chat"):
            await set_mode(pool, user_id, "chat")
            await tg_send_message(chat_id, "🗣 Режим: Чат")
            return
        if low in ("🛠 инструменты", "tools"):
            await set_mode(pool, user_id, "tools")
            await tg_send_message(chat_id, "🔧 Режим: Инструменты")
            return
        if low in ("🎨 картинка", "image"):
            await set_mode(pool, user_id, "image")
            await tg_send_message(chat_id, "🎨 Режим: Картинка. Опиши, что сгенерировать.")
            return
        if low in ("🔊 голос", "voice"):
            await set_mode(pool, user_id, "voice")
            await tg_send_message(chat_id, "🔊 Режим: Голос. Пришли voice — распознаю; отвечу голосом.")
            return
        if low in ("🧹 сбросить память", "reset", "/reset"):
            await pool.execute("DELETE FROM messages USING users WHERE messages.user_id=users.id AND users.telegram_id=$1", user_id)
            await tg_send_message(chat_id, "✅ Память очищена.")
            return

    mode = await get_mode(pool, user_id)

    # voice?
    v = _voice(update)
    if v:
        counters = await inc_limits(pool, user_id, is_image=False)
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан.")
            return
        file_url = await tg_get_file(v["file_id"])
        async with httpx.AsyncClient() as h:
            r = await h.get(file_url); r.raise_for_status()
            ogg_bytes = r.content
        try:
            text = await stt_transcribe(ogg_bytes, filename="audio.ogg")
        except Exception:
            from pydub import AudioSegment; import io
            audio = AudioSegment.from_file(io.BytesIO(ogg_bytes), format="ogg")
            buf = io.BytesIO(); audio.export(buf, format="mp3"); buf.seek(0)
            text = await stt_transcribe(buf.read(), filename="audio.mp3")
        if not text.strip():
            await tg_send_message(chat_id, "Не удалось распознать речь.")
            return
        await append_msg(pool, user_id, "user", text)
        hist = await history(pool, user_id, HISTORY_LIMIT)
        sys = {"role":"system","content":"Ты дружелюбный голосовой ассистент. Отвечай кратко и по делу."}
        reply = await respond_text(hist + [sys, {"role":"user","content":text}], use_tools=False, pool=pool, telegram_id=user_id, chat_id=chat_id)
        await append_msg(pool, user_id, "assistant", reply or "")
        if reply:
            await tg_send_message(chat_id, reply)
            try:
                voice_bytes = await tts_speak(reply)
                await tg_send_voice(chat_id, voice_bytes, filename="reply.ogg")
            except Exception as e:
                log.warning("TTS failed: %s", e)
        return

    # photo?
    phs = _photos(update)
    if phs:
        counters = await inc_limits(pool, user_id, is_image=False)
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан.")
            return
        best = sorted(phs, key=lambda p: p.get("file_size", 0))[-1]
        furl = await tg_get_file(best["file_id"])
        prompt = _text(update) or "Опиши, что на этом изображении."
        await append_msg(pool, user_id, "user", f"[image]\n{prompt}")
        reply = await respond_vision(prompt, furl)
        await append_msg(pool, user_id, "assistant", reply or "")
        await tg_send_message(chat_id, reply or "Готово.")
        return

    # text?
    if text:
        if not await moderate(text):
            await tg_send_message(chat_id, "⚠️ Запрос отклонён модерацией.")
            return

        if mode == "image":
            counters = await inc_limits(pool, user_id, is_image=True)
            if counters["daily_imgs"] > FREE_IMAGES_PER_DAY:
                await tg_send_message(chat_id, "⚠️ Лимит картинок на сегодня исчерпан.")
                return
            await append_msg(pool, user_id, "user", text)
            img = await generate_image(text)
            await tg_send_document(chat_id, img, filename="image.png", caption=f"🖼 {text}")
            await append_msg(pool, user_id, "assistant", f"[generated image: {text}]")
            return

        counters = await inc_limits(pool, user_id, is_image=False)
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан.")
            return
        await append_msg(pool, user_id, "user", text)
        hist = await history(pool, user_id, HISTORY_LIMIT)
        sys = {"role":"system","content":"Ты умный ассистент, отвечай кратко и содержательно."}
        use_tools = (mode == "tools")
        reply = await respond_text(hist + [sys, {"role":"user","content":text}], use_tools=use_tools, pool=pool, telegram_id=user_id, chat_id=chat_id)
        await append_msg(pool, user_id, "assistant", reply or "")
        await tg_send_message(chat_id, reply or "Готово.")
        return

    return
