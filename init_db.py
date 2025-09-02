#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных Railway.

Этот скрипт создает необходимые таблицы в базе данных PostgreSQL,
выполняя SQL-скрипт из файла schema.sql.

Использование:
python init_db.py
"""

import asyncio
import asyncpg
import os

# Получаем DATABASE_URL из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

async def main():
    """Основная функция для создания таблиц в базе данных."""
    if not DATABASE_URL:
        print("❌ Переменная окружения DATABASE_URL не установлена")
        return
    
    try:
        # Подключаемся к базе данных
        print("🔄 Подключение к базе данных...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Подключение установлено")
        
        # Читаем SQL-скрипт
        print("📖 Чтение schema.sql...")
        with open("schema.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()
        
        # Выполняем SQL-скрипт
        print("⚙️ Выполнение SQL-скрипта...")
        # Разделяем скрипт на отдельные команды по точке с запятой
        commands = sql_script.split(";")
        
        for command in commands:
            command = command.strip()
            if command:
                try:
                    await conn.execute(command)
                    print(f"✅ Выполнена команда: {command[:50]}...")
                except Exception as e:
                    print(f"⚠️ Ошибка при выполнении команды: {command[:50]}... Ошибка: {e}")
        
        # Закрываем соединение
        await conn.close()
        print("✅ Таблицы успешно созданы!")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")

if __name__ == "__main__":
    asyncio.run(main())