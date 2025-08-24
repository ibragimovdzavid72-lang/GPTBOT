#!/usr/bin/env python3
"""Скрипт инициализации базы данных."""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь поиска модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_ru import база_данных

async def init_db():
    """Инициализация базы данных."""
    try:
        print("Инициализация базы данных...")
        await база_данных.инициализировать_бд()
        print("✅ База данных успешно инициализирована")
        
        # Закрываем соединение
        await база_данных.закрыть()
        print("🔒 Соединение с базой данных закрыто")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(init_db())
    sys.exit(0 if success else 1)
