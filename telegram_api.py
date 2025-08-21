import logging
from typing import Any, Dict, Optional
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt

from settings import TELEGRAM_BOT_TOKEN

log = logging.getLogger("tg")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TG_FILE_API = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"
http = httpx.AsyncClient(timeout=30.0)

@retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3))
async def tg_call(method: str, *, json: Dict[str, Any] | None = None, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    r = await http.post(f"{TG_API}/{method}", json=json, data=data)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j)
    return j

async def tg_send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await tg_call("sendMessage", json=payload)

async def tg_send_photo(chat_id: int, photo_url: str, caption: str = ""):
    data: Dict[str, Any] = {"chat_id": str(chat_id), "photo": photo_url}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    await tg_call("sendPhoto", data=data)

async def tg_send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str = ""):
    files = {"document": (filename, file_bytes)}
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    r = await http.post(f"{TG_API}/sendDocument", data=data, files=files)
    if r.is_error or not r.json().get("ok", False):
        log.error("sendDocument failed: %s %s", r.status_code, r.text)

async def tg_send_voice(chat_id: int, file_bytes: bytes, filename: str = "voice.ogg", caption: str = ""):
    files = {"voice": (filename, file_bytes)}
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    r = await http.post(f"{TG_API}/sendVoice", data=data, files=files)
    if r.is_error or not r.json().get("ok", False):
        log.error("sendVoice failed: %s %s", r.status_code, r.text)

async def tg_get_file(file_id: str) -> str:
    resp = await tg_call("getFile", json={"file_id": file_id})
    return f"{TG_FILE_API}/{resp['result']['file_path']}"

async def close_http_client():
    try:
        await http.aclose()
    except Exception:
        pass
