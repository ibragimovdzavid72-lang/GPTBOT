import logging
from datetime import date
from typing import Any, Dict, List, Tuple, Optional
from .settings import DATABASE_URL

log = logging.getLogger("db")

# попробуем импортировать asyncpg
try:
    import asyncpg  # type: ignore
except Exception:
    asyncpg = None  # type: ignore

pg_pool: Any = None
DB_ENABLED = False

# ---------- SQL-схема ----------
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
  role TEXT NOT NULL,
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
  kind TEXT,          -- "chat" | "image"
  model TEXT,
  duration_ms INT,
  status TEXT,        -- "ok" | "err"
  err TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# ---------- in-memory fallback ----------
_MEM_HISTORY: Dict[int, List[Tuple[str, str]]] = {}           # chat_id -> [(role, content)]
_MEM_USAGE: Dict[Tuple[int, date], Dict[str, int]] = {}       # (user_id, date) -> {"text": n, "image": m}

# ---------- подключение ----------
async def db_safe_connect(url: Optional[str]):
    """Подключение к Postgres. Если нет asyncpg или URL пустой — работаем без БД."""
    global pg_pool, DB_ENABLED
    if not asyncpg or not url:
        log.warning("DB disabled: asyncpg not installed or DATABASE_URL empty")
        DB_ENABLED = False
        return
    try:
        pg_pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=5)
        async with pg_pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        DB_ENABLED = True
        log.info("DB enabled and ready")
    except Exception as e:
        DB_ENABLED = False
        pg_pool = None
        log.error("DB connect failed, working WITHOUT DB: %s", e)

# ---------- тонкие обёртки ----------
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

# ---------- high-level API: usage/history/analytics ----------
async def usage_get_today(user_id: int) -> Tuple[int, int]:
    """Вернуть (text_count, image_count) за текущий день для пользователя."""
    today = date.today()
    if DB_ENABLED:
        rows = await db_fetch(
            "SELECT text_count, image_count FROM usage_daily WHERE user_id=$1 AND the_date=$2",
            user_id, today
        )
        if rows:
            row = rows[0]
            return int(row["text_count"]), int(row["image_count"])
        await db_exec("INSERT INTO usage_daily(user_id, the_date) VALUES($1,$2)", user_id, today)
        return 0, 0
    # memory
    d = _MEM_USAGE.setdefault((user_id, today), {"text": 0, "image": 0})
    return d["text"], d["image"]

async def usage_inc(user_id: int, kind: str):
    """Увеличить счётчик 'chat' или 'image' за сегодня."""
    today = date.today()
    if DB_ENABLED:
        col = "text_count" if kind == "chat" else "image_count"
        await db_exec(f"UPDATE usage_daily SET {col} = {col} + 1 WHERE user_id=$1 AND the_date=$2", user_id, today)
        return
    d = _MEM_USAGE.setdefault((user_id, today), {"text": 0, "image": 0})
    if kind == "chat":
        d["text"] += 1
    else:
        d["image"] += 1

async def history_fetch(chat_id: int, limit: int = 12) -> List[Tuple[str, str]]:
    """Забрать последние сообщения чата (role, content)."""
    if DB_ENABLED:
        rows = await db_fetch(
            "SELECT role, content FROM messages WHERE chat_id=$1 ORDER BY created_at DESC LIMIT $2",
            chat_id, limit
        )
        return list(reversed([(r["role"], r["content"]) for r in rows]))
    return _MEM_HISTORY.get(chat_id, [])[-limit:]

async def history_add(chat_id: int, user_id: int, role: str, content: str):
    """Добавить сообщение в историю."""
    if DB_ENABLED:
        await db_exec(
            "INSERT INTO messages(chat_id,user_id,role,content) VALUES($1,$2,$3,$4)",
            chat_id, user_id, role, content
        )
    else:
        _MEM_HISTORY.setdefault(chat_id, []).append((role, content))

async def analytics_write(user_id: int, chat_id: int, kind: str, model: str, duration_ms: int, status: str, err: Optional[str]):
    """Записать строку аналитики (если есть БД)."""
    if DB_ENABLED:
        await db_exec(
            "INSERT INTO analytics(user_id,chat_id,kind,model,duration_ms,status,err) VALUES($1,$2,$3,$4,$5,$6,$7)",
            user_id, chat_id, kind, model, duration_ms, status, err
        )
