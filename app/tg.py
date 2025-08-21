import logging
from typing import Any, Dict
import httpx
from .settings import TELEGRAM_BOT_TOKEN

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
log = logging.getLogger("tg")

http: httpx.AsyncClient | None = None

async def init_http():
    global http
    http = httpx.AsyncClient(timeout=12.0)

async def close_http():
    global http
    if http:
        await http.aclose()

async def tg_send_message(chat_id: int, text: str, reply_markup: Dict[str, Any] | None = None):
    assert http is not None
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = await http.post(f"{TG_API}/sendMessage", json=payload)
        if r.is_error:
            log.error("sendMessage %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendMessage failed")

async def tg_send_photo(chat_id: int, url: str, caption: str = ""):
    assert http is not None
    data: Dict[str, Any] = {"chat_id": chat_id, "photo": url}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    try:
        r = await http.post(f"{TG_API}/sendPhoto", data=data)
        if r.is_error:
            log.error("sendPhoto %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("sendPhoto failed")
