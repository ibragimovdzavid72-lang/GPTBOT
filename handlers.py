from __future__ import annotations
import httpx
from typing import Any, Dict
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ChatAction
from settings import FREE_MSGS_PER_DAY, FREE_IMAGES_PER_DAY, HISTORY_LIMIT, RATE_PER_MIN, ADMIN_IDS, BOT_TOKEN
from db import SessionLocal, upsert_user, get_active_session, append_message, get_history, set_mode, inc_limits, add_reminder
from openai_api import moderate, respond_text, respond_vision, generate_image, stt_transcribe, tts_speak

router = Router()

KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💬 Текст"), KeyboardButton(text="🧰 Инструменты")],
        [KeyboardButton(text="🖼 Картинка"), KeyboardButton(text="🎙 Голос")],
        [KeyboardButton(text="🧠 Память ВКЛ/ВЫКЛ"), KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True
)

_last_hits: dict[int, list[float]] = {}
def rate_ok(uid: int) -> bool:
    if RATE_PER_MIN <= 0: return True
    import time
    now = time.time()
    wins = _last_hits.setdefault(uid, [])
    _last_hits[uid] = [t for t in wins if now - t <= 60]
    if len(_last_hits[uid]) >= RATE_PER_MIN: return False
    _last_hits[uid].append(now); return True

@router.message(F.text == "/start")
async def cmd_start(msg: Message):
    await msg.answer("👋 Привет! Я мультибот (GPT‑4o): текст, картинки, голос и инструменты. Выбирай режим на клавиатуре ниже.", reply_markup=KB)

@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(msg: Message):
    await msg.answer("Режимы:\n• 💬 Текст — обычные ответы\n• 🧰 Инструменты — поиск/погода/калькулятор/вики\n• 🖼 Картинка — генерация (DALL·E 3)\n• 🎙 Голос — пришли voice; отвечу голосом\n• 🧠 Память — переключатель хранения истории в БД")

@router.message(F.text.in_({"💬 Текст","🧰 Инструменты","🖼 Картинка","🎙 Голос","🧠 Память ВКЛ/ВЫКЛ"}))
async def switch_mode(msg: Message):
    uid = msg.from_user.id
    async with SessionLocal() as s:
        u = await upsert_user(s, uid, msg.from_user.username)
        if msg.text == "💬 Текст":
            await set_mode(s, u, "chat"); await s.commit(); await msg.answer("🗣 Режим: Текст")
        elif msg.text == "🧰 Инструменты":
            await set_mode(s, u, "tools"); await s.commit(); await msg.answer("🧰 Режим: Инструменты")
        elif msg.text == "🖼 Картинка":
            await set_mode(s, u, "image"); await s.commit(); await msg.answer("🖼 Режим: Картинка")
        elif msg.text == "🎙 Голос":
            await set_mode(s, u, "voice"); await s.commit(); await msg.answer("🎙 Режим: Голос. Пришли voice-сообщение.")
        else:
            sess = await get_active_session(s, u); sess.memory_enabled = not sess.memory_enabled; await s.commit()
            await msg.answer(f"🧠 Память: {'ВКЛ' if sess.memory_enabled else 'ВЫКЛ'}")

@router.message(F.photo)
async def on_photo(msg: Message):
    uid = msg.from_user.id; chat_id = msg.chat.id
    async with SessionLocal() as s:
        u = await upsert_user(s, uid, msg.from_user.username)
        if not rate_ok(uid): await msg.answer("⏳ Слишком часто. Попробуй через пару секунд."); return
        sess = await get_active_session(s, u)
        ph = msg.photo[-1]
        file = await msg.bot.get_file(ph.file_id)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        prompt = msg.caption or "Опиши это изображение."
        await msg.bot.send_chat_action(chat_id, ChatAction.TYPING)
        reply = await respond_vision(prompt, url)
        await append_message(s, sess.id, "user", f"[image]\n{prompt}")
        await append_message(s, sess.id, "assistant", reply or ""); await s.commit()
        await msg.answer(reply or "Готово.")

@router.message(F.voice)
async def on_voice(msg: Message):
    uid = msg.from_user.id; chat_id = msg.chat.id
    async with SessionLocal() as s:
        u = await upsert_user(s, uid, msg.from_user.username)
        if not rate_ok(uid): await msg.answer("⏳ Слишком часто. Попробуй через пару секунд."); return
        counters = await inc_limits(s, u, is_image=False); await s.commit()
        file = await msg.bot.get_file(msg.voice.file_id)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        async with httpx.AsyncClient() as h:
            r = await h.get(url); r.raise_for_status(); ogg = r.content
        await msg.bot.send_chat_action(chat_id, ChatAction.TYPING)
        try: text = await stt_transcribe(ogg, filename="audio.ogg")
        except Exception: await msg.answer("Не удалось распознать речь."); return
        if not await moderate(text): await msg.answer("⚠️ Запрос отклонён модерацией."); return
        sess = await get_active_session(s, u)
        await append_message(s, sess.id, "user", text)
        hist = await get_history(s, sess.id, 20)
        reply = await respond_text(hist + [{"role":"user","content":text}], use_tools=False)
        await append_message(s, sess.id, "assistant", reply or ""); await s.commit()
        if reply:
            audio = await tts_speak(reply)
            await msg.answer_audio(audio, title="Ответ", performer="GPT‑4o")
        else:
            await msg.answer("Готово.")

@router.message(F.text)
async def on_text(msg: Message):
    uid = msg.from_user.id; chat_id = msg.chat.id; text = msg.text.strip()
    async with SessionLocal() as s:
        u = await upsert_user(s, uid, msg.from_user.username)
        if u.is_banned: await msg.answer("🚫 Доступ запрещён."); return
        if not rate_ok(uid): await msg.answer("⏳ Слишком часто. Попробуй через пару секунд."); return
        sess = await get_active_session(s, u)
        mode = u.mode or "chat"
        if mode == "image":
            counters = await inc_limits(s, u, is_image=True); await s.commit()
            if counters["daily_imgs"] > FREE_IMAGES_PER_DAY and not u.is_premium:
                await msg.answer("⚠️ Лимит картинок на сегодня исчерпан."); return
            size = "1024x1024"; lt = text.lower()
            if "16:9" in lt or "горизонт" in lt or "wide" in lt: size="1792x1024"
            if "9:16" in lt or "вертик" in lt or "tiktok" in lt: size="1024x1792"
            await msg.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
            try:
                url = await generate_image(text, size=size)
                await msg.answer_photo(url, caption=f"🖼 {text}")
                await append_message(s, sess.id, "assistant", f"[generated image: {text}]"); await s.commit()
            except Exception as e:
                await msg.answer(f"Ошибка генерации: {e}")
            return
        counters = await inc_limits(s, u, is_image=False); await s.commit()
        if counters["daily_msgs"] > FREE_MSGS_PER_DAY and not u.is_premium:
            await msg.answer("⚠️ Лимит сообщений на сегодня исчерпан."); return
        if not await moderate(text): await msg.answer("⚠️ Запрос отклонён модерацией."); return
        await append_message(s, sess.id, "user", text)
        hist = await get_history(s, sess.id, 20)
        await msg.bot.send_chat_action(chat_id, ChatAction.TYPING)
        use_tools = (mode == "tools")
        reply = await respond_text(hist + [{"role":"user","content":text}], use_tools=use_tools)
        await append_message(s, sess.id, "assistant", reply or ""); await s.commit()
        await msg.answer(reply or "Готово.")
