"""Упрощённое FastAPI приложение для Railway деплоя."""

import os
import logging
from fastapi import FastAPI

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание FastAPI приложения
приложение = FastAPI(
    title="Telegram AI Bot",
    description="Telegram AI Bot",
    version="1.0.0"
)

@приложение.get("/")
async def корень():
    """Корневая точка входа."""
    return {"message": "Telegram AI Bot работает", "status": "ok"}

@приложение.get("/health")
async def проверка_здоровья():
    """Проверка здоровья."""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_simple:приложение", host="0.0.0.0", port=port)
