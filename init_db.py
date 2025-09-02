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
        print("✅ Таблицы из schema.sql созданы или уже существовали.")

        # Проверим список таблиц
        rows = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            ORDER BY table_name;
        """)
        print("📋 Таблицы в базе данных:")
        for row in rows:
            print(" -", row["table_name"])

        await conn.close()
        print("🎉 Готово! Можно возвращать команду запуска main.py")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
