import logging
from typing import Any, Dict, Optional
import httpx

from db import (
    upsert_user, set_mode, get_mode, append_msg, history, inc_limits
)
from openai_api import (
    moderate, respond_text, respond_vision, generate_image, stt_transcribe, tts_speak, edit_image
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

def get_msg(update: Dict[str, Any]) -> Dict[str, Any]:
    return update.get("message") or {}

def text_of(update: Dict[str, Any]) -> Optional[str]:
    return get_msg(update).get("text")

def ids_of(update: Dict[str, Any]) -> tuple[int, int, Optional[str]]:
    m = get_msg(update); c = m.get("chat", {}); f = m.get("from", {})
    return int(f.get("id", 0)), int(c.get("id", 0)), f.get("username")

def photos_of(update: Dict[str, Any]) -> list[Dict[str, Any]]:
    return get_msg(update).get("photo") or []

def voice_of(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return get_msg(update).get("voice")

async def handle_update(update: Dict[str, Any], *, pool):
    msg_text = text_of(update)
    user_id, chat_id, username = ids_of(update)
    await upsert_user(pool, user_id, username)

    # Команды
    if msg_text:
        low = msg_text.strip().lower()
        if low in ("/start", "start"):
            await tg_send_message(chat_id,
                "👋 Привет! Я ассистент на GPT-4o: чат, инструменты, картинки, голос.\n"
                "Выбери режим на клавиатуре ниже и напиши/скажи мне."
            )
            await tg_send_message(chat_id, "Готово.", reply_markup=kb_main())
            return
        if low in ("/help", "ℹ️ помощь", "help"):
            await tg_send_message(chat_id,
                "Режимы:\n"
                "• 💬 Чат — обычные ответы.\n"
                "• 🛠 Инструменты — web-поиск (вики), погода, калькулятор, напоминания.\n"
                "• 🎨 Картинка — генерирую изображение (DALL·E 3) или редактирую присланное фото (gpt-image-1).\n"
                "• 🔊 Голос — присылай voice; отвечу голосом и текстом.\n"
                "Сброс памяти: «🧹 Сбросить память».",
            )
            return
        if low in ("💬 чат", "chat"):
            await set_mode(pool, user_id, "chat"); await tg_send_message(chat_id, "🗣 Режим: Чат"); return
        if low in ("🛠 инструменты", "tools"):
            await set_mode(pool, user_id, "tools"); await tg_send_message(chat_id, "🔧 Режим: Инструменты"); return
        if low in ("🎨 картинка", "image"):
            await set_mode(pool, user_id, "image"); await tg_send_message(chat_id, "🎨 Режим: Картинка. Напиши промпт или пришли фото с подписью."); return
        if low in ("🔊 голос", "voice"):
            await set_mode(pool, user_id, "voice"); await tg_send_message(chat_id, "🔊 Режим: Голос. Пришли voice — распознаю; отвечу голосом."); return
        if low in ("🧹 сбросить память", "reset", "/reset"):
            await pool.execute("DELETE FROM messages USING users WHERE messages.user_id=users.id AND users.telegram_id=$1", user_id)
            await tg_send_message(chat_id, "✅ Память очищена."); return

    mode = await get_mode(pool, user_id)

    # Голос
    v = voice_of(update)
    if v:
        counters = await inc_limits(pool, user_id, is_image=False)
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан."); return

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
            await tg_send_message(chat_id, "Не удалось распознать речь."); return

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

    # Фото
    phs = photos_of(update)
    if phs:
        best = sorted(phs, key=lambda p: p.get("file_size", 0))[-1]
        furl = await tg_get_file(best["file_id"])
        async with httpx.AsyncClient() as h:
            r = await h.get(furl); r.raise_for_status()
            photo_bytes = r.content

        caption = msg_text or ""

        if mode == "image":
            # редактирование
            counters = await inc_limits(pool, user_id, is_image=True)
            if counters["daily_imgs"] > FREE_IMAGES_PER_DAY:
                await tg_send_message(chat_id, "⚠️ Лимит картинок на сегодня исчерпан."); return
            if not caption.strip():
                await tg_send_message(chat_id, "Напиши, что изменить на фото (например: «добавь бороду»)."); return
            try:
                edited = await edit_image(photo_bytes, prompt=caption.strip())
                await tg_send_document(chat_id, edited, filename="edited.png", caption=f"🖼 {caption}")
                await append_msg(pool, user_id, "user", f"[image edit]\\n{caption}")
                await append_msg(pool, user_id, "assistant", f"[edited image: {caption}]")
            except Exception as e:
                await tg_send_message(chat_id, f"{e}")
            return
        else:
            # анализ
            counters = await inc_limits(pool, user_id, is_image=False)
            if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
                await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан."); return
            prompt = caption or "Опиши, что на этом изображении."
            await append_msg(pool, user_id, "user", f"[image]\\n{prompt}")
            reply = await respond_vision(prompt, furl)
            await append_msg(pool, user_id, "assistant", reply or "")
            await tg_send_message(chat_id, reply or "Готово.")
            return

    # Текст
    if msg_text:
        if not await moderate(msg_text):
            await tg_send_message(chat_id, "⚠️ Запрос отклонён модерацией."); return

        if mode == "image":
            counters = await inc_limits(pool, user_id, is_image=True)
            if counters["daily_imgs"] > FREE_IMAGES_PER_DAY:
                await tg_send_message(chat_id, "⚠️ Лимит картинок на сегодня исчерпан."); return

            # генерация (DALL·E 3)
            size = "1024x1024"
            lt = msg_text.lower()
            if "16:9" in lt or "горизонт" in lt or "wide" in lt:
                size = "1792x1024"
            if "9:16" in lt or "вертик" in lt or "tiktok" in lt:
                size = "1024x1792"
            try:
                img = await generate_image(msg_text, size=size, quality="hd", style="vivid")
                await tg_send_document(chat_id, img, filename="image.png", caption=f"🖼 {msg_text}")
                await append_msg(pool, user_id, "assistant", f"[generated image: {msg_text}]")
            except Exception as e:
                await tg_send_message(chat_id, f"{e}")
            return

        # обычный чат/инструменты
        counters = await inc_limits(pool, user_id, is_image=False)
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, "⚠️ Лимит сообщений на сегодня исчерпан."); return
        await append_msg(pool, user_id, "user", msg_text)
        hist = await history(pool, user_id, HISTORY_LIMIT)
        sys = {"role":"system","content":"Ты умный ассистент, отвечай кратко и содержательно."}
        use_tools = (mode == "tools")
        reply = await respond_text(hist + [sys, {"role":"user","content":msg_text}], use_tools=use_tools, pool=pool, telegram_id=user_id, chat_id=chat_id)
        await append_msg(pool, user_id, "assistant", reply or "")
        await tg_send_message(chat_id, reply or "Готово.")
        return

    return
