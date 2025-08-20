import os
import json
import time
import asyncio
import logging
from typing import Any, Dict, Optional, List, Tuple

from contextlib import asynccontextmanager
from datetime import datetime, timezone, date

import httpx
import asyncpg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from openai import AsyncOpenAI

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# ---------------- ENV ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini")

FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "20"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "5"))

ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x) for x in ADMIN_IDS_ENV.replace(" ", "").split(",") if x.isdigit()]
# ваш ID как дефолт
if 1752390166 not in ADMIN_IDS:
    ADMIN_IDS.append(1752390166)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ---------------- GLOBALS ----------------
http: Optional[httpx.AsyncClient] = None
pg: Optional[asyncpg.Pool] = None
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
BOT_ENABLED = True
CHAT_MODES: Dict[int, str] = {}  # chat_id -> "chat"|"image"

# ---------------- DB INIT ----------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
  chat_id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  chat_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  role TEXT NOT NULL,       -- "user" | "assistant"
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages(chat_id, created_at DESC);

CREATE TABLE IF NOT EXISTS usage_daily (
  user_id BIGINT NOT NULL,
  the_date DATE NOT NULL,
  text_count INT NOT NULL DEFAULT 0,
  image_count INT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, the_date)
);

CREATE TABLE IF NOT EXISTS analytics (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT,
  chat_id BIGINT,
  kind TEXT,                 -- "chat" | "image"
  model TEXT,
  duration_ms INT,
  status TEXT,               -- "ok" | "err"
  err TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

async def db_init():
    assert pg is not None
    async with pg.acquire() as conn:
        await conn.execute(SCHEMA_SQL)

async def get_or_create_user(user_id: int) -> None:
    assert pg is not None
    async with pg.acquire() as conn:
        await conn.execute(
            """INSERT INTO users(user_id, is_admin)
               VALUES($1, $2)
               ON CONFLICT (user_id) DO NOTHING""",
            user_id, user_id in ADMIN_IDS
        )

async def touch_session(chat_id: int, user_id: int) -> None:
    assert pg is not None
    async with pg.acquire() as conn:
        await conn.execute(
            """INSERT INTO sessions(chat_id, user_id, updated_at)
               VALUES($1,$2,NOW())
               ON CONFLICT (chat_id) DO UPDATE SET updated_at=EXCLUDED.updated_at, user_id=EXCLUDED.user_id""",
            chat_id, user_id
        )

async def add_message(chat_id: int, user_id: int, role: str, content: str):
    assert pg is not None
    async with pg.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages(chat_id,user_id,role,content) VALUES($1,$2,$3,$4)",
            chat_id, user_id, role, content
        )

async def fetch_history(chat_id: int, limit: int = 12) -> List[Tuple[str, str]]:
    """Return last N messages as list of (role, content) from newest->oldest reversed to oldest->newest"""
    assert pg is not None
    async with pg.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM messages WHERE chat_id=$1 ORDER BY created_at DESC LIMIT $2",
            chat_id, limit
        )
    return list(reversed([(r["role"], r["content"]) for r in rows]))

async def get_usage_today(user_id: int) -> Tuple[int, int]:
    assert pg is not None
    d = date.today()
    async with pg.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT text_count, image_count FROM usage_daily WHERE user_id=$1 AND the_date=$2",
            user_id, d
        )
        if row:
            return int(row["text_count"]), int(row["image_count"])
        else:
            await conn.execute("INSERT INTO usage_daily(user_id, the_date) VALUES($1,$2)", user_id, d)
            return 0, 0

async def inc_usage(user_id: int, kind: str):
    assert pg is not None
    d = date.today()
    col = "text_count" if kind == "chat" else "image_count"
    async with pg.acquire() as conn:
        await conn.execute(
            f"UPDATE usage_daily SET {col} = {col} + 1 WHERE user_id=$1 AND the_date=$2",
            user_id, d
        )

async def write_analytics(user_id: int, chat_id: int, kind: str, model: str, duration_ms: int, status: str, err: Optional[str]):
    assert pg is not None
    async with pg.acquire() as conn:
        await conn.execute(
            "INSERT INTO analytics(user_id,chat_id,kind,model,duration_ms,status,err) VALUES($1,$2,$3,$4,$5,$6,$7)",
            user_id, chat_id, kind, model, duration_ms, status, err
        )

# ---------------- LIFESPAN ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http, pg
    http = httpx.AsyncClient(timeout=12.0)
    pg = await asyncpg.create_pool(DATABASE_URL, max_size=5)
    await db_init()
    try:
        yield
    finally:
        await http.aclose()
        await pg.close()

