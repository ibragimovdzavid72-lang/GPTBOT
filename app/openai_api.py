import time
import logging
import subprocess
import httpx
from openai import AsyncOpenAI

from .settings import (
    OPENAI_API_KEY, OPENAI_MODEL, FALLBACK_MODEL, OPENAI_IMAGE_MODEL,
    FREE_MSGS_PER_DAY, FREE_IMAGES_PER_DAY, ADMIN_IDS, TELEGRAM_BOT_TOKEN
)
from .db import history_fetch, history_add, usage_get_today, usage_inc, analytics_write
from .tg import tg_send_message, tg_send_photo, tg_send_action

log = logging.getLogger("gptbot")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ---------- модерация ----------
async def moderate(text: str) -> bool:
    try:
        res = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(res.results[0].flagged)
    except Exception as e:
        log.warning("moderation failed: %s", e)
        return True

# ---------- чат ----------
async def do_chat(user_id: int, chat_id: int, text: str):
    t0 = time.perf_counter()
    model_used = OPENAI_MODEL
    try:
        txt, _ = await usage_get_today(user_id)
        if user_id not in ADMIN_IDS and txt >= FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, f"⛔ Лимит сообщений на сегодня: {FREE_MSGS_PER_DAY}.")
            return

        if not await moderate(text):
            await tg_send_message(chat_id, "⚠️ Сообщение отклонено модерацией.")
            return

        history = await history_fetch(chat_id, 12)
        messages = [{"role": "system", "content": "Вы полезный ассистент. Отвечайте кратко и по делу."}]
        for role, content in history:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": text})

        await tg_send_action(chat_id, "typing")

        try:
            resp = await client.chat.completions.create(
                model=model_used, messages=messages, temperature=0.7, max_tokens=800
            )
        except Exception as e1:
            log.warning("Primary model failed (%s). Trying fallback...", e1)
            model_used = FALLBACK_MODEL
            resp = await client.chat.completions.create(
                model=model_used, messages=messages, temperature=0.7, max_tokens=800
            )

        answer = (resp.choices[0].message.content or "").strip() or "⚠️ Пустой ответ."
        if not await moderate(answer):
            answer = "⚠️ Ответ скрыт модерацией."

        await history_add(chat_id, user_id, "user", text)
        await history_add(chat_id, user_id, "assistant", answer)
        await usage_inc(user_id, "chat")

        await tg_send_message(chat_id, answer)
        await analytics_write(
            user_id, chat_id, "chat", model_used, int((time.perf_counter()-t0)*1000), "ok", None
        )
    except Exception as e:
        await analytics_write(
            user_id, chat_id, "chat", model_used, int((time.perf_counter()-t0)*1000), "err", str(e)
        )
        await tg_send_message(chat_id, f"❌ Ошибка ИИ: <code>{e}</code>")

# ---------- генерация изображения ----------
async def do_image(user_id: int, chat_id: int, prompt: str):
    t0 = time.perf_counter()
    try:
        _, img = await usage_get_today(user_id)
        if user_id not in ADMIN_IDS and img >= FREE_IMAGES_PER_DAY:
            await tg_send_message(chat_id, f"⛔ Лимит изображений на сегодня: {FREE_IMAGES_PER_DAY}.")
            return

        if not await moderate(prompt):
            await tg_send_message(chat_id, "⚠️ Описание отклонено модерацией.")
            return

        await tg_send_action(chat_id, "upload_photo")

        resp = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size="1024x1024")
        url = resp.data[0].url
        await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
        await usage_inc(user_id, "image")

        await analytics_write(
            user_id, chat_id, "image", OPENAI_IMAGE_MODEL, int((time.perf_counter()-t0)*1000), "ok", None
        )
    except Exception as e:
        await analytics_write(
            user_id, chat_id, "image", OPENAI_IMAGE_MODEL, int((time.perf_counter()-t0)*1000), "err", str(e)
        )
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: <code>{e}</code>")

