"""Главное FastAPI приложение с Telegram webhook."""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from config_ru import настройки
from database_ru import база_данных
from telegram_ru import получить_бота, получить_диспетчера
from services.reminders_ru import запустить_службу_напоминаний

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Безопасность для webhook
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Менеджер жизненного цикла приложения."""
    # Запуск
    logger.info("Запуск приложения...")
    
    # Инициализация базы данных
    await база_данных.инициализировать_бд()
    
    # Инициализация бота и установка webhook
    бот = получить_бота()
    
    if настройки.webhook_base_url:
        webhook_url = f"{настройки.webhook_base_url}{настройки.webhook_path}"
        
        webhook_info = await бот.get_webhook_info()
        if webhook_info.url != webhook_url:
            await бот.set_webhook(
                url=webhook_url,
                secret_token=настройки.webhook_secret_token,
                drop_pending_updates=True
            )
            logger.info(f"Webhook установлен: {webhook_url}")
        else:
            logger.info(f"Webhook уже установлен: {webhook_url}")
    else:
        logger.warning("WEBHOOK_BASE_URL не задан, webhook не настроен")
    
    # Запуск фоновых сервисов
    задача_напоминаний = asyncio.create_task(запустить_службу_напоминаний())
    
    logger.info("Приложение успешно запущено")
    
    yield
    
    # Завершение
    logger.info("Завершение работы приложения...")
    
    # Отмена фоновых задач
    задача_напоминаний.cancel()
    try:
        await задача_напоминаний
    except asyncio.CancelledError:
        pass
    
    # Закрытие базы данных
    await база_данных.закрыть()
    
    # Закрытие сессии бота
    await бот.session.close()
    
    logger.info("Завершение работы приложения завершено")


# Создание FastAPI приложения
приложение = FastAPI(
    title="Telegram AI Bot",
    description="Продвинутый AI-бот для Telegram с платежами, аналитикой и многим другим",
    version="1.0.0",
    lifespan=lifespan
)


@приложение.get("/")
async def корень():
    """Корневая точка входа."""
    return {"message": "Telegram AI Bot работает", "status": "ok"}


@приложение.get("/здоровье")
async def проверка_здоровья():
    """Точка входа для проверки здоровья."""
    try:
        # Проверка подключения к базе данных
        if база_данных.pool:
            async with база_данных.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Проверка здоровья не удалась: {e}")
        raise HTTPException(status_code=503, detail="Сервис недоступен")


async def проверить_секрет_webhook(request: Request):
    """Проверка секретного токена webhook."""
    if not настройки.webhook_secret_token:
        return True  # Секрет не настроен
    
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != настройки.webhook_secret_token:
        logger.warning("Неверный секретный токен webhook")
        raise HTTPException(status_code=401, detail="Неверный секретный токен")
    
    return True


@приложение.post(настройки.webhook_path)
async def обработчик_webhook(
    request: Request,
    _: bool = Depends(проверить_секрет_webhook)
):
    """Обработка обновлений Telegram webhook."""
    try:
        # Получение обновления из запроса
        данные_обновления = await request.json()
        обновление = Update(**данные_обновления)
        
        # Обработка обновления диспетчером
        бот = получить_бота()
        диспетчер = получить_диспетчера()
        
        await диспетчер.feed_update(бот, обновление)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main_ru:приложение",
        host="0.0.0.0",
        port=port,
        reload=настройки.debug
    )