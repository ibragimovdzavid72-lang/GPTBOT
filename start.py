#!/usr/bin/env python3
"""
Скрипт запуска для Railway деплоя.
Исправлен согласно памяти о Project Startup Configuration.
"""

import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Запуск приложения с диагностикой."""
    print("🚀 Запуск Telegram AI Bot...")
    logger.info("Инициализация приложения")
    
    # Проверка Python версии
    print(f"Python версия: {sys.version}")
    logger.info(f"Python версия: {sys.version}")
    
    # Проверка переменных окружения
    required_vars = [
        'DATABASE_URL', 
        'TELEGRAM_BOT_TOKEN', 
        'OPENAI_API_KEY',
        'SUPER_ADMIN_ID'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # Показываем только первые символы для безопасности
            masked_value = value[:8] + "..." if len(value) > 8 else value
            print(f"✅ {var}: {masked_value}")
    
    if missing_vars:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Отсутствуют переменные: {missing_vars}")
        print("\n💡 Инструкции по настройке:")
        print("1. Перейдите в Railway Dashboard")
        print("2. Откройте ваш проект")
        print("3. Перейдите в Variables") 
        print("4. Добавьте недостающие переменные:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n📚 Подробнее см. QUICK_START.md")
        sys.exit(1)
    
    # Проверка зависимостей
    try:
        import uvicorn
        print(f"✅ uvicorn найден: версия {uvicorn.__version__}")
        logger.info(f"uvicorn версия: {uvicorn.__version__}")
    except ImportError as e:
        print(f"❌ uvicorn не найден: {e}")
        print("💡 Проверьте requirements.txt и логи установки")
        logger.error(f"uvicorn импорт ошибка: {e}")
        sys.exit(1)
    
    # Проверка импорта приложения
    try:
        from main import приложение
        print("✅ Приложение main:приложение импортировано успешно")
        logger.info("Приложение импортировано успешно")
    except ImportError as e:
        print(f"❌ Ошибка импорта приложения main:приложение: {e}")
        logger.error(f"Ошибка импорта: {e}")
        
        # Диагностика импорта
        try:
            import main
            print("✅ Модуль main найден")
            if hasattr(main, 'приложение'):
                print("✅ Атрибут 'приложение' найден")
            else:
                print("❌ Атрибут 'приложение' не найден в main")
                print(f"Доступные атрибуты: {dir(main)}")
        except ImportError as ie:
            print(f"❌ Модуль main не найден: {ie}")
        
        sys.exit(1)
    
    # Получение порта
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Запуск на порту {port}")
    logger.info(f"Порт: {port}")
    
    # Проверка WEBHOOK_BASE_URL
    webhook_url = os.getenv('WEBHOOK_BASE_URL')
    if webhook_url:
        print(f"🌐 Webhook URL: {webhook_url}")
    else:
        print("⚠️  WEBHOOK_BASE_URL не установлен - webhook может не работать")
    
    print("🚀 Запуск uvicorn...")
    logger.info("Запуск сервера uvicorn")
    
    # Запуск приложения
    try:
        uvicorn.run(
            "main:приложение",
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        print(f"❌ Ошибка запуска uvicorn: {e}")
        logger.error(f"Ошибка запуска: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()м
