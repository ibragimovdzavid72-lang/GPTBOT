"""
Инновационный Русский AI Телеграм Бот v4.0
==========================================
Полнофункциональный бот с исправленными кнопками и монетизацией
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

import structlog
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config_ru import настройки
from database_ru import МенеджерБазыДанных
from telegram_ru import ТелеграмКлиент
from openai_ru import ОпенАИКлиент
from handlers_ru import ОбработчикСообщений
from payments_ru import МенеджерПлатежей
from analytics_ru import АналитикаДвижок
from admin_ru import АдминистраторБота

# Настройка логирования
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer(colors=True)],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

лог = structlog.get_logger("главный")

# Глобальные объекты
менеджер_бд = None
телеграм_клиент = None
опенаи_клиент = None
обработчик_сообщений = None
менеджер_платежей = None
аналитика_движок = None
администратор = None


@asynccontextmanager
async def жизненный_цикл_приложения(приложение: FastAPI):
    """Управление жизненным циклом приложения."""
    await инициализировать_сервисы()
    yield
    await очистить_сервисы()


приложение = FastAPI(
    title="🚀 AI CHAT 2 - Инновационный Русский Бот",
    description="Революционный AI-бот с максимальными возможностями",
    version="4.0.0",
    lifespan=жизненный_цикл_приложения
)

приложение.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def инициализировать_сервисы():
    """Инициализация всех сервисов бота."""
    global менеджер_бд, телеграм_клиент, опенаи_клиент, обработчик_сообщений, менеджер_платежей, аналитика_движок, администратор
    
    try:
        лог.info("🚀 Запуск AI CHAT 2...")
        
        # Инициализация БД
        менеджер_бд = МенеджерБазыДанных()
        await менеджер_бд.инициализировать()
        лог.info("✅ База данных подключена")
        
        # Инициализация клиентов
        телеграм_клиент = ТелеграмКлиент(настройки.телеграм.токен_бота, менеджер_бд)
        опенаи_клиент = ОпенАИКлиент()
        лог.info("✅ API клиенты инициализированы")
        
        # Инициализация сервисов
        менеджер_платежей = МенеджерПлатежей(телеграм_клиент, менеджер_бд)
        аналитика_движок = АналитикаДвижок(менеджер_бд) if настройки.функции.включить_аналитику else None
        администратор = АдминистраторБота(телеграм_клиент, менеджер_бд, аналитика_движок)
        
        # Главный обработчик с инновациями
        обработчик_сообщений = ОбработчикСообщений(
            телеграм_клиент, опенаи_клиент, менеджер_бд, 
            менеджер_платежей, аналитика_движок
        )
        
        # Установка вебхука
        if настройки.телеграм.полная_ссылка_вебхука:
            await телеграм_клиент.установить_вебхук(
                настройки.телеграм.полная_ссылка_вебхука,
                настройки.телеграм.секрет_вебхука
            )
            лог.info("✅ Вебхук установлен", ссылка=настройки.телеграм.полная_ссылка_вебхука)
        
        лог.info("🎉 AI CHAT 2 успешно запущен!")
        
    except Exception as e:
        лог.error("❌ Ошибка инициализации", ошибка=str(e))
        raise


async def очистить_сервисы():
    """Очистка ресурсов при завершении."""
    if телеграм_клиент:
        await телеграм_клиент.закрыть()
    if менеджер_бд:
        await менеджер_бд.закрыть()
    лог.info("🔄 Сервисы очищены")


# API маршруты
@приложение.post(настройки.телеграм.путь_вебхука)
async def обработать_вебхук(запрос: Request, фоновые_задачи: BackgroundTasks):
    """Обработка входящих обновлений от Telegram."""
    try:
        данные = await запрос.json()
        
        # Валидация секрета
        секрет_заголовок = запрос.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if настройки.телеграм.секрет_вебхука and секрет_заголовок != настройки.телеграм.секрет_вебхука:
            raise HTTPException(status_code=403, detail="Неверный секрет")
        
        # Обработка в фоне
        if "message" in данные:
            фоновые_задачи.add_task(
                обработчик_сообщений.обработать_сообщение,
                данные["message"]
            )
        elif "callback_query" in данные:
            фоновые_задачи.add_task(
                обработчик_сообщений.обработать_колбек_запрос,
                данные["callback_query"]
            )
        
        return {"status": "ok"}
        
    except Exception as e:
        лог.error("Ошибка вебхука", ошибка=str(e))
        raise HTTPException(status_code=500, detail="Внутренняя ошибка")


@приложение.get("/здоровье")
async def проверка_здоровья():
    """Проверка состояния сервиса."""
    return {
        "статус": "работает",
        "версия": "4.0.0",
        "время": time.time(),
        "описание": "🚀 AI CHAT 2 - Инновационный Русский Бот"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main_ru:приложение",
        host=настройки.хост,
        port=настройки.порт,
        reload=настройки.отладка,
        log_level="info"
    )
