import logging
from datetime import date
from typing import Any, Dict, List, Tuple, Optional
from .settings import DATABASE_URL

log = logging.getLogger("db")

# Пытаемся импортировать asyncpg (если не установлен — работаем без БД)
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
  user_id_
