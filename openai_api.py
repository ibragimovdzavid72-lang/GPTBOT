from __future__ import annotations
import io, base64, re
from typing import Any, Dict, List
import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from settings import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL, OPENAI_IMAGE_MODEL, OPENAI_TTS_MODEL, OPENAI_STT_MODEL, OPENWEATHER_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def moderate(text: str) -> bool:
    try:
        r = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(r.results[0].flagged)
    except Exception:
        return True

FUNCTIONS = [
    {"type":"function","function":{
        "name":"tool_web_search","description":"Веб-поиск по DuckDuckGo",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}
    }},
    {"type":"function","function":{
        "name":"tool_calculator","description":"Точное вычисление выражения",
        "parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}
    }},
    {"type":"function","function":{
        "name":"tool_weather","description":"Погода через OpenWeather",
        "parameters":{"type":"object","properties":{"location":{"type":"string"}},"required":["location"]}
    }},
    {"type":"function","function":{
        "name":"tool_wiki","description":"Резюме из Википедии",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}
    }},
]

async def tool_web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
        return "\n".join([f"- {r['title']} — {r['href']}" for r in results]) or "Ничего не найдено."
    except Exception as e:
        return f"Ошибка поиска: {e}"

async def tool_calculator(expression: str) -> str:
    import numexpr as ne
    try: return str(ne.evaluate(expression).item())
    except Exception as e: return f"Ошибка: {e}"

async def tool_weather(location: str) -> str:
    if not OPENWEATHER_API_KEY: return "OPENWEATHER_API_KEY не настроен."
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {"q":location,"appid":OPENWEATHER_API_KEY,"units":"metric","lang":"ru"}
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(url, params=params)
        if r.status_code != 200: return "Погода: ошибка."
        j = r.json(); return f"{location}: {j['weather'][0]['description']}, {j['main']['temp']:.1f}°C"

async def tool_wiki(query: str) -> str:
    import wikipedia, re
    wikipedia.set_lang("ru" if re.search(r"[А-Яа-яЁё]", query or "") else "en")
    try:
        hits = wikipedia.search(query, results=1)
        if not hits: return "Ничего не найдено."
        page = wikipedia.page(hits[0]); return (page.summary or "")[:1200]
    except Exception as e: return f"Ошибка wiki: {e}"

async def run_tool(name: str, args: Dict[str, Any]) -> str:
    if name=="tool_web_search": return await tool_web_search(args.get("query",""))
    if name=="tool_calculator": return await tool_calculator(args.get("expression",""))
    if name=="tool_weather": return await tool_weather(args.get("location",""))
    if name=="tool_wiki": return await tool_wiki(args.get("query",""))
    return f"Неизвестный инструмент: {name}"

async def _response_with_fallback(args: Dict[str, Any]):
    try:
        return await client.responses.create(**args)
    except Exception:
        args["model"] = OPENAI_FALLBACK_MODEL
        return await client.responses.create(**args)

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
async def respond_text(history: List[Dict[str,str]], *, use_tools: bool=False) -> str:
    args: Dict[str, Any] = {"model": OPENAI_MODEL, "input": history}
    if use_tools: args["tools"] = FUNCTIONS; args["tool_choice"] = "auto"
    resp = await _response_with_fallback(args)
    if resp.output and resp.output[0].type=="tool_use":
        t = resp.output[0].tool_use
        result = await run_tool(t.name, t.arguments or {})
        follow_args = {"model": OPENAI_MODEL, "input": history + [{"role":"tool","name":t.name,"content":result}]}
        resp2 = await _response_with_fallback(follow_args)
        return resp2.output_text or ""
    return resp.output_text or ""

async def respond_vision(prompt: str, image_url: str) -> str:
    r = await client.responses.create(model=OPENAI_MODEL, input=[{"role":"user","content":[
        {"type":"input_text","text":prompt},
        {"type":"input_image","image_url":{"url":image_url}}
    ]}])
    return r.output_text or ""

async def generate_image(prompt: str, *, size: str="1024x1024") -> str:
    gen = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size=size, quality="standard", style="vivid")
    return gen.data[0].url

async def stt_transcribe(file_bytes: bytes, filename: str="audio.ogg") -> str:
    f = io.BytesIO(file_bytes); f.name = filename
    tr = await client.audio.transcriptions.create(model="whisper-1", file=f)
    return tr.text or ""

async def tts_speak(text: str, voice: str="alloy") -> bytes:
    speech = await client.audio.speech.create(model="tts-1", voice=voice, input=text, format="mp3")
    data = base64.b64decode(speech.data) if hasattr(speech, "data") else speech
    return data
