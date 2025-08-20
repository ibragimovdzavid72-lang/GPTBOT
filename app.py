import os
import json
import time
import asyncio
import logging
from typing import Any, Dict, Optional, List, Tuple

from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from openai import AsyncOpenAI

# --- необязательная БД: подключим динамически, чтобы без неё не падать
try:
    import asyncpg  # type: ignore
except Exception:  # если пакет не установлен — работаем без БД
    asyncpg = None  # type: ignore

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gptbot")

# ---------------- ENV ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini")

DATABASE_URL = os.getenv("DATABASE_URL")  # МОЖЕТ БЫТЬ ПУСТО/НЕПРАВИЛЬНО — тогда работаем без БД

FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "20"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "5"))

ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x) for x in ADMIN_IDS_ENV.replace(" ", "").split(",") if x.isdigit()]
if 1752390166 not in ADMIN_IDS:
    ADMIN_IDS.append(1752390166)  # ваш ID по умолчанию

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ---------------- GLOBALS ----------------
http: Optional[httpx.AsyncClient] = None
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
pg_pool = None  # type: ignore
DB_ENABLED = False  # переключатель: включим после успешного коннекта

BOT_ENABLED = True
CHAT_MODES: Dict[int, str] = {}  # chat_id -> "chat"|"image"

# ---- in-memory (когда БД нет): простая память и лимиты на процесс
MEM_HISTORY: Dict[int, List[Tuple[str, str]]] = {}         # chat_id -> [(role, content), ...]
MEM_USAGE: Dict[Tuple[int, date], Dict[str, int]] = {}     # (user_id, date) -> {"text": n, "image": m}

# ---------------- SQL ----------------
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

# ---------------- DB HELPERS ----------------
async def db_safe_connect(url: Optional[str]):
    """Пытаемся подключиться к БД. Любая ошибка — работаем без БД (не падаем)."""
    global pg_pool, DB_ENABLED
    if not asyncpg or not url:
        log.warning("DB disabled: asyncpg not installed or DATABASE_URL is empty")
        DB_ENABLED = False
        return
    try:
        # Railway даёт URL вида:
        # postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require
        # Если у вас остались заглушки (USER:PASSWORD@HOST:PORT/DBNAME) — будет ошибка parse.
        pg_pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=5)  # безопасные значения
        async with pg_pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        DB_ENABLED = True
        log.info("DB enabled and ready")
    except Exception as e:
        DB_ENABLED = False
        pg_pool = None
        log.error("DB connect failed, running WITHOUT database: %s", e)

async def db_exec(query: str, *args):
    if not DB_ENABLED or not pg_pool:
        return
    async with pg_pool.acquire() as conn:
        await conn.execute(query, *args)

async def db_fetch(query: str, *args):
    if not DB_ENABLED or not pg_pool:
        return []
    async with pg_pool.acquire() as conn:
        return await conn.fetch(query, *args)

# ---------------- LIFESPAN ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http
    http = httpx.AsyncClient(timeout=12.0)
    await db_safe_connect(DATABASE_URL)
    try:
        yield
    finally:
        await http.aclose()
        if DB_ENABLED and pg_pool:
            await pg_pool.close()

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
    try:
        res = await client.moderations.create(model="omni-moderation-latest", input=text)
        return not bool(res.results[0].flagged)
    except Exception as e:
        log.warning("moderation failed: %s", e)
        return True  # не роняем UX при сбое модерации

# ---------------- USAGE & HISTORY (DB/Memory) ----------------
async def usage_get_today(user_id: int) -> Tuple[int, int]:
    today = date.today()
    if DB_ENABLED:
        row = None
        rows = await db_fetch("SELECT text_count, image_count FROM usage_daily WHERE user_id=$1 AND the_date=$2", user_id, today)
        if rows:
            row = rows[0]
        else:
            await db_exec("INSERT INTO usage_daily(user_id, the_date) VALUES($1,$2)", user_id, today)
            row = {"text_count": 0, "image_count": 0}
        return int(row["text_count"]), int(row["image_count"])
    # memory
    d = MEM_USAGE.setdefault((user_id, today), {"text": 0, "image": 0})
    return d["text"], d["image"]

async def usage_inc(user_id: int, kind: str):
    today = date.today()
    if DB_ENABLED:
        col = "text_count" if kind == "chat" else "image_count"
        await db_exec(f"UPDATE usage_daily SET {col} = {col} + 1 WHERE user_id=$1 AND the_date=$2", user_id, today)
        return
    d = MEM_USAGE.setdefault((user_id, today), {"text": 0, "image": 0})
    if kind == "chat":
        d["text"] += 1
    else:
        d["image"] += 1

async def history_fetch(chat_id: int, limit: int = 12) -> List[Tuple[str, str]]:
    if DB_ENABLED:
        rows = await db_fetch(
            "SELECT role, content FROM messages WHERE chat_id=$1 ORDER BY created_at DESC LIMIT $2",
            chat_id, limit
        )
        return list(reversed([(r["role"], r["content"]) for r in rows]))
    return MEM_HISTORY.get(chat_id, [])[-limit:]

async def history_add(chat_id: int, user_id: int, role: str, content: str):
    if DB_ENABLED:
        await db_exec("INSERT INTO messages(chat_id,user_id,role,content) VALUES($1,$2,$3,$4)", chat_id, user_id, role, content)
    else:
        MEM_HISTORY.setdefault(chat_id, []).append((role, content))

