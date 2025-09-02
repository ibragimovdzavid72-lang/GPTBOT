import asyncio
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

async def main():
    print("⏳ Подключение к базе...")
    sql = open("schema.sql", "r", encoding="utf-8").read()
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(sql)
        await conn.close()
        print("✅ Таблицы успешно созданы!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