# ---------- редактирование/вариации присланного фото ----------
async def do_image_edit(user_id: int, chat_id: int, photo_sizes: list, prompt: str):
    try:
        file_id = photo_sizes[-1]["file_id"]
        async with httpx.AsyncClient(timeout=20.0) as h:
            fr = await h.get(f"{TG_API}/getFile", params={"file_id": file_id})
            fr.raise_for_status()
            file_path = fr.json()["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            img_resp = await h.get(file_url)
            img_resp.raise_for_status()
            src = "/tmp/input.png"
            with open(src, "wb") as f:
                f.write(img_resp.content)

        if not await moderate(prompt):
            await tg_send_message(chat_id, "⚠️ Подпись отклонена модерацией.")
            return

        await tg_send_action(chat_id, "upload_photo")

        try:
            with open(src, "rb") as f:
                edit = await client.images.edits(
                    model=OPENAI_IMAGE_MODEL, image=f, prompt=prompt, size="1024x1024"
                )
            url = edit.data[0].url
            await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
            await usage_inc(user_id, "image")
            return
        except Exception as e1:
            msg = str(e1).lower()
            policy_hit = any(x in msg for x in [
                "content_policy_violation", "safety system", "not allowed", "policy"
            ])
            if not policy_hit:
                raise

        # безопасный фоллбэк (без текста/брендов)
        safe_prompt = (
            "Неоновая минималистичная иконка дружелюбного робота на тёмном фоне, "
            "без текста и логотипов, чистый современный стиль, высокое качество."
        )
        gen = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=safe_prompt, size="1024x1024")
        url = gen.data[0].url
        await tg_send_photo(
            chat_id, url,
            caption="🖼 Редактирование с брендами/текстом запрещено — сделал безопасный вариант без текста."
        )
        await usage_inc(user_id, "image")

    except Exception as e:
        log.exception("image edit failed: %s", e)
        await tg_send_message(chat_id, f"❌ Ошибка обработки изображения: <code>{e}</code>")

# ---------- голосовые ----------
async def do_voice(user_id: int, chat_id: int, voice_obj: dict):
    try:
        file_id = voice_obj["file_id"]
        async with httpx.AsyncClient(timeout=30.0) as h:
            fr = await h.get(f"{TG_API}/getFile", params={"file_id": file_id})
            fr.raise_for_status()
            file_path = fr.json()["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            r = await h.get(file_url)
            r.raise_for_status()

        src_ogg = "/tmp/input.ogg"
        with open(src_ogg, "wb") as f:
            f.write(r.content)

        # пробуем .ogg как есть
        try:
            with open(src_ogg, "rb") as f:
                tr = await client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=f
                )
            text = (tr.text or "").strip()
        except Exception as e1:
            # конвертируем через ffmpeg → mp3
            mp3 = "/tmp/input.mp3"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src_ogg, "-ar", "16000", "-ac", "1", mp3],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                with open(mp3, "rb") as f:
                    tr = await client.audio.transcriptions.create(
                        model="gpt-4o-mini-transcribe",
                        file=f
                    )
                text = (tr.text or "").strip()
            except Exception as e2:
                raise RuntimeError(f"transcribe failed: {e1} | after-convert: {e2}")

        if not text:
            await tg_send_message(chat_id, "⚠️ Не удалось распознать голосовое сообщение.")
            return

        # показываем, что «печатает», и отвечаем на распознанный текст
        await tg_send_message(chat_id, f"🗣️ Распознал: <i>{text}</i>")
        await tg_send_action(chat_id, "typing")

        try:
            await do_chat(user_id, chat_id, text)
        except Exception as e:
            log.exception("do_chat from voice failed: %s", e)
            await tg_send_message(chat_id, f"❌ Ошибка ответа на голосовое: <code>{e}</code>")

    except Exception as e:
        log.exception("voice failed: %s", e)
        await tg_send_message(chat_id, f"❌ Ошибка распознавания голоса: <code>{e}</code>")
