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

async def initialize_database():
    """Инициализация базы данных - создание таблиц если они не существуют."""
    if not DATABASE_URL:
        print("❌ Переменная окружения DATABASE_URL не установлена")
        return False
    
    try:
        # Подключаемся к базе данных
        print("🔄 Подключение к базе данных...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Подключение установлено")
        
        # Проверяем существование таблиц
        print("🔍 Проверка существующих таблиц...")
        tables_exist = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'logs' OR table_name = 'bot_config'
            )
        """)
        
        if tables_exist:
            print("✅ Таблицы уже существуют в базе данных")
            await conn.close()
            return True
        
        # Читаем SQL-скрипт
        print("📖 Чтение schema.sql...")
        try:
            with open("schema.sql", "r", encoding="utf-8") as f:
                sql_script = f.read()
        except FileNotFoundError:
            print("❌ Файл schema.sql не найден")
            await conn.close()
            return False
        except Exception as e:
            print(f"❌ Ошибка при чтении schema.sql: {e}")
            await conn.close()
            return False
        
        # Выполняем SQL-скрипт
        print("⚙️ Выполнение SQL-скрипта...")
        # Разделяем скрипт на отдельные команды по точке с запятой
        commands = sql_script.split(";")
        
        success_count = 0
        for i, command in enumerate(commands):
            command = command.strip()
            if command:
                try:
                    await conn.execute(command)
                    print(f"✅ Выполнена команда {i+1}: {command[:50]}...")
                    success_count += 1
                except Exception as e:
                    print(f"⚠️ Ошибка при выполнении команды {i+1}: {command[:50]}... Ошибка: {e}")
        
        # Закрываем соединение
        await conn.close()
        print(f"✅ Таблицы успешно созданы! Успешно выполнено команд: {success_count}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")
        return False

async def main():
    """Основная функция для создания таблиц в базе данных."""
    success = await initialize_database()
    if success:
        print("\n🎉 Инициализация базы данных завершена успешно!")
    else:
        print("\n💥 Инициализация базы данных завершена с ошибками!")

if __name__ == "__main__":
    asyncio.run(main())
