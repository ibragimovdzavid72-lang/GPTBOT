import base64
import io
import logging
import re
from typing import Any, Dict, List

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

async def moderate(text: str) -> bool:
    try:
        r = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(r.results[0].flagged)
    except Exception:
        return True

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Поиск по Википедии (упрощённый веб-поиск)",
        "parameters": {"type": "object","properties":{"query":{"type":"string"}},"required":["query"]}
    }},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Посчитать простое выражение",
        "parameters": {"type": "object","properties":{"expression":{"type":"string"}},"required":["expression"]}
    }},
    {"type": "function", "function": {
        "name": "weather",
        "description": "Погода через OpenWeather",
        "parameters": {"type": "object","properties":{"location":{"type":"string"}},"required":["location"]}
    }},
    {"type": "function", "function": {
        "name": "set_reminder",
        "description": "Создать напоминание пользователю",
        "parameters": {"type": "object","properties":{"when":{"type":"string"},"task":{"type":"string"}},"required":["when","task"]}
    }},
]

async def tool_web_search(query: str) -> str:
    import wikipedia
    lang = "ru" if re.search(r"[А-Яа-яЁё]", query or "") else "en"
    wikipedia.set_lang(lang)
    try:
        hits = wikipedia.search(query, results=1)
        if not hits:
            return "Ничего не найдено."
        page = wikipedia.page(hits[0])
        return (page.summary or "")[:1200]
    except Exception as e:
        return f"Ошибка поиска: {e}"

async def tool_calculator(expression: str) -> str:
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expression or ""):
        return "Недопустимое выражение."
    try:
        val = eval(expression, {"__builtins__": None}, {})
        return str(val)
    except Exception as e:
        return f"Ошибка вычисления: {e}"

async def tool_weather(location: str) -> str:
    import os, requests
    api = os.getenv("OPENWEATHER_API_KEY", "")
    if not api:
        return "Погода не настроена."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return "Не удалось получить данные погоды."
        j = r.json()
        desc = j["weather"][0]["description"]
        temp = j["main"]["temp"]
        return f"Погода в {location}: {desc}, {temp:.1f}°C"
    except Exception as e:
        return f"Ошибка запроса погоды: {e}"

async def tool_set_reminder(pool, telegram_id: int, chat_id: int, when: str, task: str) -> str:
    try:
        dt = dtparser.parse(when, dayfirst=True)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=tz)
        await add_reminder(pool, telegram_id, chat_id, dt, task)
        return f"Напоминание установлено на {dt.astimezone(tz).strftime('%Y-%m-%d %H:%M %Z')}: {task}"
    except Exception as e:
        return f"Не удалось распознать время: {e}"

async def run_tools(tool_name: str, args: Dict[str, Any], *, pool, telegram_id: int, chat_id: int) -> str:
    if tool_name == "web_search":
        return await tool_web_search(args.get("query", ""))
    if tool_name == "calculator":
        return await tool_calculator(args.get("expression", ""))
    if tool_name == "weather":
        return await tool_weather(args.get("location", ""))
    if tool_name == "set_reminder":
        return await tool_set_reminder(pool, telegram_id, chat_id, args.get("when", ""), args.get("task", ""))
    return f"Неизвестный инструмент: {tool_name}"

async def respond_text(history: List[Dict[str, str]], *, use_tools: bool, pool, telegram_id: int, chat_id: int) -> str:
    args: Dict[str, Any] = {"model": OPENAI_MODEL, "input": history}
    if use_tools:
        args["tools"] = TOOLS
        args["tool_choice"] = "auto"
    # Responses API итеративно вызывает инструменты
    while True:
        resp = await client.responses.create(**args)
        if resp.output and resp.output[0].type == "tool_use":
            tool = resp.output[0].tool_use
            name = tool.name
            targs = tool.arguments or {}
            result = await run_tools(name, targs, pool=pool, telegram_id=telegram_id, chat_id=chat_id)
            args["input"] = history + [{"role": "tool", "name": name, "content": result}]
            continue
        return resp.output_text or ""

async def respond_vision(prompt: str, image_url: str) -> str:
    resp = await client.responses.create(
        model=OPENAI_MODEL,
        input=[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":{"url":image_url}}]}],
    )
    return resp.output_text or ""

async def generate_image(prompt: str) -> bytes:
    img = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size="1024x1024")
    url = img.data[0].url
    async with httpx.AsyncClient(timeout=60.0) as h:
        r = await h.get(url)
        r.raise_for_status()
        return r.content

async def stt_transcribe(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    f = io.BytesIO(file_bytes); f.name = filename
    tr = await client.audio.transcriptions.create(model=OPENAI_STT_MODEL, file=f)
    return tr.text or ""

async def tts_speak(text: str, voice: str = "alloy") -> bytes:
    from pydub import AudioSegment
    # получаем mp3
    mp3 = await client.audio.speech.create(model=OPENAI_TTS_MODEL, voice=voice, input=text, format="mp3")
    mp3_bytes = base64.b64decode(mp3.data) if hasattr(mp3, "data") else mp3
    # конвертируем в ogg/opus
    seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
    out = io.BytesIO()
    seg.export(out, format="ogg", codec="libopus")
    out.seek(0)
    return out.read()
