import logging
import asyncpg
from datetime import date
from typing import Any, List, Dict, Tuple, Optional
from .settings import DATABASE_URL

log = logging.getLogger("db")

pg_pool = None
DB_ENABLED = False

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
  kind TEXT,
  model TEXT,
  duration_ms INT,
  status TEXT,
  err TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

async def db_safe_connect():
    global pg_pool, DB_ENABLED
    if not DATABASE_URL:
        log.warning("DB disabled: DATABASE_URL is empty")
        return
    try:
        pg_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)
        async with pg_pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        DB_ENABLED = True
        log.info("DB enabled and ready")
    except Exception as e:
        DB_ENABLED = False
        pg_pool = None
        log.error("DB connect failed: %s", e)

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
