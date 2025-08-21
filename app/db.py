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
_MEM_USAGE: Dict[Tuple[int, date], Dict[str, int]] = {}
