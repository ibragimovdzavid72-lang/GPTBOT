"""Bot initialization and dispatcher setup."""

import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings

logger = logging.getLogger(__name__)

# Global bot and dispatcher instances
_bot: Bot = None
_dispatcher: Dispatcher = None


def get_bot() -> Bot:
    """Get bot instance."""
    global _bot
    if _bot is None:
        _bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    return _bot


def get_dispatcher() -> Dispatcher:
    """Get dispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher(storage=MemoryStorage())
        
        # Register handlers
        from app.handlers.start import router as start_router
        from app.handlers.chat import router as chat_router
        from app.handlers.images import router as images_router
        from app.handlers.voice import router as voice_router
        from app.handlers.tools import router as tools_router
        from app.handlers.reminders import router as reminders_router
        from app.handlers.payments import router as payments_router
        from app.handlers.admin import router as admin_router
        from app.handlers.callbacks import router as callbacks_router
        
        _dispatcher.include_router(start_router)
        _dispatcher.include_router(chat_router)
        _dispatcher.include_router(images_router)
        _dispatcher.include_router(voice_router)
        _dispatcher.include_router(tools_router)
        _dispatcher.include_router(reminders_router)
        _dispatcher.include_router(payments_router)
        _dispatcher.include_router(admin_router)
        _dispatcher.include_router(callbacks_router)
        
        logger.info("Dispatcher configured with all routers")
    
    return _dispatcher