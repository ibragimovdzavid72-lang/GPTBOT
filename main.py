import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from settings import TELEGRAM_BOT_TOKEN, FULL_WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_SECRET, DATABASE_URL
from db import create_pool, create_tables, due_reminders, mark_reminder_done
from handlers import handle_update
from telegram_api import tg_send_message, close_http_client

log = logging.getLogger("app")
logging.basicConfig(level=logging.INFO)

state = {"pool": None, "reminder_task": None}

async def reminder_worker():
    while True:
        try:
            if state["pool"]:
                items = await due_reminders(state["pool"])
                for it in items:
                    try:
                        await tg_send_message(it["chat_id"], f"⏰ Напоминание: {it['task']}")
                        await mark_reminder_done(state["pool"], it["id"])
                    except Exception as e:
                        log.error("send reminder error: %s", e)
        except Exception as e:
            log.error("reminder loop error: %s", e)
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is empty")
    if not DATABASE_URL:
        log.warning("DATABASE_URL is empty (history/limits won't persist).")
    pool = None
    if DATABASE_URL:
        pool = await create_pool(DATABASE_URL)
        await create_tables(pool)
    state["pool"] = pool
    state["reminder_task"] = asyncio.create_task(reminder_worker())
    yield
    # shutdown
    if state["reminder_task"]:
        state["reminder_task"].cancel()
        try:
            await state["reminder_task"]
        except Exception:
            pass
    await close_http_client()
    if pool:
        await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    if WEBHOOK_SECRET:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="bad secret token")
    raw = await request.body()
    update = json.loads(raw.decode("utf-8")) if raw else {}
    asyncio.create_task(handle_update(update, pool=state["pool"]))
    return JSONResponse({"ok": True})