app = FastAPI(lifespan=lifespan)

# ---------------- KEYBOARDS ----------------
def kb_main(is_admin: bool = False) -> Dict[str, Any]:
    rows = [
        [{"text": "💬 Чат с GPT"}, {"text": "🎨 Создать изображение"}],
        [{"text": "ℹ️ Помощь"}],
    ]
    if is_admin:
        rows.append([{"text": "🛠 Админ-панель"}])
    return {"keyboard": rows, "resize_keyboard": True}

def kb_admin() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "🟢 Включить бот"}, {"text": "🔴 Выключить бот"}],
            [{"text": "📊 Статистика"}, {"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
    }

# ---------------- TG HELPERS ----------------
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

# ---------------- MODERATION ----------------
async def moderate(text: str) -> bool:
    """Return True if text is allowed, False if flagged"""
    try:
        res = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(res.results[0].flagged)
    except Exception as e:
        log.warning("moderation failed: %s", e)
        # В случае сбоя модерации — пропускаем (или верните False, если хотите строгий режим)
        return True

# ---------------- OPENAI LOGIC ----------------
async def do_chat(user_id: int, chat_id: int, text: str):
    t0 = time.perf_counter()
    model_used = OPENAI_MODEL
    try:
        # лимиты
        txt_count, _ = await get_usage_today(user_id)
        if user_id not in ADMIN_IDS and txt_count >= FREE_MSGS_PER_DAY:
            await tg_send_message(chat_id, f"⛔ Исчерпан дневной лимит сообщений ({FREE_MSGS_PER_DAY}). Попробуйте завтра.")
            return

        # модерация входа
        if not await moderate(text):
            await tg_send_message(chat_id, "⚠️ Сообщение отклонено модерацией.")
            return

        # контекст
        history = await fetch_history(chat_id, limit=12)
        messages = [{"role": "system", "content": "Вы полезный и вежливый ассистент. Отвечайте кратко и по делу."}]
        for role, content in history:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": text})

        # основной вызов
        try:
            resp = await client.chat.completions.create(model=model_used, messages=messages, temperature=0.7, max_tokens=800)
        except Exception as e_first:
            # фоллбэк на запасную модель
            log.warning("primary model failed, trying fallback: %s", e_first)
            model_used = FALLBACK_MODEL
            resp = await client.chat.completions.create(model=model_used, messages=messages, temperature=0.7, max_tokens=800)

        answer = (resp.choices[0].message.content or "").strip() or "⚠️ Пустой ответ."
        # модерация выхода (мягкая)
        if not await moderate(answer):
            answer = "⚠️ Ответ скрыт модерацией."

        # сохранить диалог
        await add_message(chat_id, user_id, "user", text)
        await add_message(chat_id, user_id, "assistant", answer)
        await inc_usage(user_id, "chat")

        await tg_send_message(chat_id, answer)

        dt = int((time.perf_counter() - t0) * 1000)
        await write_analytics(user_id, chat_id, "chat", model_used, dt, "ok", None)
    except Exception as e:
        dt = int((time.perf_counter() - t0) * 1000)
        await write_analytics(user_id, chat_id, "chat", model_used, dt, "err", str(e))
        log.exception("chat failed")
        await tg_send_message(chat_id, f"❌ Ошибка ИИ: <code>{e}</code>")

async def do_image(user_id: int, chat_id: int, prompt: str):
    t0 = time.perf_counter()
    try:
        _, img_count = await get_usage_today(user_id)
        if user_id not in ADMIN_IDS and img_count >= FREE_IMAGES_PER_DAY:
            await tg_send_message(chat_id, f"⛔ Лимит изображений на сегодня исчерпан ({FREE_IMAGES_PER_DAY}).")
            return

        if not await moderate(prompt):
            await tg_send_message(chat_id, "⚠️ Описание изображения отклонено модерацией.")
            return

        resp = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size="1024x1024")
        url = resp.data[0].url
        await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
        await inc_usage(user_id, "image")

        dt = int((time.perf_counter() - t0) * 1000)
        await write_analytics(user_id, chat_id, "image", OPENAI_IMAGE_MODEL, dt, "ok", None)
    except Exception as e:
        dt = int((time.perf_counter() - t0) * 1000)
        await write_analytics(user_id, chat_id, "image", OPENAI_IMAGE_MODEL, dt, "err", str(e))
        log.exception("image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: <code>{e}</code>")

