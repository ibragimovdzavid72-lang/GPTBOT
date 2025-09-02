#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота.

Этот скрипт загружает переменные окружения и запускает основной модуль бота.
Перед запуском убедитесь, что у вас есть файл .env с необходимыми настройками.

Использование:
python run_bot.py
"""

import asyncio
import logging
import sys
import os

# Добавляем текущую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Загружаем переменные окружения
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  Библиотека python-dotenv не установлена. Переменные окружения будут читаться из системы.")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_environment():
    """Проверяет наличие необходимых переменных окружения."""
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY", 
        "DATABASE_URL"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("❌ Отсутствуют необходимые переменные окружения:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        logger.error("💡 Создайте файл .env и добавьте необходимые переменные.")
        return False
    
    logger.info("✅ Все необходимые переменные окружения присутствуют")
    return True

async def main():
    """Основная функция для запуска бота."""
    logger.info("🚀 Запуск Telegram AI Agent...")
    
    # Проверяем переменные окружения
    if not check_environment():
        return
    
    try:
        # Импортируем и запускаем основной модуль бота
        from app.main import main as bot_main
        await bot_main()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Неожиданная ошибка: {e}")
        sys.exit(1)
