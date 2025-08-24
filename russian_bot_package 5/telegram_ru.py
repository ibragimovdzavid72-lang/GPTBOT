"""Инициализация бота и настройка диспетчера."""

import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config_ru import настройки

logger = logging.getLogger(__name__)

# Глобальные экземпляры бота и диспетчера
_бот: Bot = None
_диспетчер: Dispatcher = None


def получить_бота() -> Bot:
    """Получить экземпляр бота."""
    global _бот
    if _бот is None:
        _бот = Bot(
            token=настройки.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    return _бот


def получить_диспетчера() -> Dispatcher:
    """Получить экземпляр диспетчера."""
    global _диспетчер
    if _диспетчер is None:
        _диспетчер = Dispatcher(storage=MemoryStorage())
        
        # Регистрация обработчиков (согласно памяти о Handler Class)
        from handlers.start_ru import роутер as роутер_старт
        from handlers.chat_ru import роутер as роутер_чат
        from handlers.images_ru import роутер as роутер_изображения
        from handlers.voice_ru import роутер as роутер_голос
        from handlers.tools_ru import роутер as роутер_инструменты
        from handlers.reminders_ru import роутер as роутер_напоминания
        from handlers.payments_ru import роутер as роутер_платежи
        from handlers.admin_ru import роутер as роутер_админ
        from handlers.callbacks_ru import роутер as роутер_коллбеки
        
        _диспетчер.include_router(роутер_старт)
        _диспетчер.include_router(роутер_чат)
        _диспетчер.include_router(роутер_изображения)
        _диспетчер.include_router(роутер_голос)
        _диспетчер.include_router(роутер_инструменты)
        _диспетчер.include_router(роутер_напоминания)
        _диспетчер.include_router(роутер_платежи)
        _диспетчер.include_router(роутер_админ)
        _диспетчер.include_router(роутер_коллбеки)
        
        logger.info("Диспетчер настроен со всеми роутерами")
    
    return _диспетчер