async def analytics_write(user_id: int, chat_id: int, kind: str, model: str, duration_ms: int, status: str, err: Optional[str]):
    if DB_ENABLED:
        await db_exec(
            "INSERT INTO analytics(user_id,chat_id,kind,model,duration_ms,status,err) VALUES($1,$2,$3,$4,$5,$6,$7)",
            user_id, chat_id, kind, model, duration_ms, status, err
        )

# ---------------- OPENAI ----------------
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
        messages = [{"role": "system", "content": "Вы полезный и вежливый ассистент. Отвечайте кратко и по делу."}]
        for role, content in history:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": text})

        try:
            resp = await client.chat.completions.create(model=model_used, messages=messages, temperature=0.7, max_tokens=800)
        except Exception as e1:
            log.warning("Primary model failed (%s). Try fallback.", e1)
            model_used = FALLBACK_MODEL
            resp = await client.chat.completions.create(model=model_used, messages=messages, temperature=0.7, max_tokens=800)

        answer = (resp.choices[0].message.content or "").strip() or "⚠️ Пустой ответ."
        if not await moderate(answer):
            answer = "⚠️ Ответ скрыт модерацией."

        await history_add(chat_id, user_id, "user", text)
        await history_add(chat_id, user_id, "assistant", answer)
        await usage_inc(user_id, "chat")

        await tg_send_message(chat_id, answer)

        await analytics_write(user_id, chat_id, "chat", model_used, int((time.perf_counter() - t0) * 1000), "ok", None)
    except Exception as e:
        await analytics_write(user_id, chat_id, "chat", model_used, int((time.perf_counter() - t0) * 1000), "err", str(e))
        log.exception("chat failed")
        await tg_send_message(chat_id, f"❌ Ошибка ИИ: <code>{e}</code>")

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

        resp = await client.images.generate(model=OPENAI_IMAGE_MODEL, prompt=prompt, size="1024x1024")
        url = resp.data[0].url
        await tg_send_photo(chat_id, url, caption=f"🖼 {prompt}")
        await usage_inc(user_id, "image")

        await analytics_write(user_id, chat_id, "image", OPENAI_IMAGE_MODEL, int((time.perf_counter() - t0) * 1000), "ok", None)
    except Exception as e:
        await analytics_write(user_id, chat_id, "image", OPENAI_IMAGE_MODEL, int((time.perf_counter() - t0) * 1000), "err", str(e))
        log.exception("image failed")
        await tg_send_message(chat_id, f"❌ Ошибка генерации изображения: <code>{e}</code>")

# ---------------- HANDLER ----------------
async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        user_id = (msg.get("from") or {}).get("id")
        if not user_id:
            return

        text = (msg.get("text") or "").strip()
        low = text.casefold()

        cmd = ""
        if low.startswith("/"):
            first = low.split()[0]
            cmd = first.split("@", 1)[0]

        is_admin = user_id in ADMIN_IDS

        # диагностика
        if cmd == "/whoami":
            await tg_send_message(chat_id, f"user_id: <code>{user_id}</code>\nchat_id: <code>{chat_id}</code>\nadmins: <code>{ADMIN_IDS}</code>\nDB_ENABLED: <code>{DB_ENABLED}</code>")
            return

        # выключение бота
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
                "• <b>Чат с GPT</b> — диалог (с памятью, если БД включена)\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Выберите режим кнопкой или просто напишите сообщение.",
                reply_markup=kb_main(is_admin=is_admin),
            )
            return

        if cmd in ("/help",) or low in ("ℹ️ помощь", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n"
                "• «💬 Чат с GPT» — контекст сохраняется, если настроена БД\n"
                "• «🎨 Создать изображение» — генерирую картинку\n"
                "• Команды: <code>/image текст</code>, <code>/whoami</code>\n"
                "• Админ: <code>/admin</code>, <code>/on</code>, <code>/off</code>, <code>/stats</code>",
            )
            return

        if cmd == "/admin" or low == "🛠 админ-панель":
            if not is_admin:
                await tg_send_message(chat_id, f"🚫 Только для администратора. (вижу user_id=<code>{user_id}</code>)")
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            dbs = "🟢" if DB_ENABLED else "🔴"
            await tg_send_message(chat_id, f"🛠 <b>Админ-панель</b>\nСтатус бота: {status}\nБаза данных: {dbs}\nКоманды: /on /off /stats", reply_markup=kb_admin())
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
            txt, img = await usage_get_today(user_id)
            await tg_send_message(chat_id, f"📊 Статистика (сегодня):\n— Тексты: <b>{txt}</b> / {FREE_MSGS_PER_DAY}\n— Картинки: <b>{img}</b> / {FREE_IMAGES_PER_DAY}\nБаза данных: {'✅' if DB_ENABLED else '❌'}")
            return

        if low == "⬅️ назад":
            await tg_send_message(chat_id, "🔙 Назад в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        if low == "💬 чат с gpt":
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: Чат с GPT")
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

        # по режиму
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(user_id, chat_id, text)
        else:
            await do_chat(user_id, chat_id, text)

    except Exception as e:
        log.exception("handle_update failed: %s", e)

# ---------------- ROUTES ----------------
@app.get("/")
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"ok": True, "enabled": BOT_ENABLED, "db": DB_ENABLED, "admins": ADMIN_IDS}

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
