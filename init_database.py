#!/usr/bin/env python3
"""
Скрипт инициализации базы данных
================================
Принудительно создает все таблицы базы данных для русского AI бота.
Используется для исправления проблем с отсутствующими таблицами.
"""

import asyncio
import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from config_ru import настройки
from database_ru import МенеджерБД
import structlog

# Настройка логирования
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer(colors=True)],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

лог = structlog.get_logger("init_database")


async def main():
    """Инициализация базы данных."""
    try:
        лог.info("🚀 Запуск инициализации базы данных...")
        
        # Проверяем DATABASE_URL
        if not настройки.база_данных.ссылка:
            лог.error("❌ DATABASE_URL не установлен!")
            лог.info("Установите переменную окружения DATABASE_URL")
            лог.info("Пример: postgresql://user:password@host:port/database")
            return False
        
        лог.info(f"Подключение к базе данных: {настройки.база_данных.ссылка}")
        
        # Создаем менеджер БД
        менеджер_бд = МенеджерБД(настройки.база_данных.ссылка)
        
        # Инициализируем
        await менеджер_бд.инициализировать()
        
        # Проверяем здоровье
        if await менеджер_бд.проверка_здоровья():
            лог.info("🎉 База данных успешно инициализирована!")
            лог.info("✅ Все таблицы созданы и готовы к работе")
            return True
        else:
            лог.error("❌ Проблемы с базой данных!")
            return False
            
    except Exception as e:
        лог.error("❌ Ошибка инициализации базы данных", ошибка=str(e))
        return False
    finally:
        if 'менеджер_бд' in locals():
            await менеджер_бд.закрыть()


if __name__ == "__main__":
    # Запускаем инициализацию
    результат = asyncio.run(main())
    
    if результат:
        print("\n✅ УСПЕХ: База данных готова к работе!")
        print("Теперь можно запускать бота: python main_ru.py")
        sys.exit(0)
    else:
        print("\n❌ ОШИБКА: Не удалось инициализировать базу данных")
        print("Проверьте DATABASE_URL и доступность PostgreSQL")
        sys.exit(1)