# ---------------- HANDLER ----------------
async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED
    try:
        # Telegram может прислать разные типы апдейтов — обрабатываем только сообщения и payment-хуки/inline можно добавить ниже
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            # платежи/инвойсы
            pcq = update.get("pre_checkout_query")
            if pcq:
                # здесь можно валидировать заказ; пока подтверждаем всегда
                await answer_pre_checkout_query(pcq["id"], ok=True)
            sp = (update.get("message") or {}).get("successful_payment")
            # здесь вы бы выставили тариф пользователю sp["telegram_payment_charge_id"]
            return

        chat_id = msg["chat"]["id"]
        user_id = (msg.get("from") or {}).get("id")
        if not user_id:
            return

        await get_or_create_user(user_id)
        await touch_session(chat_id, user_id)

        text = (msg.get("text") or "").strip()
        low = text.casefold()

        # нормализация команд
        cmd = ""
        if low.startswith("/"):
            first = low.split()[0]
            cmd = first.split("@", 1)[0]

        is_admin = user_id in ADMIN_IDS

        # диагностика
        if cmd == "/whoami":
            await tg_send_message(chat_id, f"user_id: <code>{user_id}</code>\nchat_id: <code>{chat_id}</code>\nadmins: <code>{ADMIN_IDS}</code>\ncmd: <code>{cmd}</code>")
            return

        # если бот выключен
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # команды
        if cmd in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "🟢 Доступные режимы:\n"
                "• <b>Чат с GPT</b> — отвечаю как ИИ\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Выберите режим кнопкой или просто напишите сообщение.",
                reply_markup=kb_main(is_admin=is_admin),
            )
            return

        if cmd in ("/help",) or low in ("ℹ️ помощь", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n"
                "• «💬 Чат с GPT» — диалог с контекстом\n"
                "• «🎨 Создать изображение» — генерация картинки\n"
                "• Команды: <code>/image ваш_текст</code>, <code>/whoami</code>\n"
                "• Админ: <code>/admin</code>, <code>/on</code>, <code>/off</code>, <code>/stats</code>",
            )
            return

        if cmd == "/admin" or low == "🛠 админ-панель":
            if not is_admin:
                await tg_send_message(chat_id, f"🚫 Только для администратора. (вижу user_id=<code>{user_id}</code>)")
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            await tg_send_message(chat_id, f"🛠 <b>Админ-панель</b>\nСтатус: {status}\nКоманды: /on /off /stats", reply_markup=kb_admin())
            return

        if cmd == "/on" or low in ("🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if cmd == "/off" or low in ("🔴 выключить бот", "выключить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен.", reply_markup=kb_admin())
            return

        if cmd == "/stats" or low == "📊 статистика":
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Нет доступа.")
                return
            txt, img = await get_usage_today(user_id)
            await tg_send_message(chat_id, f"📊 Статистика (сегодня):\n— Ваши тексты: <b>{txt}</b> / {FREE_MSGS_PER_DAY}\n— Ваши изображения: <b>{img}</b> / {FREE_IMAGES_PER_DAY}")
            return

        if low == "⬅️ назад":
            await tg_send_message(chat_id, "🔙 Назад в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        if low == "💬 чат с gpt":
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат с GPT (с памятью)")
            return

        if low == "🎨 создать изображение":
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: Изображение. Опишите, что нарисовать.")
            return

        if cmd == "/image" or low.startswith("/image "):
            parts = text.split(maxsplit=1)
            prompt = parts[1] if len(parts) > 1 else ""
            if not prompt:
                await tg_send_message(chat_id, "📸 Пример: <code>/image кот на скейте</code>")
                return
            await do_image(user_id, chat_id, prompt)
            return

        # по текущему режиму
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(user_id, chat_id, text)
        else:
            await do_chat(user_id, chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)

# ---------------- PAYMENTS (STUBS) ----------------
async def answer_pre_checkout_query(pre_checkout_query_id: str, ok: bool, error_message: Optional[str] = None):
    assert http is not None
    data: Dict[str, Any] = {"pre_checkout_query_id": pre_checkout_query_id, "ok": ok}
    if not ok and error_message:
        data["error_message"] = error_message
    try:
        await http.post(f"{TG_API}/answerPreCheckoutQuery", json=data)
    except Exception:
        log.exception("answerPreCheckoutQuery failed")

# ---------------- ROUTES ----------------
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True, "enabled": BOT_ENABLED, "admins": ADMIN_IDS}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    if TELEGRAM_WEBHOOK_TOKEN:
        if request.headers.get("x-telegram-bot-api-secret-token") != TELEGRAM_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403)
    try:
        raw = await request.body()
        update = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        log.warning("Non-JSON update")
        return JSONResponse({"ok": True})
    asyncio.create_task(handle_update(update))
    return JSONResponse({"ok": True})
