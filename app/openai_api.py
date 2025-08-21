import time
import logging
from typing import List, Tuple, Optional
from datetime import date
from openai import AsyncOpenAI

from .settings import (
    OPENAI_API_KEY, OPENAI_MODEL, FALLBACK_MODEL,
    OPENAI_IMAGE_MODEL, ADMIN_IDS, FREE_MSGS_PER_DAY, FREE_IMAGES_PER_DAY
)
from .tg import tg_send_message, tg_send_photo
from .db import db_fetch, db_exec
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

log = logging.getLogger("openai")

# память в RAM если нет БД
MEM_HISTORY: dict[int, List[Tuple[str,str]]] = {}
MEM_USAGE: dict[Tuple[int,date], dict[str,int]] = {}

async def moderate(text: str) -> bool:
    try:
        res = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(res.results[0].flagged)
    except Exception as e:
        log.warning("moderation failed: %s", e)
        return True

async def do_chat(user_id: int, chat_id: int, text: str):
    txt_count = MEM_USAGE.get((user_id,date.today()),{"text":0}).get("text",0)
    if user_id not in ADMIN_IDS and txt_count >= FREE_MSGS_PER_DAY:
        await tg_send_message(chat_id, f"⛔ Лимит сообщений: {FREE_MSGS_PER_DAY}")
        return
    if not await moderate(text):
        await tg_send_message(chat_id, "⚠️ Сообщение отклонено модерацией.")
        return

    history = MEM_HISTORY.get(chat_id, [])
    messages = [{"role":"system","content":"Ты помощник, отвечай коротко."}]
    for r,c in history[-12:]:
        messages.append({"role":r,"content":c})
    messages.append({"role":"user","content":text})

    model_used = OPENAI_MODEL
    try:
        resp = await client.chat.completions.create(model=model_used, messages=messages)
    except Exception:
        model_used = FALLBACK_MODEL
        resp = await client.chat.completions.create(model=model_used, messages=messages)

    answer = resp.choices[0].message.content.strip()
    MEM_HISTORY.setdefault(chat_id,[]).append(("user",text))
    MEM_HISTORY[chat_id].append(("assistant",answer))
    MEM_USAGE.setdefault((user_id,date.today()),{"text":0,"image":0})["text"]+=1

    await tg_send_message(chat_id, answer)

async def do_image(user_id: int, chat_id: int, prompt: str):
    img_count = MEM_USAGE.get((user_id,date.today()),{"image":0}).get("image",0)
    if user_id not in ADMIN_IDS and img_count >= FREE_IMAGES_PER_DAY:
        await tg_send_message(chat_id, f"⛔ Лимит картинок: {FREE_IMAGES_PER_DAY}")
        return
    if not await moderate(prompt):
        await tg_send_message(chat_id,"⚠️ Описание отклонено модерацией.")
        return
    resp = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size="1024x1024")
    url = resp.data[0].url
    await tg_send_photo(chat_id,url,caption=f"🖼 {prompt}")
    MEM_USAGE.setdefault((user_id,date.today()),{"text":0,"image":0})["image"]+=1
    import httpx
from .settings import TELEGRAM_BOT_TOKEN

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

async def do_image_edit(user_id: int, chat_id: int, photo_sizes: list, prompt: str):
    """
    Обработка отправленного фото: делаем edit/variation по подписи.
    Берём самую большую версию фото из массива photo_sizes.
    """
    try:
        # 1) Получаем file_path у Telegram
        file_id = photo_sizes[-1]["file_id"]
        async with httpx.AsyncClient(timeout=15.0) as h:
            fr = await h.get(f"{TG_API}/getFile", params={"file_id": file_id})
            fr.raise_for_status()
            fjson = fr.json()
            file_path = fjson["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            img_resp = await h.get(file_url)
            img_resp.raise_for_status()
            local_png = "/tmp/input.png"
            with open(local_png, "wb") as f:
                f.write(img_resp.content)

        # 2) Модерация промпта
        if not await moderate(prompt):
            await tg_send_message(chat_id, "⚠️ Подпись отклонена модерацией.")
            return

        # 3) Отправляем edit в OpenAI
        with open(local_png, "rb") as f:
            edit = await client.images.edits(model=OPENAI_IMAGE_MODEL, image=f, prompt=prompt, size="1024x1024")
        url = edit.data[0].url
        await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
        await usage_inc(user_id, "image")
    except Exception as e:
        log.exception("image edit failed: %s", e)
        await tg_send_message(chat_id, f"❌ Ошибка обработки изображения: <code>{e}</code>")

