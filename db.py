import asyncpg
from datetime import date
from typing import Any, Dict, List

async def create_pool(dsn: str):
    return await asyncpg.create_pool(dsn, min_size=1, max_size=5)

async def create_tables(pool):
    async with pool.acquire() as con:
        await con.execute("""        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            chat_mode TEXT DEFAULT 'chat',
            daily_msgs INT DEFAULT 0,
            daily_imgs INT DEFAULT 0,
            last_date DATE DEFAULT NULL
        );""")
        await con.execute("""        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );""")
        await con.execute("""        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            chat_id BIGINT NOT NULL,
            remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
            task TEXT NOT NULL,
            done BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );""")

async def upsert_user(pool, telegram_id: int, username: str | None) -> Dict[str, Any]:
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
        if row:
            return dict(row)
        row = await con.fetchrow(
            "INSERT INTO users (telegram_id, username) VALUES ($1, $2) RETURNING *", telegram_id, username
        )
        return dict(row)

async def set_mode(pool, telegram_id: int, mode: str):
    async with pool.acquire() as con:
        await con.execute("UPDATE users SET chat_mode=$1 WHERE telegram_id=$2", mode, telegram_id)

async def get_mode(pool, telegram_id: int) -> str:
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT chat_mode FROM users WHERE telegram_id=$1", telegram_id)
        return (row and row["chat_mode"]) or "chat"

async def append_msg(pool, telegram_id: int, role: str, content: str):
    async with pool.acquire() as con:
        uid = await con.fetchval("SELECT id FROM users WHERE telegram_id=$1", telegram_id)
        if uid:
            await con.execute("INSERT INTO messages (user_id, role, content) VALUES ($1, $2, $3)", uid, role, content)

async def history(pool, telegram_id: int, limit: int) -> List[Dict[str, str]]:
    async with pool.acquire() as con:
        uid = await con.fetchval("SELECT id FROM users WHERE telegram_id=$1", telegram_id)
        if not uid:
            return []
        rows = await con.fetch("SELECT role, content FROM messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2", uid, limit)
        return [{"role": r["role"], "content": r["content"]} for r in reversed(list(rows))]

async def inc_limits(pool, telegram_id: int, *, is_image: bool = False) -> Dict[str, int]:
    today = date.today()
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT daily_msgs, daily_imgs, last_date FROM users WHERE telegram_id=$1", telegram_id)
        if not row:
            return {"daily_msgs": 0, "daily_imgs": 0}
        daily_msgs, daily_imgs, last_date = row["daily_msgs"], row["daily_imgs"], row["last_date"]
        if last_date != today:
            daily_msgs = 0
            daily_imgs = 0
        if is_image:
            daily_imgs += 1
        else:
            daily_msgs += 1
        await con.execute(
            "UPDATE users SET daily_msgs=$1, daily_imgs=$2, last_date=$3 WHERE telegram_id=$4",
            daily_msgs, daily_imgs, today, telegram_id
        )
        return {"daily_msgs": daily_msgs, "daily_imgs": daily_imgs}

async def add_reminder(pool, telegram_id: int, chat_id: int, remind_at_ts, task: str):
    async with pool.acquire() as con:
        uid = await con.fetchval("SELECT id FROM users WHERE telegram_id=$1", telegram_id)
        await con.execute(
            "INSERT INTO reminders (user_id, chat_id, remind_at, task) VALUES ($1, $2, $3, $4)",
            uid, chat_id, remind_at_ts, task
        )

async def due_reminders(pool):
    async with pool.acquire() as con:
        rows = await con.fetch(
            "SELECT id, chat_id, task FROM reminders WHERE done=false AND remind_at <= NOW()"
        )
        return [dict(r) for r in rows]

async def mark_reminder_done(pool, reminder_id: int):
    async with pool.acquire() as con:
        await con.execute("UPDATE reminders SET done=true WHERE id=$1", reminder_id)
