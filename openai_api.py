import base64
import io
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from dateutil import parser as dtparser
from dateutil.tz import gettz
from openai import AsyncOpenAI

from settings import (
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL, OPENAI_IMAGE_MODEL,
    OPENAI_TTS_MODEL, OPENAI_STT_MODEL, TZ
)
from db import add_reminder

log = logging.getLogger("openai")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
tz = gettz(TZ)

# ---------- Moderation ----------
async def moderate(text: str) -> bool:
    try:
        r = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(r.results[0].flagged)
    except Exception:
        return True  # не блокируем при ошибке модерации

# ---------- Tools ----------
TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Упрощённый поиск по Википедии",
        "parameters": {"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}
    }},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Посчитать простое ариритметическое выражение",
        "parameters": {"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}
    }},
    {"type": "function", "function": {
        "name": "weather",
        "description": "Погода через OpenWeather (если ключ настроен)",
        "parameters": {"type":"object","properties":{"location":{"type":"string"}},"required":["location"]}
    }},
    {"type": "function", "function": {
        "name": "set_reminder",
        "description": "Создать напоминание пользователю",
        "parameters": {"type":"object","properties":{"when":{"type":"string"},"task":{"type":"string"}},"required":["when","task"]}
    }},
]

# ---------- Images ----------
async def generate_image(prompt: str, *, size: str = "1024x1024", quality: str = "standard", style: str = "vivid") -> bytes:
    """Генерация: DALL·E 3 (если OPENAI_IMAGE_MODEL=dall-e-3) или gpt-image-1."""
    try:
        gen = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
        )
        url = gen.data[0].url
        async with httpx.AsyncClient(timeout=60.0) as h:
            r = await h.get(url); r.raise_for_status()
            return r.content
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise RuntimeError("🚫 Модели изображений недоступны. Пройди Verify Organization в OpenAI, чтобы включить генерацию картинок.")
        raise
    except Exception as e:
        raise RuntimeError(f"Ошибка генерации: {e}")

async def edit_image(image_bytes: bytes, *, prompt: str, mask_bytes: Optional[bytes] = None) -> bytes:
    """Редактирование фото через REST /v1/images/edits (gpt-image-1)."""
    url = "https://api.openai.com/v1/images/edits"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    files = [
        ("model", (None, OPENAI_IMAGE_MODEL)),
        ("prompt", (None, prompt)),
        ("image", ("image.png", image_bytes, "image/png")),
    ]
    if mask_bytes:
        files.append(("mask", ("mask.png", mask_bytes, "image/png")))

    async with httpx.AsyncClient(timeout=90.0) as h:
        r = await h.post(url, headers=headers, files=files)
        if r.status_code == 403:
            raise RuntimeError("🚫 Редактирование фото недоступно. Пройди Verify Organization в OpenAI, чтобы включить edits.")
        if r.is_error:
            raise RuntimeError(f"Ошибка редактирования: {r.status_code} — {r.text}")

        data = r.json()
        img_url = data["data"][0]["url"]
        rr = await h.get(img_url)
        rr.raise_for_status()
        return rr.content
